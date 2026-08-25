"""Facial landmarks, blink signal, and head pose via MediaPipe FaceLandmarker.

MediaPipe is Apache-2.0 and the ``face_landmarker`` model bundle is Google's own,
published under the same terms — see LICENSES.md. It was chosen for Stream C for
the same reason YuNet was chosen for face detection in Phase 1: no commercial-use
restriction, unlike several alternatives considered for other streams.

Two things this model gives directly, rather than needing to be hand-derived:

- **Blink signal** comes from the ``eyeBlinkLeft``/``eyeBlinkRight`` blendshape
  scores, a trained regression, rather than a hand-rolled eye-aspect-ratio
  heuristic computed from raw landmark geometry.
- **Head pose** comes from the returned facial transformation matrix, a rigid
  transform already fitted by the model's own 3D face geometry, rather than a
  separate solvePnP fit against a generic face model.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)

from app.config import get_settings

_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
_MODEL_FILENAME = "face_landmarker.task"

# Standard six-point eye-corner loops from the canonical 478-point MediaPipe face
# mesh topology, used only to place forehead/cheek ROIs -- not for the blink
# signal itself, which comes from blendshapes above.
_LEFT_EYE_IDX = (33, 160, 158, 133, 153, 144)
_RIGHT_EYE_IDX = (362, 385, 387, 263, 373, 380)
_MOUTH_IDX = (61, 291, 13, 14)  # left corner, right corner, upper lip, lower lip


@dataclass(frozen=True)
class FaceRegion:
    """A skin patch used for rPPG, as a pixel-space bounding box."""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def valid(self) -> bool:
        return self.x1 > self.x0 and self.y1 > self.y0


@dataclass(frozen=True)
class LandmarkFrame:
    """One frame's landmark result."""

    points_px: np.ndarray  # (478, 2) float, pixel coordinates
    blink_left: float  # 0 = open, 1 = fully closed
    blink_right: float
    pose_euler_deg: tuple[float, float, float]  # pitch, yaw, roll
    forehead: FaceRegion
    left_cheek: FaceRegion
    right_cheek: FaceRegion


def ensure_landmarker_model() -> Path:
    settings = get_settings()
    dest = settings.model_cache_dir / _MODEL_FILENAME

    if dest.is_file() and dest.stat().st_size > 0:
        return dest

    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(_MODEL_URL, tmp)  # noqa: S310 - fixed URL
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)

    return dest


@lru_cache(maxsize=1)
def _get_landmarker() -> FaceLandmarker:
    options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(ensure_landmarker_model())),
        running_mode=RunningMode.IMAGE,
        num_faces=1,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
    )
    return FaceLandmarker.create_from_options(options)


def _rotation_matrix_to_euler_deg(rotation: np.ndarray) -> tuple[float, float, float]:
    """Pitch, yaw, roll in degrees from a 3x3 rotation matrix (XYZ convention)."""
    sy = float(np.sqrt(rotation[0, 0] ** 2 + rotation[1, 0] ** 2))
    singular = sy < 1e-6

    if not singular:
        pitch = np.arctan2(rotation[2, 1], rotation[2, 2])
        yaw = np.arctan2(-rotation[2, 0], sy)
        roll = np.arctan2(rotation[1, 0], rotation[0, 0])
    else:
        pitch = np.arctan2(-rotation[1, 2], rotation[1, 1])
        yaw = np.arctan2(-rotation[2, 0], sy)
        roll = 0.0

    return tuple(float(np.degrees(a)) for a in (pitch, yaw, roll))


def _region_from_points(points: np.ndarray, indices: tuple[int, ...]) -> tuple[float, float]:
    """Mean (x, y) of a landmark subset, in pixel coordinates."""
    subset = points[list(indices)]
    return float(subset[:, 0].mean()), float(subset[:, 1].mean())


