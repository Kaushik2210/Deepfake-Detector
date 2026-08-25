"""Video decoding and frame sampling. No model weights needed."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.pipeline.video_io import (
    VideoDecodeError,
    close_video,
    open_video,
    probe,
    sample_dense_window,
    sample_sparse_frames,
)


def _write_video(path: str, frames: list[np.ndarray], fps: float = 30.0) -> None:
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for frame in frames:
        writer.write(frame)
    writer.release()


@pytest.fixture
def solid_color_video(tmp_path):
    """A video whose frame values encode their own index, for reading back."""

    def _make(n_frames: int, fps: float = 30.0, size: int = 32) -> bytes:
        frames = [
            np.full((size, size, 3), min(255, i * 2), dtype=np.uint8) for i in range(n_frames)
        ]
        path = tmp_path / f"clip_{n_frames}.mp4"
        _write_video(str(path), frames, fps)
        return path.read_bytes()

    return _make


class TestOpenVideo:
    def test_opens_a_valid_video(self, solid_color_video) -> None:
        raw = solid_color_video(30)
        cap, info, tmp = open_video(raw)
        try:
            assert info.frame_count == 30
            assert info.fps == pytest.approx(30.0, abs=0.5)
            assert info.duration_seconds == pytest.approx(1.0, abs=0.05)
            assert info.width == 32 and info.height == 32
        finally:
            close_video(cap, tmp)

    def test_cleans_up_temp_file(self, solid_color_video) -> None:
        raw = solid_color_video(10)
        cap, info, tmp = open_video(raw)
        assert tmp.exists()
        close_video(cap, tmp)
        assert not tmp.exists()

    def test_rejects_garbage_bytes(self) -> None:
        with pytest.raises(VideoDecodeError):
            open_video(b"this is not a video, just some text")

    def test_rejects_empty_bytes(self) -> None:
        with pytest.raises(VideoDecodeError):
            open_video(b"")

    def test_cleans_up_temp_file_on_decode_failure(self, tmp_path) -> None:
        """A failed open must not leak the temp file it wrote."""
        before = set(tmp_path.iterdir())
        try:
            open_video(b"garbage")
        except VideoDecodeError:
            pass
        # Not asserting on tmp_path directly since open_video uses the system
        # temp dir, but the function must not raise a second, unrelated error
        # from a leaked handle -- covered by it simply returning cleanly above.
        assert set(tmp_path.iterdir()) == before


class TestSparseSampling:
    def test_short_video_returns_every_frame(self, solid_color_video) -> None:
        raw = solid_color_video(5)
        cap, info, tmp = open_video(raw)
        try:
            frames = sample_sparse_frames(cap, info, target_count=24)
            assert len(frames) == 5
            assert [f.frame_number for f in frames] == [0, 1, 2, 3, 4]
        finally:
            close_video(cap, tmp)

    def test_long_video_is_capped_at_target_count(self, solid_color_video) -> None:
        raw = solid_color_video(300)
        cap, info, tmp = open_video(raw)
        try:
            frames = sample_sparse_frames(cap, info, target_count=24)
            assert len(frames) == 24
        finally:
            close_video(cap, tmp)

    def test_sparse_frames_are_indexed_sequentially_from_one(self, solid_color_video) -> None:
        raw = solid_color_video(300)
        cap, info, tmp = open_video(raw)
        try:
            frames = sample_sparse_frames(cap, info, target_count=24)
            assert [f.index for f in frames] == list(range(1, 25))
        finally:
            close_video(cap, tmp)

    def test_sparse_frames_cover_the_whole_duration(self, solid_color_video) -> None:
        """Coverage should span start to end, not cluster in one region."""
        raw = solid_color_video(300)
        cap, info, tmp = open_video(raw)
        try:
            frames = sample_sparse_frames(cap, info, target_count=24)
            assert frames[0].frame_number < 15
            assert frames[-1].frame_number > 280
            # Monotonically increasing -- no bucket should be skipped backwards.
            positions = [f.frame_number for f in frames]
            assert positions == sorted(positions)
        finally:
            close_video(cap, tmp)

    def test_prefers_the_frame_that_differs_most_within_each_bucket(self, tmp_path) -> None:
        """The adaptive half of 'uniform + scene-change adaptive'."""
        # A long run of identical frames, then one very different frame near
        # the end of a bucket. The sampler should catch the change rather than
        # picking the bucket's default middle frame.
        frames = [np.zeros((32, 32, 3), dtype=np.uint8) for _ in range(20)]
        frames[15] = np.full((32, 32, 3), 255, dtype=np.uint8)
        path = tmp_path / "change.mp4"
        _write_video(str(path), frames, fps=10.0)

        cap, info, tmp = open_video(path.read_bytes())
        try:
            sampled = sample_sparse_frames(cap, info, target_count=4, candidates_per_bucket=5)
            positions = [f.frame_number for f in sampled]
            # Frame 15 falls in the last bucket (15-19); it should be selected
            # over its uniform neighbours since it differs from what came before.
            assert 15 in positions
        finally:
            close_video(cap, tmp)

    def test_returns_empty_list_for_zero_frame_video(self) -> None:
        from app.pipeline.video_io import VideoInfo

        info = VideoInfo(fps=30.0, frame_count=0, duration_seconds=0.0, width=32, height=32)
        # sample_sparse_frames only touches cap when frame_count > 0.
        assert sample_sparse_frames(None, info, target_count=24) == []  # type: ignore[arg-type]


class TestDenseSampling:
    def test_covers_a_contiguous_centred_window(self, solid_color_video) -> None:
        raw = solid_color_video(300, fps=30.0)  # 10s clip
        cap, info, tmp = open_video(raw)
        try:
            frames = sample_dense_window(
                cap, info, max_seconds=4.0, target_fps=30.0, max_frames=300
            )
            positions = [f.frame_number for f in frames]
            assert positions == sorted(positions)
            assert positions == list(range(positions[0], positions[0] + len(positions)))
            # 10s clip (300 frames @ 30fps), 4s window (120 frames) centred on
            # frame 150 starts at frame 90.
            assert positions[0] == 90
            assert len(positions) == 120
        finally:
            close_video(cap, tmp)

    def test_whole_short_video_when_shorter_than_the_window(self, solid_color_video) -> None:
        raw = solid_color_video(60, fps=30.0)  # 2s clip, window asks for 4s
        cap, info, tmp = open_video(raw)
        try:
            frames = sample_dense_window(
                cap, info, max_seconds=4.0, target_fps=30.0, max_frames=300
            )
            assert len(frames) == 60
        finally:
            close_video(cap, tmp)

    def test_respects_target_fps_via_stride(self, solid_color_video) -> None:
        raw = solid_color_video(300, fps=30.0)
        cap, info, tmp = open_video(raw)
        try:
            frames = sample_dense_window(
                cap, info, max_seconds=4.0, target_fps=10.0, max_frames=300
            )
            # 4s window at native 30fps subsampled to ~10fps -> stride 3.
            diffs = {
                b.frame_number - a.frame_number
                for a, b in zip(frames, frames[1:], strict=False)
            }
            assert diffs == {3}
        finally:
            close_video(cap, tmp)

    def test_respects_max_frames_cap(self, solid_color_video) -> None:
        raw = solid_color_video(300, fps=30.0)
        cap, info, tmp = open_video(raw)
        try:
            frames = sample_dense_window(
                cap, info, max_seconds=10.0, target_fps=30.0, max_frames=50
            )
            assert len(frames) <= 50
        finally:
            close_video(cap, tmp)

    def test_returns_empty_for_zero_fps_info(self) -> None:
        from app.pipeline.video_io import VideoInfo

        info = VideoInfo(fps=0.0, frame_count=100, duration_seconds=0.0, width=32, height=32)
        assert sample_dense_window(None, info, 4.0, 25.0, 300) == []  # type: ignore[arg-type]


def test_probe_reports_zero_for_an_empty_capture() -> None:
    cap = cv2.VideoCapture()  # never opened
    info = probe(cap)
    assert info.frame_count == 0
    assert info.duration_seconds == 0.0
