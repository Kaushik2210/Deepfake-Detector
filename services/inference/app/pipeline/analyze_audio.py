"""Audio analysis orchestrator: bytes in, AnalysisReport out.

Structurally the audio counterpart of analyze_image, but simpler: one stream
(no frequency/provenance/temporal analogue exists for audio yet), no per-item
findings (there is no "face" unit here -- see AnalysisReportSchema's own
comment that ``faces`` is empty "for media where faces are not the unit of
analysis"), so this mirrors analyze_image's own no-face fallback path rather
than its per-face loop.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.bands import report_footer_disclaimer, score_to_band
from app.config import get_settings
from app.models.audio_registry import get_audio_model, score_waveform
from app.pipeline import audio_envelope
from app.pipeline import fusion as fusion_mod
from app.pipeline.audio_io import decode_audio, prepare_for_model
from app.pipeline.audio_spectrogram import render_spectrogram
from app.schemas import (
    AnalysisReport,
    Envelope,
    EnvelopeFactors,
    EnvelopePenalty,
    MediaMeta,
    NoteArtifact,
    Provenance,
    SpectrumPlotArtifact,
    StreamResult,
)


class AudioTooLongError(ValueError):
    """Raised when audio exceeds the configured duration limit."""


def _apply_confidence(raw_score: float, confidence: float) -> float:
    """Shrink toward 0.5 in proportion to how much the envelope penalises this input."""
    return 0.5 + (raw_score - 0.5) * confidence


def _uncertainty_band(score: float, confidence: float) -> tuple[float, float]:
    """Widen a point score into an interval from how far outside the envelope it sits.

    There is only one stream, so there is no cross-stream disagreement to widen
    with the way the fused image/video score has -- the envelope confidence is
    the only uncertainty source available here.
    """
    half_width = (1.0 - confidence) * 0.5
    return (
        round(max(0.0, score - half_width), 4),
        round(min(1.0, score + half_width), 4),
    )


def analyze_audio(
    raw: bytes,
    filename: str | None = None,
    mime_type: str = "application/octet-stream",
    job_id: str | None = None,
) -> AnalysisReport:
    settings = get_settings()
    job_id = job_id or uuid.uuid4().hex

    waveform, sample_rate = decode_audio(raw)
    duration_seconds = waveform.shape[0] / sample_rate

    if duration_seconds > settings.max_audio_duration_seconds:
        raise AudioTooLongError(
            f"audio is {duration_seconds:.1f}s, longer than the "
            f"{settings.max_audio_duration_seconds:.0f}s limit"
        )

    assessment = audio_envelope.assess(waveform, sample_rate, duration_seconds)
    confidence = assessment.confidence

    audio_model = get_audio_model()
    model_versions = {"audio": audio_model.version_string}

    model_input = prepare_for_model(
        waveform, sample_rate, settings.audio_target_sample_rate, settings.audio_target_samples
    )
    raw_score = round(score_waveform(audio_model, model_input), 4)

    weight = fusion_mod.stream_weights().get("audio", 1.0)

    spectrogram_path = render_spectrogram(waveform, sample_rate, settings.artifact_dir)

    artifacts = [
        SpectrumPlotArtifact(
            label="Spectrogram (magnitude, dB)",
            url=f"{settings.artifact_base_url}/{spectrogram_path.name}",
        ),
        NoteArtifact(
            label="Model",
            detail=(
                f"AASIST graph-attention anti-spoofing network, trained on ASVspoof2019 "
                f"LA. Raw spoof probability: {raw_score}."
            ),
        ),
    ]

    streams = [
        StreamResult(
            name="audio",
            score=raw_score,
            weight=round(weight, 4),
            models=[audio_model.version_string],
            artifacts=artifacts,
        )
    ]

    score = round(min(1.0, max(0.0, _apply_confidence(raw_score, confidence))), 4)
    lo, hi = _uncertainty_band(score, confidence)

    now = datetime.now(UTC)

    return AnalysisReport(
        job_id=job_id,
        score=score,
        band=score_to_band(score).id,  # type: ignore[arg-type]
        uncertainty=(lo, hi),
        streams=streams,
        faces=[],
        conclusion=None,
        envelope=Envelope(
            in_distribution=assessment.in_distribution,
            penalties=[
                EnvelopePenalty(reason=reason, factor=factor)
                for reason, factor in assessment.penalties
            ],
            factors_checked=EnvelopeFactors(**assessment.factors),
        ),
        provenance=Provenance(),
        media_meta=MediaMeta(
            kind="audio",
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(raw),
            duration_seconds=round(duration_seconds, 3),
        ),
        model_versions=model_versions,
        processed_at=now.isoformat(),
        ttl_expires_at=(now + timedelta(hours=settings.media_ttl_hours)).isoformat(),
        disclaimer=report_footer_disclaimer(),
    )
