"""Service configuration.

Every knob that affects a reported score lives here rather than being scattered
as literals through the pipeline, so the envelope thresholds we surface in the UI
are traceable to one place.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_SERVICE_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VERIFRAME_", extra="ignore")

    # --- Stream A: spatial classifier ---
    # Apache-2.0, ViTForImageClassification, id2label = {0: Realism, 1: Deepfake}.
    # See LICENSES.md. Pinning a revision keeps reported scores reproducible.
    spatial_model_id: str = "prithivMLmods/Deep-Fake-Detector-v2-Model"
    spatial_model_revision: str = "main"
    spatial_input_size: int = 224

    # --- Face detection (YuNet, MIT, shipped inside OpenCV) ---
    face_score_threshold: float = 0.6
    face_nms_threshold: float = 0.3
    face_top_k: int = 20
    max_faces_analyzed: int = 10

    # --- Envelope thresholds ---
    # Below this face height in pixels the crop is upsampled past what the model
    # saw in training, so we penalise confidence rather than pretending otherwise.
    min_face_px: int = 64
    # Laplacian variance below this reads as blurred.
    blur_threshold: float = 60.0
    # Mean luma outside this range reads as under/over-exposed.
    min_mean_luma: float = 40.0
    max_mean_luma: float = 215.0
    # JPEG quality estimate below this reads as heavily recompressed.
    min_jpeg_quality: int = 70

    # --- Video ---
    max_video_bytes: int = 100 * 1024 * 1024
    max_video_duration_seconds: float = 60.0

    # Expensive per-frame analysis (Stream A's ViT+TTA, Stream B's frequency
    # stats, Grad-CAM) can only afford a small capped sample on this CPU-only
    # service. Chosen so worst case stays under roughly a minute.
    video_sparse_frame_cap: int = 24
    video_sparse_heatmap_top_k: int = 3

    # Stream C's biological signals need temporally dense, evenly-spaced frames
    # to resolve a periodic signal at all -- the sparse sample above is far too
    # coarse. This is a second, separate, much cheaper (landmark-only) pass.
    video_dense_window_max_seconds: float = 12.0
    video_dense_window_target_fps: float = 25.0
    video_dense_window_max_frames: int = 300

    # rPPG needs enough samples to resolve a 0.7-4 Hz signal with usable
    # frequency resolution; below this the FFT bin width is too coarse to trust.
    video_min_dense_frames_for_rppg: int = 96
    # Below this, too little time has passed to expect even one blink cycle
    # (typical adult blink interval is 2-10s), so a rate estimate is not
    # trustworthy rather than "zero blinks observed."
    video_min_dense_frames_for_blink: int = 60

    # --- Paths ---
    model_cache_dir: Path = _SERVICE_ROOT / ".model_cache"
    artifact_dir: Path = _SERVICE_ROOT / ".artifacts"

    # Artifact URLs are absolute because the report schema requires absolute URLs
    # and the web app and extension fetch them cross-origin.
    public_base_url: str = "http://localhost:8000"

    @property
    def artifact_base_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/artifacts"

    # --- Retention ---
    media_ttl_hours: int = 24

    # --- Limits ---
    max_upload_bytes: int = 25 * 1024 * 1024

    def ensure_dirs(self) -> None:
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
