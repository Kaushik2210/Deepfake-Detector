"""Weighted fusion of stream scores, with a provenance override path.

Three rules, in order of precedence.

1. **Provenance overrides statistics.** Cryptographic and recorded facts beat
   inference from pixels. A generator that names itself in metadata floors the
   score; valid Content Credentials from a signer clamp it. Neither is treated as
   conclusive on its own — the floor and clamp leave the score inside a band that
   still says "review this", because metadata is removable and a signature
   attests to a signing chain rather than to the content's truthfulness.

2. **Weighted average of the rest**, using weights fitted from validation AUC and
   loaded from calibration.json. If that file has no fitted weights, fusion falls
   back to the single highest-weighted available stream rather than inventing a
   weighting — an unfitted product should behave conservatively, not guess.

3. **Disagreement widens uncertainty.** When streams disagree the result is less
   trustworthy than either stream alone suggests, so the spread across streams
   feeds the reported interval. This finally replaces the test-time-augmentation
   proxy Phase 1 had to use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np


@dataclass
class StreamInput:
    name: str
    score: float
    available: bool = True


@dataclass
class FusionResult:
    score: float
    disagreement: float
    weights_used: dict[str, float]
    notes: list[str] = field(default_factory=list)
    override_applied: str | None = None


def _calibration_path() -> Path:
    here = Path(__file__).resolve()
    return here.parents[4] / "packages" / "core" / "src" / "calibration.json"


@lru_cache(maxsize=1)
def load_calibration() -> dict:
    path = _calibration_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def stream_weights() -> dict[str, float]:
    weights = load_calibration().get("stream_weights") or {}
    return {k: float(v) for k, v in weights.items() if isinstance(v, (int, float))}


def temperatures() -> dict[str, float]:
    values = load_calibration().get("temperature") or {}
    return {k: float(v) for k, v in values.items() if isinstance(v, (int, float))}


def apply_temperature(score: float, temperature: float) -> float:
    """Soften or sharpen a probability without changing its ranking."""
    if temperature <= 0:
        return score
    eps = 1e-6
    p = min(max(score, eps), 1.0 - eps)
    logit = np.log(p / (1.0 - p)) / temperature
    return float(1.0 / (1.0 + np.exp(-logit)))


def calibrate_stream(name: str, score: float) -> tuple[float, bool]:
    """Apply the fitted temperature for a stream, if one exists."""
    temperature = temperatures().get(name)
    if temperature is None:
        return score, False
    return apply_temperature(score, temperature), True


# A generator that names itself is strong evidence, but metadata is removable and
# can be forged, so this floors rather than saturates the score.
_GENERATOR_FLOOR = 0.88

# Valid Content Credentials attest to a signing chain, not to the content being
# unmanipulated, so this clamps rather than zeroing the score.
_C2PA_VALID_CLAMP = 0.35


def fuse(
    streams: list[StreamInput],
    generator_marker: str | None = None,
    c2pa_valid: bool = False,
    c2pa_signer: str | None = None,
) -> FusionResult:
    available = [s for s in streams if s.available]
    notes: list[str] = []

    weights = stream_weights()
    used: dict[str, float] = {}

    if not available:
        return FusionResult(
            score=0.5,
            disagreement=0.0,
            weights_used={},
            notes=["No stream could be scored, so the result is uninformative."],
        )

    applicable = {s.name: weights.get(s.name, 0.0) for s in available}
    total = sum(applicable.values())

    if total <= 0:
        # No fitted weights cover the available streams. Fall back to the single
        # stream rather than averaging with made-up weights.
        chosen = max(available, key=lambda s: s.score)
        used = {chosen.name: 1.0}
        fused = chosen.score
        notes.append(
            "No validation-derived fusion weights are available for these streams, so "
            f"the score comes from '{chosen.name}' alone rather than an invented "
            "weighting. Run the eval harness to fit weights."
        )
        disagreement = 0.0
    else:
        used = {name: w / total for name, w in applicable.items() if w > 0}
        fused = sum(s.score * used.get(s.name, 0.0) for s in available)

        contributing = [s.score for s in available if used.get(s.name, 0.0) > 0]
        disagreement = float(np.std(contributing)) if len(contributing) > 1 else 0.0

        if len(contributing) > 1:
            notes.append(
                "Streams were combined using weights derived from their measured "
                "validation AUC. Their spread of "
                f"{disagreement:.3f} widens the reported range."
            )

    override: str | None = None

    if generator_marker:
        if fused < _GENERATOR_FLOOR:
            fused = _GENERATOR_FLOOR
            override = "generator_metadata"
            notes.append(
                f"Metadata names {generator_marker} as the source, which raises the "
                "score above what the pixel-based streams alone reported. Such "
                "metadata is easily removed, so its presence is meaningful while its "
                "absence proves nothing."
            )

    elif c2pa_valid:
        if fused > _C2PA_VALID_CLAMP:
            fused = _C2PA_VALID_CLAMP
            override = "c2pa_valid"
            signer = c2pa_signer or "an identified signer"
            notes.append(
                f"Valid Content Credentials from {signer} lower this score below what "
                "the statistical streams reported. The signature attests to the "
                "signing chain, not to the content being unaltered before signing, so "
                "the score is reduced rather than cleared."
            )

    return FusionResult(
        score=float(np.clip(fused, 0.0, 1.0)),
        disagreement=disagreement,
        weights_used=used,
        notes=notes,
        override_applied=override,
    )
