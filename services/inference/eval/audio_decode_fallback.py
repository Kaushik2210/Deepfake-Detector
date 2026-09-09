"""Eval-only decode fallback via a locally-installed ffmpeg binary.

This exists because roughly half of ASVspoof2021 DF's files have genuine
frame-level bitstream defects (confirmed with `pyflac`, a strict reference
decoder: FRAME_CRC_MISMATCH / LOST_SYNC, not just a libsndfile compatibility
gap -- see DECISIONS.md, 2026-09-08) that `soundfile`/libsndfile refuses to
decode at all. ffmpeg's decoder is more error-tolerant and recovers them.

Deliberately NOT added to `app/pipeline/audio_io.py`, which the shipped
inference service also imports and which explicitly documents never
shelling out to system ffmpeg. This module:

- Is only ever imported by the eval harness, never by the service.
- Shells out to whatever `ffmpeg` binary is already installed on the
  machine running the eval -- it is not bundled, vendored, or added as a
  Python dependency, so this project neither distributes nor links against
  FFmpeg's code. Invoking an already-installed external program as a
  separate subprocess does not create a derivative work under the GPL the
  way statically linking its libraries (the `av`/PyAV approach rejected
  2026-09-08) would -- that is the entire reason this path is usable where
  that one was not.
- Degrades to "not available" if `ffmpeg` is not on PATH, rather than
  requiring it -- the eval harness still runs, just without recovering
  these files, exactly as it did before this module existed.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

from app.pipeline.audio_io import AudioDecodeError

_FFMPEG_PATH: str | None | bool = False  # False = not checked yet


def ffmpeg_available() -> bool:
    global _FFMPEG_PATH
    if _FFMPEG_PATH is False:
        _FFMPEG_PATH = shutil.which("ffmpeg")
    return _FFMPEG_PATH is not None


def decode_via_ffmpeg(raw: bytes) -> tuple[np.ndarray, int]:
    """Round-trip through ffmpeg to a clean WAV, then decode that normally.

    Raises AudioDecodeError if ffmpeg is unavailable or itself fails --
    callers should already have tried the primary decoder first and are
    calling this only as a fallback.
    """
    if not ffmpeg_available():
        raise AudioDecodeError("ffmpeg fallback requested but ffmpeg is not on PATH")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.flac"
        dst = Path(tmp) / "out.wav"
        src.write_bytes(raw)
        result = subprocess.run(
            [_FFMPEG_PATH, "-v", "error", "-y", "-i", str(src), "-f", "wav", str(dst)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0 or not dst.exists():
            raise AudioDecodeError(
                f"ffmpeg fallback failed: {result.stderr.decode(errors='replace')[:200]}"
            )
        waveform, sample_rate = sf.read(dst, dtype="float32", always_2d=True)

    if waveform.size == 0:
        raise AudioDecodeError("ffmpeg-decoded audio is empty")
    mono = waveform.mean(axis=1).astype(np.float32)
    return mono, int(sample_rate)
