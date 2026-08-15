"""Score -> band mapping.

The band table itself lives in ``packages/core/src/bands.json`` and is shared with
the TypeScript side. This module reads that file rather than restating the
thresholds, so there is exactly one place a threshold can be changed.

Non-negotiable: never collapse a band into a binary FAKE/REAL verdict.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Band:
    id: str
    min: float
    max: float
    label: str
    copy: str


def _locate_bands_json() -> Path:
    """Find packages/core/src/bands.json.

    Explicit override wins, so the file can be copied next to the service in a
    container image where the monorepo layout isn't preserved.
    """
    override = os.environ.get("VERIFRAME_BANDS_JSON")
    if override:
        path = Path(override)
        if not path.is_file():
            raise FileNotFoundError(f"VERIFRAME_BANDS_JSON points at a missing file: {path}")
        return path

    here = Path(__file__).resolve()
    candidates = [
        # monorepo layout: services/inference/app/bands.py -> repo root
        here.parents[3] / "packages" / "core" / "src" / "bands.json",
        # container layout: bands.json copied alongside the app package
        here.parent / "bands.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise FileNotFoundError(
        "could not locate bands.json; set VERIFRAME_BANDS_JSON to its path. "
        f"Looked in: {', '.join(str(c) for c in candidates)}"
    )


@lru_cache(maxsize=1)
def _load() -> tuple[tuple[Band, ...], str]:
    data = json.loads(_locate_bands_json().read_text(encoding="utf-8"))
    bands = tuple(
        Band(id=b["id"], min=b["min"], max=b["max"], label=b["label"], copy=b["copy"])
        for b in data["bands"]
    )
    return bands, data["report_footer_disclaimer"]


def band_definitions() -> tuple[Band, ...]:
    return _load()[0]


def report_footer_disclaimer() -> str:
    return _load()[1]


def score_to_band(score: float) -> Band:
    """Map a calibrated score in [0, 1] to its band.

    Lower bounds are inclusive and upper bounds exclusive, except for the final
    band whose upper bound is inclusive. A score exactly on a boundary therefore
    lands in the higher band -- matching ``scoreToBand`` in packages/core.
    """
    if score != score or score < 0.0 or score > 1.0:  # NaN-safe range check
        raise ValueError(f"score must be a finite number in [0, 1], got {score!r}")

    bands = band_definitions()
    last_index = len(bands) - 1
    for i, band in enumerate(bands):
        upper_ok = score <= band.max if i == last_index else score < band.max
        if score >= band.min and upper_ok:
            return band

    raise ValueError(f"no band matched score {score!r}")