def _skin_regions(
    points_px: np.ndarray, width: int, height: int
) -> tuple[FaceRegion, FaceRegion, FaceRegion]:
    """Forehead and cheek ROIs, placed geometrically from a few stable anchors.

    Rather than trusting a hand-picked list of "forehead landmark" indices
    against the full 478-point topology -- easy to get subtly wrong -- these are
    placed relative to eye and mouth position, which only needs the eye/mouth
    index sets above to be roughly right. The ROI only needs to land on skin away
    from eyes and mouth, not be pixel-perfect.

    The forehead box is anchored to eye position and overall face height rather
    than the topmost mesh point, since low headwear can otherwise pull it onto a
    brim instead of skin. That still fails on caps with a low brim close to the
    eyebrows -- verified against a real photo -- so rPPG combines this with both
    cheek ROIs rather than depending on it alone; see temporal.py.
    """
    x_min, y_min = points_px[:, 0].min(), points_px[:, 1].min()
    x_max, y_max = points_px[:, 0].max(), points_px[:, 1].max()
    face_w = max(x_max - x_min, 1.0)
    face_h = max(y_max - y_min, 1.0)

    _, left_eye_y = _region_from_points(points_px, _LEFT_EYE_IDX)
    _, right_eye_y = _region_from_points(points_px, _RIGHT_EYE_IDX)
    eye_y = (left_eye_y + right_eye_y) / 2.0
    left_eye_x, _ = _region_from_points(points_px, _LEFT_EYE_IDX)
    right_eye_x, _ = _region_from_points(points_px, _RIGHT_EYE_IDX)
    _, mouth_y = _region_from_points(points_px, _MOUTH_IDX)

    center_x = (x_min + x_max) / 2.0

    forehead = FaceRegion(
        x0=int(center_x - 0.20 * face_w),
        y0=int(eye_y - 0.24 * face_h),
        x1=int(center_x + 0.20 * face_w),
        y1=int(eye_y - 0.06 * face_h),
    )

    cheek_y0 = eye_y + 0.15 * (mouth_y - eye_y)
    cheek_y1 = mouth_y - 0.10 * (mouth_y - eye_y)

    left_cheek = FaceRegion(
        x0=int(x_min + 0.05 * face_w),
        y0=int(cheek_y0),
        x1=int(min(left_eye_x, right_eye_x) - 0.05 * face_w),
        y1=int(cheek_y1),
    )
    right_cheek = FaceRegion(
        x0=int(max(left_eye_x, right_eye_x) + 0.05 * face_w),
        y0=int(cheek_y0),
        x1=int(x_max - 0.05 * face_w),
        y1=int(cheek_y1),
    )

    def _clip(region: FaceRegion) -> FaceRegion:
        return FaceRegion(
            x0=max(0, min(region.x0, width - 1)),
            y0=max(0, min(region.y0, height - 1)),
            x1=max(0, min(region.x1, width)),
            y1=max(0, min(region.y1, height)),
        )

    return _clip(forehead), _clip(left_cheek), _clip(right_cheek)


def detect(frame_bgr: np.ndarray) -> LandmarkFrame | None:
    """Run landmark detection on one frame. Returns None if no face is found."""
    landmarker = _get_landmarker()
    height, width = frame_bgr.shape[:2]

    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect(mp_image)

    if not result.face_landmarks:
        return None

    landmarks = result.face_landmarks[0]
    points_px = np.array(
        [(lm.x * width, lm.y * height) for lm in landmarks], dtype=np.float64
    )

    blink_left = blink_right = 0.0
    if result.face_blendshapes:
        for category in result.face_blendshapes[0]:
            if category.category_name == "eyeBlinkLeft":
                blink_left = float(category.score)
            elif category.category_name == "eyeBlinkRight":
                blink_right = float(category.score)

    pose = (0.0, 0.0, 0.0)
    if result.facial_transformation_matrixes:
        matrix = np.array(result.facial_transformation_matrixes[0])
        pose = _rotation_matrix_to_euler_deg(matrix[:3, :3])

    forehead, left_cheek, right_cheek = _skin_regions(points_px, width, height)

    return LandmarkFrame(
        points_px=points_px,
        blink_left=blink_left,
        blink_right=blink_right,
        pose_euler_deg=pose,
        forehead=forehead,
        left_cheek=left_cheek,
        right_cheek=right_cheek,
    )
