"""Annotated overview of which faces were analysed.

A group-photo report is unreadable without a way to tell which finding refers to
which person. This draws numbered boxes on the source image, colour-coded by
band, and saves it as a derived artifact — so it survives the media TTL sweep
that deletes the original upload.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import numpy as np

from app.config import get_settings
from app.pipeline.faces import DetectedFace

# BGR, matching the band colours used in the web UI.
_BAND_COLOR: dict[str, tuple[int, int, int]] = {
    "low": (61, 128, 21),
    "weak": (13, 163, 101),
    "mixed": (4, 138, 202),
    "strong": (22, 101, 234),
    "very_strong": (28, 28, 185),
}
_DEFAULT_COLOR = (128, 128, 128)

# Keep the longest edge at this size so the annotation is legible without
# shipping a full-resolution copy of the upload.
_MAX_EDGE = 900


def generate_face_map(
    image_bgr: np.ndarray,
    faces: list[DetectedFace],
    bands: list[str],
    output_dir: Path | None = None,
) -> Path:
    """Draw numbered, band-coloured boxes over each analysed face."""
    settings = get_settings()
    output_dir = output_dir or settings.artifact_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    canvas = image_bgr.copy()
    height, width = canvas.shape[:2]

    scale = min(1.0, _MAX_EDGE / max(height, width))
    if scale < 1.0:
        canvas = cv2.resize(
            canvas, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA
        )

    # Line and text weight scale with image size so annotations stay readable
    # on both a 300px thumbnail and a 900px group shot.
    thickness = max(2, int(round(canvas.shape[1] / 400)))
    font_scale = max(0.5, canvas.shape[1] / 1100)

    for index, (face, band) in enumerate(zip(faces, bands, strict=True), start=1):
        color = _BAND_COLOR.get(band, _DEFAULT_COLOR)

        x0, y0 = int(face.x * scale), int(face.y * scale)
        x1, y1 = int((face.x + face.w) * scale), int((face.y + face.h) * scale)

        cv2.rectangle(canvas, (x0, y0), (x1, y1), color, thickness)

        label = str(index)
        (text_w, text_h), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
        )

        # Put the number inside the box when there is no room above it, so the
        # badge never falls off the top edge of the image.
        pad = max(3, thickness * 2)
        badge_h = text_h + baseline + pad
        badge_top = y0 - badge_h if y0 - badge_h >= 0 else y0
        badge_bottom = badge_top + badge_h

        cv2.rectangle(
            canvas,
            (x0, badge_top),
            (min(x0 + text_w + pad * 2, canvas.shape[1]), badge_bottom),
            color,
            -1,
        )
        cv2.putText(
            canvas,
            label,
            (x0 + pad, badge_bottom - baseline - pad // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    path = output_dir / f"facemap_{uuid.uuid4().hex}.png"
    cv2.imwrite(str(path), canvas)
    return path
