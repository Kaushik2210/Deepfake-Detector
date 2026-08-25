"""Video decoding and frame sampling.

Two different sampling densities exist because they serve different needs.

The expensive per-frame analysis (Stream A's ViT+TTA, Stream B's frequency
stats, Grad-CAM) can only afford a small, capped number of frames on this
CPU-only service, so those get a *sparse* set chosen by uniform-with-
scene-change-bias sampling: divide the clip into equal time buckets and, within
each, prefer whichever candidate frame differs most from the previously
selected one. In a static clip this degenerates to plain uniform sampling; in a
high-motion clip it biases toward the frames most likely to show a cut or a
manipulation boundary.

Stream C's biological signals (rPPG, blink rate, optical flow) need temporally
*dense*, evenly-spaced frames to resolve a periodic signal at all. A sparse
24-frame sample over a 60 s clip is roughly one frame every 2.5 seconds, far
below the ~8 Hz the Nyquist criterion needs to resolve a 0.7-4 Hz pulse. So a
second, cheap (decode-only, no model) contiguous window is read separately.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class VideoDecodeError(ValueError):
    """Raised when the uploaded bytes are not a decodable video."""


@dataclass(frozen=True)
class VideoInfo:
    fps: float
    frame_count: int
    duration_seconds: float
    width: int
    height: int


@dataclass(frozen=True)
class SampledFrame:
    index: int  # 1-based ordinal among the sampled set
    frame_number: int  # position in the source video
    timestamp: float  # seconds
    image_bgr: np.ndarray


def probe(cap: cv2.VideoCapture) -> VideoInfo:
    # An unopened or invalid capture reports -1 from these, not 0 -- `or 0`
    # alone would not catch that, since -1 is truthy, so each is clamped.
    fps = max(0.0, float(cap.get(cv2.CAP_PROP_FPS) or 0.0))
    frame_count = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0))
    width = max(0, int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0))
    height = max(0, int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0))
    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
    return VideoInfo(
        fps=fps, frame_count=frame_count, duration_seconds=duration,
        width=width, height=height,
    )


def open_video(raw: bytes) -> tuple[cv2.VideoCapture, VideoInfo, Path]:
    """Write bytes to a temp file and open it.

    ``cv2.VideoCapture`` needs a real path for its FFmpeg backend to reliably
    identify the container on Windows; an in-memory buffer is not a supported
    input here. The caller is responsible for releasing the capture and
    deleting the returned path (see ``close_video``).
    """
    fd, tmp_path_str = tempfile.mkstemp(suffix=".bin")
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)

        cap = cv2.VideoCapture(str(tmp_path))
        if not cap.isOpened():
            cap.release()
            tmp_path.unlink(missing_ok=True)
            raise VideoDecodeError("could not open the uploaded bytes as a video")

        info = probe(cap)
        if info.frame_count <= 0 or info.fps <= 0:
            cap.release()
            tmp_path.unlink(missing_ok=True)
            raise VideoDecodeError(
                "video container has no readable frame count or frame rate"
            )

        return cap, info, tmp_path
    except VideoDecodeError:
        raise
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise VideoDecodeError(f"could not open video: {exc}") from exc


def close_video(cap: cv2.VideoCapture, tmp_path: Path) -> None:
    cap.release()
    tmp_path.unlink(missing_ok=True)


def _read_at(cap: cv2.VideoCapture, position: int) -> np.ndarray | None:
    cap.set(cv2.CAP_PROP_POS_FRAMES, position)
    ok, frame = cap.read()
    return frame if ok else None


def sample_sparse_frames(
    cap: cv2.VideoCapture, info: VideoInfo, target_count: int, candidates_per_bucket: int = 3
) -> list[SampledFrame]:
    """Uniform time buckets, adaptive pick within each bucket by scene change."""
    total = info.frame_count
    if total <= 0:
        return []

    if total <= target_count:
        frames: list[SampledFrame] = []
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        for position in range(total):
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(
                SampledFrame(
                    index=len(frames) + 1,
                    frame_number=position,
                    timestamp=position / info.fps,
                    image_bgr=frame,
                )
            )
        return frames

    edges = np.linspace(0, total, target_count + 1).astype(int)
    selected: list[SampledFrame] = []
    prev_gray: np.ndarray | None = None

    for bucket in range(target_count):
        low, high = int(edges[bucket]), int(edges[bucket + 1])
        if high <= low:
            high = low + 1
        candidates = sorted(
            {
                int(p)
                for p in np.linspace(low, max(low, high - 1), candidates_per_bucket)
                if p < total
            }
        )

        best: tuple[int, np.ndarray, np.ndarray] | None = None
        best_score = -1.0

        for position in candidates:
            frame = _read_at(cap, position)
            if frame is None:
                continue
            gray = cv2.cvtColor(cv2.resize(frame, (64, 64)), cv2.COLOR_BGR2GRAY)
            score = (
                0.0
                if prev_gray is None
                else float(np.abs(gray.astype(np.int16) - prev_gray.astype(np.int16)).mean())
            )
            if score > best_score:
                best_score = score
                best = (position, frame, gray)

        if best is None:
            continue

        position, frame, gray = best
        prev_gray = gray
        selected.append(
            SampledFrame(
                index=len(selected) + 1,
                frame_number=position,
                timestamp=position / info.fps,
                image_bgr=frame,
            )
        )

    return selected


def sample_dense_window(
    cap: cv2.VideoCapture,
    info: VideoInfo,
    max_seconds: float,
    target_fps: float,
    max_frames: int,
) -> list[SampledFrame]:
    """A contiguous, evenly-spaced window centred in the clip.

    Centred rather than starting from frame zero, since intros and outros are
    disproportionately likely to contain title cards, transitions, or a face not
    yet in frame.
    """
    if info.fps <= 0 or info.frame_count <= 0:
        return []

    window_seconds = min(max_seconds, info.duration_seconds)
    window_frames = max(1, int(round(window_seconds * info.fps)))

    center = info.frame_count // 2
    start = max(0, center - window_frames // 2)
    end = min(info.frame_count, start + window_frames)

    stride = max(1, round(info.fps / target_fps)) if target_fps > 0 else 1
    positions = list(range(start, end, stride))[:max_frames]

    frames: list[SampledFrame] = []
    for position in positions:
        frame = _read_at(cap, position)
        if frame is None:
            continue
        frames.append(
            SampledFrame(
                index=len(frames) + 1,
                frame_number=position,
                timestamp=position / info.fps,
                image_bgr=frame,
            )
        )

    return frames
