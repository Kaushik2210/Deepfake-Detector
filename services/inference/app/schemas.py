"""Pydantic mirrors of the Zod schemas in ``packages/core/src/schemas``.

Both sides describe the same wire format. When you change one, change the other —
``tests/test_contract.py`` guards the field names against drift.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

MediaKind = Literal["image", "video", "audio"]
StreamName = Literal["spatial", "frequency", "temporal", "provenance", "audio"]
BandId = Literal["low", "weak", "mixed", "strong", "very_strong"]


class HeatmapArtifact(BaseModel):
    type: Literal["heatmap"] = "heatmap"
    label: str
    url: str


class TimelinePoint(BaseModel):
    t: float = Field(ge=0)
    score: float = Field(ge=0, le=1)


class TimelineArtifact(BaseModel):
    type: Literal["timeline"] = "timeline"
    label: str
    points: list[TimelinePoint]


class FaceMapArtifact(BaseModel):
    type: Literal["face_map"] = "face_map"
    label: str
    url: str


class SpectrumPlotArtifact(BaseModel):
    type: Literal["spectrum_plot"] = "spectrum_plot"
    label: str
    url: str


class NoteArtifact(BaseModel):
    type: Literal["note"] = "note"
    label: str
    detail: str


Artifact = Annotated[
    HeatmapArtifact | FaceMapArtifact | TimelineArtifact | SpectrumPlotArtifact | NoteArtifact,
    Field(discriminator="type"),
]


class StreamResult(BaseModel):
    name: StreamName
    score: float = Field(ge=0, le=1)
    weight: float = Field(ge=0, le=1)
    models: list[str]
    artifacts: list[Artifact]


class EnvelopePenalty(BaseModel):
    reason: str
    factor: float = Field(ge=0, le=1)


class EnvelopeFactors(BaseModel):
    resolution: str | None = None
    compression_estimate: str | None = None
    face_size: str | None = None
    blur: str | None = None
    illumination: str | None = None
    # Audio envelope factors.
    duration: str | None = None
    sample_rate: str | None = None
    clipping: str | None = None
    silence_ratio: str | None = None


class Envelope(BaseModel):
    in_distribution: bool
    penalties: list[EnvelopePenalty]
    factors_checked: EnvelopeFactors


class C2paInfo(BaseModel):
    present: bool
    valid: bool | None = None
    signer: str | None = None
    trusted_signer: bool | None = None


class Provenance(BaseModel):
    c2pa: C2paInfo | None = None
    exif_consistent: bool | None = None
    known_generator_watermark: str | None = None
    phash: str | None = None


class FaceBox(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class FaceFinding(BaseModel):
    """One analysed face, carrying its own band, interval and caveats.

    For a video, ``index`` is the sampled frame's ordinal and ``timestamp``
    locates it in the clip; for a still image ``timestamp`` stays None.
    """

    index: int = Field(gt=0)
    box: FaceBox
    score: float = Field(ge=0, le=1)
    band: BandId
    uncertainty: tuple[float, float]
    detector_confidence: float = Field(ge=0, le=1)
    penalties: list[EnvelopePenalty]
    heatmap_url: str | None = None
    timestamp: float | None = None


FacePattern = Literal[
    "none_elevated",
    "single_outlier",
    "several_elevated",
    "all_elevated",
    "single_face",
]


class Conclusion(BaseModel):
    headline: str
    detail: str
    next_steps: str
    pattern: FacePattern
    faces_analyzed: int = Field(ge=0)
    faces_elevated: int = Field(ge=0)


class MediaMeta(BaseModel):
    kind: MediaKind
    filename: str | None = None
    mime_type: str
    size_bytes: int = Field(ge=0)
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None


class AnalysisReport(BaseModel):
    job_id: str
    score: float = Field(ge=0, le=1)
    band: BandId
    uncertainty: tuple[float, float]
    streams: list[StreamResult]
    faces: list[FaceFinding] = Field(default_factory=list)
    conclusion: Conclusion | None = None
    envelope: Envelope
    provenance: Provenance
    media_meta: MediaMeta
    model_versions: dict[str, str]
    processed_at: str
    ttl_expires_at: str
    disclaimer: str


class AnalyzeJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "complete", "failed"]


class AnalyzeByHashRequest(BaseModel):
    # Exactly what phash() produces: 64 bits as lowercase hex. Validated here,
    # not left to hamming_distance() to discover, because this field comes
    # straight from an untrusted caller (the extension's own client-side hash
    # implementation) and a length mismatch there raises ValueError rather
    # than returning cleanly -- worth a 422 at the boundary, not a 500 from
    # inside the cache scan.
    phash: str = Field(pattern=r"^[0-9a-f]{16}$")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    model_versions: dict[str, str]
    models_loaded: bool
