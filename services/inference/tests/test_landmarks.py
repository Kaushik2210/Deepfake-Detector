"""MediaPipe FaceLandmarker wrapper. All model-marked: they download and run
the real face_landmarker.task bundle."""

from __future__ import annotations

import numpy as np
import pytest

from app.pipeline.landmarks import detect, ensure_landmarker_model

pytestmark = pytest.mark.model


def test_model_downloads_and_caches() -> None:
    path = ensure_landmarker_model()
    assert path.is_file()
    assert path.stat().st_size > 100_000  # a real model bundle, not a stub


def test_detects_478_landmarks_on_a_real_face(real_face_bgr: np.ndarray) -> None:
    result = detect(real_face_bgr)
    assert result is not None
    assert result.points_px.shape == (478, 2)


def test_landmark_points_land_within_the_image(real_face_bgr: np.ndarray) -> None:
    height, width = real_face_bgr.shape[:2]
    result = detect(real_face_bgr)
    assert result is not None
    # A generous margin: MediaPipe can estimate slightly outside the frame for
    # partially-cropped faces, but not wildly so for a well-framed portrait.
    margin = 0.2
    assert (result.points_px[:, 0] >= -margin * width).all()
    assert (result.points_px[:, 0] <= width * (1 + margin)).all()
    assert (result.points_px[:, 1] >= -margin * height).all()
    assert (result.points_px[:, 1] <= height * (1 + margin)).all()


def test_blink_scores_are_in_unit_range(real_face_bgr: np.ndarray) -> None:
    result = detect(real_face_bgr)
    assert result is not None
    assert 0.0 <= result.blink_left <= 1.0
    assert 0.0 <= result.blink_right <= 1.0


def test_open_eyes_score_as_mostly_open(real_face_bgr: np.ndarray) -> None:
    """The fixture photo has open eyes; the blink score should reflect that."""
    result = detect(real_face_bgr)
    assert result is not None
    assert result.blink_left < 0.5
    assert result.blink_right < 0.5


def test_pose_is_three_finite_angles(real_face_bgr: np.ndarray) -> None:
    result = detect(real_face_bgr)
    assert result is not None
    assert len(result.pose_euler_deg) == 3
    assert all(np.isfinite(a) for a in result.pose_euler_deg)


def test_returns_none_for_an_image_with_no_face(no_face_bgr: np.ndarray) -> None:
    assert detect(no_face_bgr) is None


class TestSkinRegions:
    def test_all_three_regions_are_valid_and_within_bounds(self, real_face_bgr: np.ndarray) -> None:
        height, width = real_face_bgr.shape[:2]
        result = detect(real_face_bgr)
        assert result is not None
        for region in (result.forehead, result.left_cheek, result.right_cheek):
            assert region.valid
            assert 0 <= region.x0 < region.x1 <= width
            assert 0 <= region.y0 < region.y1 <= height

    def test_cheeks_sit_on_either_side_of_the_face_centre(self, real_face_bgr: np.ndarray) -> None:
        result = detect(real_face_bgr)
        assert result is not None
        left_center = (result.left_cheek.x0 + result.left_cheek.x1) / 2
        right_center = (result.right_cheek.x0 + result.right_cheek.x1) / 2
        assert left_center < right_center

    def test_forehead_sits_above_the_cheeks(self, real_face_bgr: np.ndarray) -> None:
        result = detect(real_face_bgr)
        assert result is not None
        assert result.forehead.y1 <= result.left_cheek.y0 + 5  # small tolerance
