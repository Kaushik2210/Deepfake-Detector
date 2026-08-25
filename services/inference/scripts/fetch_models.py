"""Pre-download the model files the inference service needs.

Run this once after install so the first request (and the model-marked tests)
don't pay a download cost:

    python scripts/fetch_models.py

Weights are never committed to the repo — see .gitignore.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.pipeline.faces import ensure_yunet_model  # noqa: E402


def main() -> int:
    settings = get_settings()

    print(f"model cache: {settings.model_cache_dir}")

    print("fetching YuNet face detector ...")
    path = ensure_yunet_model()
    print(f"  -> {path} ({path.stat().st_size / 1024:.0f} KB)")

    print(f"fetching spatial classifier {settings.spatial_model_id} ...")
    from app.models.registry import get_spatial_model

    model = get_spatial_model()
    print(f"  -> loaded, revision {model.revision}")

    print("fetching audio anti-spoofing model (AASIST) ...")
    from app.models.audio_registry import ensure_aasist_checkpoint

    audio_path = ensure_aasist_checkpoint()
    print(f"  -> {audio_path} ({audio_path.stat().st_size / 1024:.0f} KB)")

    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
