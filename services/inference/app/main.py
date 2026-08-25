"""FastAPI surface for the inference service.

Phase 1 keeps jobs in process: analysis runs synchronously and the result is held
in an in-memory store so ``GET /v1/analyze/{job_id}`` works against the same
contract the queued implementation will use. Redis/BullMQ replaces the store in
Phase 2 without changing the response shape.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import get_settings
from app.models import audio_registry, registry
from app.pipeline import hash_cache
from app.pipeline.analyze import DecodeError, analyze_image
from app.pipeline.analyze_audio import AudioTooLongError, analyze_audio
from app.pipeline.analyze_video import VideoTooLongError, analyze_video
from app.pipeline.audio_io import AudioDecodeError
from app.pipeline.video_io import VideoDecodeError
from app.schemas import AnalysisReport, AnalyzeByHashRequest, HealthResponse

logger = logging.getLogger(__name__)

app = FastAPI(
    title="VeriFrame Inference",
    version="0.1.0",
    description=(
        "Synthetic-media detection. Returns a calibrated probability with an "
        "uncertainty band and supporting evidence — never a binary verdict."
    ),
)

# The extension calls this service directly from a chrome-extension:// origin,
# unauthenticated, since it must work without a signed-in web session -- see
# config.cors_allow_origin_regex and DECISIONS.md.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=get_settings().cors_allow_origin_regex,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Phase 1 job store. Bounded only by process lifetime; Phase 2 moves this to Redis.
_JOBS: dict[str, AnalysisReport] = {}

_ACCEPTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/bmp"}
_ACCEPTED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska"}
# Whatever the installed libsndfile build supports through soundfile -- WAV and
# FLAC unconditionally; OGG/MP3 are accepted here but may fail to decode on a
# platform whose bundled libsndfile predates MP3 support, surfacing as a 400.
_ACCEPTED_AUDIO_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/x-flac",
    "audio/ogg",
    "audio/mpeg",
}
_ACCEPTED_TYPES = _ACCEPTED_IMAGE_TYPES | _ACCEPTED_VIDEO_TYPES | _ACCEPTED_AUDIO_TYPES


@app.get("/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    loaded = registry.is_loaded()
    versions: dict[str, str] = {
        "face_detector": "YuNet (OpenCV zoo, MIT)",
        "landmarker": "MediaPipe FaceLandmarker (Google, Apache-2.0)",
    }

    if loaded:
        versions["spatial"] = registry.get_spatial_model().version_string
    else:
        versions["spatial"] = f"{settings.spatial_model_id} (not loaded)"

    versions["audio"] = (
        audio_registry.get_audio_model().version_string
        if audio_registry.is_loaded()
        else "AASIST (not loaded)"
    )

    return HealthResponse(
        status="ok" if loaded else "degraded",
        model_versions=versions,
        models_loaded=loaded,
    )


@app.post("/v1/analyze", response_model=AnalysisReport)
async def analyze(file: UploadFile = File(...)) -> AnalysisReport:
    settings = get_settings()
    content_type = file.content_type or ""
    is_video = content_type in _ACCEPTED_VIDEO_TYPES
    is_audio = content_type in _ACCEPTED_AUDIO_TYPES

    if content_type not in _ACCEPTED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"unsupported content type {content_type!r}; "
                f"expected one of {sorted(_ACCEPTED_TYPES)}"
            ),
        )

    raw = await file.read()
    if is_video:
        size_limit = settings.max_video_bytes
    elif is_audio:
        size_limit = settings.max_audio_bytes
    else:
        size_limit = settings.max_upload_bytes
    if len(raw) > size_limit:
        raise HTTPException(
            status_code=413,
            detail=f"upload exceeds {size_limit} bytes",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="empty upload")

    job_id = uuid.uuid4().hex

    try:
        if is_video:
            report = analyze_video(
                raw, filename=file.filename, mime_type=content_type, job_id=job_id
            )
        elif is_audio:
            report = analyze_audio(
                raw, filename=file.filename, mime_type=content_type, job_id=job_id
            )
        else:
            report = analyze_image(
                raw, filename=file.filename, mime_type=content_type, job_id=job_id
            )
    except (DecodeError, VideoDecodeError, AudioDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (VideoTooLongError, AudioTooLongError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Never let raw media or byte content reach the logs (privacy principle 4).
        logger.exception("analysis failed for job %s", job_id)
        raise HTTPException(status_code=500, detail="analysis failed") from exc

    _JOBS[job_id] = report

    # Best-effort: an unreachable cache degrades to "not cached today", not to
    # a failed response for an analysis the caller already waited on.
    hash_cache.cache_report(
        report.provenance.phash,
        report.model_dump(mode="json"),
        datetime.fromisoformat(report.ttl_expires_at),
    )

    return report


@app.post("/v1/analyze/hash", response_model=AnalysisReport)
def analyze_by_hash(request: AnalyzeByHashRequest) -> AnalysisReport:
    """Look up a previously computed report by perceptual hash.

    Lets a caller check "has this already been analysed?" before uploading
    anything -- the point of computing the hash client-side in the first
    place. A miss and an unreachable cache both read as 404 to the caller:
    the caller's job either way is to fall back to a real upload, not to
    distinguish "no" from "couldn't ask".
    """
    try:
        cached = hash_cache.lookup(request.phash)
    except hash_cache.HashCacheUnavailable:
        cached = None

    if cached is None:
        raise HTTPException(status_code=404, detail="no cached report for this hash")

    return AnalysisReport.model_validate(cached)


@app.get("/v1/analyze/{job_id}", response_model=AnalysisReport)
def get_report(job_id: str) -> AnalysisReport:
    report = _JOBS.get(job_id)
    if report is None:
        raise HTTPException(status_code=404, detail="unknown job_id")

    if datetime.fromisoformat(report.ttl_expires_at) <= datetime.now(UTC):
        _JOBS.pop(job_id, None)
        raise HTTPException(status_code=410, detail="report expired and was deleted")

    return report


@app.get("/artifacts/{filename}")
def get_artifact(filename: str) -> FileResponse:
    settings = get_settings()

    # Resolve and confirm containment so a crafted filename can't escape the dir.
    path = (settings.artifact_dir / filename).resolve()
    if not path.is_file() or settings.artifact_dir.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="unknown artifact")

    return FileResponse(path)
