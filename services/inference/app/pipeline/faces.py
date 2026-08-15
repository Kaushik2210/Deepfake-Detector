"""Face detection and cropping via YuNet.

YuNet is MIT-licensed and ships as a ~230 KB ONNX file in the OpenCV model zoo,
run through OpenCV's own ``cv2.FaceDetectorYN``. It was chosen over the two
detectors named in the original spec because both of those block commercial use:
Ultralytics YOLOv8-face is AGPL-3.0, and InsightFace's RetinaFace weights are
released for non-commercial research only. See LICENSES.md.
"""

from __future__ import annotations

import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.config import get_settings

# OpenCV 5.x needs the dynamic-input-shape build; 4.x needs the fixed-shape one.
_YUNET_VARIANTS = (
    ("face_detection_yunet_2026may.onnx", (5,)),
    ("face_detection_yunet_2023mar.onnx", (4,)),
)
_YUNET_BASE_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet"


@dataclass(frozen=True)
class DetectedFace:
    """A detected face in original-image pixel coordinates."""

    x: int
    y: int
    w: int
    h: int
    confidence: float

    @property
    def area(self) -> int:
        return self.w * self.h


def _yunet_filename() -> str:
    major = int(cv2.__version__.split(".")[0])
    for filename, majors in _YUNET_VARIANTS:
        if major in majors:
            return filename
    # Unknown OpenCV major: prefer the dynamic-shape build, which is the zoo default.
    return _YUNET_VARIANTS[0][0]


def ensure_yunet_model() -> Path:
    """Download the YuNet ONNX file into the model cache if it isn't there yet."""
    settings = get_settings()
    filename = _yunet_filename()
    dest = settings.model_cache_dir / filename

    if dest.is_file() and dest.stat().st_size > 0:
        return dest

    url = f"{_YUNET_BASE_URL}/{filename}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        urllib.request.urlretrieve(url, tmp)  # noqa: S310 - fixed, non-user-supplied URL
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)

    return dest


def detect_faces(image_bgr: np.ndarray) -> list[DetectedFace]:
    """Detect faces, largest first.

    Returns an empty list when nothing is found — callers must treat that as
    "no evidence available", not as "nothing suspicious".
    """
    settings = get_settings()
    height, width = image_bgr.shape[:2]

    detector = cv2.FaceDetectorYN.create(
        model=str(ensure_yunet_model()),
        config="",
        input_size=(width, height),
        score_threshold=settings.face_score_threshold,
        nms_threshold=settings.face_nms_threshold,
        top_k=settings.face_top_k,
    )
    detector.setInputSize((width, height))

    _, raw = detector.detect(image_bgr)
    if raw is None:
        return []

    faces: list[DetectedFace] = []
    for row in raw:
        x, y, w, h = (int(round(v)) for v in row[:4])
        # Clamp to image bounds; YuNet can return boxes that hang off the edge.
        x, y = max(0, x), max(0, y)
        w, h = min(w, width - x), min(h, height - y)
        if w <= 0 or h <= 0:
            continue
        faces.append(DetectedFace(x=x, y=y, w=w, h=h, confidence=float(row[-1])))

    faces.sort(key=lambda f: f.area, reverse=True)
    return faces[: settings.max_faces_analyzed]


def crop_face(image_bgr: np.ndarray, face: DetectedFace, margin: float = 0.25) -> np.ndarray:
    """Crop a face with a margin, since the classifier was trained on loose crops."""
    height, width = image_bgr.shape[:2]
    pad_x = int(face.w * margin)
    pad_y = int(face.h * margin)

    x0 = max(0, face.x - pad_x)
    y0 = max(0, face.y - pad_y)
    x1 = min(width, face.x + face.w + pad_x)
    y1 = min(height, face.y + face.h + pad_y)

    return image_bgr[y0:y1, x0:x1]
