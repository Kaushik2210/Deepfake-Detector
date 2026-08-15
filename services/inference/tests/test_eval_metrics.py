"""Evaluation metrics and calibration fitting.

The properties worth guarding here are the honesty ones: that an unmeasurable
metric reports itself as unmeasurable, and that calibration cannot silently
change how samples rank.
"""

from __future__ import annotations

import numpy as np
import pytest

from eval import calibrate, metrics


@pytest.fixture
def separable():
    """A dataset a detector should score well on."""
    rng = np.random.default_rng(0)
    labels = np.array([0] * 500 + [1] * 500)
    scores = np.concatenate([rng.beta(2, 5, 500), rng.beta(5, 2, 500)])
    return labels, scores


class TestThresholdMetrics:
    def test_reports_unmeasurable_rather_than_guessing(self) -> None:
        """The central honesty property of this module."""
        labels = np.array([0] * 20 + [1] * 20)
        scores = np.linspace(0, 1, 40)

        result = metrics.tpr_at_fpr(labels, scores, 0.001)

        assert result.measurable is False
        assert result.tpr is None
        assert "not measurable" in result.note

    def test_measurable_when_the_negative_set_is_large_enough(self, separable) -> None:
        labels, scores = separable
        result = metrics.tpr_at_fpr(labels, scores, 0.01)

        assert result.measurable is True
        assert 0.0 <= result.tpr <= 1.0

    def test_flags_estimates_built_on_few_events(self, separable) -> None:
        labels, scores = separable
        # 500 negatives at 1% FPR is ~5 expected false positives.
        result = metrics.tpr_at_fpr(labels, scores, 0.01)
        assert "unstable" in result.note

    def test_no_negatives_is_unmeasurable(self) -> None:
        result = metrics.tpr_at_fpr(np.ones(10, dtype=int), np.linspace(0, 1, 10), 0.01)
        assert result.measurable is False


class TestAuc:
    def test_perfect_separation(self) -> None:
        labels = np.array([0, 0, 0, 1, 1, 1])
        assert metrics.auc_score(labels, np.array([0.1, 0.2, 0.3, 0.7, 0.8, 0.9])) == 1.0

    def test_confidence_interval_brackets_the_estimate(self, separable) -> None:
        labels, scores = separable
        auc = metrics.auc_score(labels, scores)
        lo, hi = metrics.bootstrap_auc_ci(labels, scores, iterations=200)

        assert lo <= auc <= hi
        assert hi - lo < 0.2

    def test_small_samples_produce_wider_intervals(self) -> None:
        """Sampling error must be visible, not implied."""
        rng = np.random.default_rng(1)
        big_labels = np.array([0] * 400 + [1] * 400)
        big_scores = np.concatenate([rng.beta(2, 4, 400), rng.beta(4, 2, 400)])

        small_labels = big_labels[::20]
        small_scores = big_scores[::20]

        big_lo, big_hi = metrics.bootstrap_auc_ci(big_labels, big_scores, iterations=200)
        small_lo, small_hi = metrics.bootstrap_auc_ci(small_labels, small_scores, iterations=200)

        assert (small_hi - small_lo) > (big_hi - big_lo)


class TestCalibrationError:
    def test_perfectly_calibrated_scores_have_near_zero_ece(self) -> None:
        rng = np.random.default_rng(2)
        scores = rng.uniform(0, 1, 20000)
        labels = (rng.uniform(0, 1, 20000) < scores).astype(int)

        ece, _ = metrics.expected_calibration_error(labels, scores)
        assert ece < 0.02

    def test_overconfident_scores_have_high_ece(self) -> None:
        labels = np.array([0] * 500 + [1] * 500)
        # Claims near-certainty but is right only half the time.
        scores = np.full(1000, 0.99)

        ece, _ = metrics.expected_calibration_error(labels, scores)
        assert ece > 0.4

    def test_bins_partition_all_samples(self, separable) -> None:
        labels, scores = separable
        _, bins = metrics.expected_calibration_error(labels, scores, bins=10)
        assert sum(b.count for b in bins) == len(scores)


class TestTemperatureFitting:
    def test_softens_an_overconfident_model(self) -> None:
        labels = np.array([0] * 500 + [1] * 500)
        rng = np.random.default_rng(3)
        scores = np.concatenate([rng.uniform(0.0, 0.05, 500), rng.uniform(0.95, 1.0, 500)])
        # Flip a third of the labels so the confidence is unjustified.
        labels[:170] = 1

        temperature, _ = calibrate.fit_temperature(labels, scores)
        assert temperature > 1.0

    def test_fitting_reduces_negative_log_likelihood(self) -> None:
        """NLL is the objective, so it must improve or stay level."""
        rng = np.random.default_rng(4)
        labels = np.array([0] * 800 + [1] * 800)
        scores = np.concatenate([rng.beta(1.2, 6, 800), rng.beta(6, 1.2, 800)])
        labels[:250] = 1

        _, fitted_nll = calibrate.fit_temperature(labels, scores)
        _, baseline_nll = calibrate.fit_temperature(labels, scores, grid=np.array([1.0]))

        assert fitted_nll <= baseline_nll

    def test_fitting_improves_calibration_on_an_overconfident_model(self) -> None:
        """ECE improves in the case temperature scaling exists to fix.

        Note ECE is not the fitted objective — NLL is — so the two can disagree
        on adversarial distributions. This asserts the well-behaved case.
        """
        rng = np.random.default_rng(4)
        labels = np.concatenate([np.zeros(800, dtype=int), np.ones(800, dtype=int)])
        # Confidently near 0/1 but wrong a quarter of the time.
        scores = np.concatenate([rng.uniform(0.01, 0.08, 800), rng.uniform(0.92, 0.99, 800)])
        flip = rng.choice(1600, 400, replace=False)
        labels[flip] = 1 - labels[flip]

        before, _ = metrics.expected_calibration_error(labels, scores)
        temperature, _ = calibrate.fit_temperature(labels, scores)
        after, _ = metrics.expected_calibration_error(
            labels, calibrate.apply_temperature(scores, temperature)
        )

        assert temperature > 1.0
        assert after < before

    def test_temperature_never_changes_auc(self) -> None:
        """Calibration adjusts confidence, not ranking. AUC must be untouched."""
        rng = np.random.default_rng(5)
        labels = np.array([0] * 300 + [1] * 300)
        scores = np.concatenate([rng.beta(2, 5, 300), rng.beta(5, 2, 300)])

        before = metrics.auc_score(labels, scores)
        after = metrics.auc_score(labels, calibrate.apply_temperature(scores, 3.7))

        assert after == pytest.approx(before, abs=1e-9)

    def test_rejects_non_positive_temperature(self) -> None:
        with pytest.raises(ValueError):
            calibrate.apply_temperature(np.array([0.5]), 0.0)


class TestFusionWeights:
    def test_weight_is_proportional_to_lift_over_chance(self) -> None:
        weights = calibrate.derive_fusion_weights({"a": 0.9, "b": 0.7})
        by_name = {w.stream: w.weight for w in weights}

        # Weights are rounded to 4 dp for readability in the persisted file.
        assert by_name["a"] == pytest.approx(0.4 / 0.6, abs=1e-4)
        assert by_name["b"] == pytest.approx(0.2 / 0.6, abs=1e-4)
        assert sum(by_name.values()) == pytest.approx(1.0, abs=1e-3)

    def test_chance_level_stream_gets_zero_weight(self) -> None:
        weights = {w.stream: w for w in calibrate.derive_fusion_weights({"a": 0.85, "b": 0.5})}

        assert weights["b"].weight == 0.0
        assert "at or below chance" in weights["b"].rationale

    def test_below_chance_stream_is_not_inverted(self) -> None:
        """Inverting would be fitting to the split, not measuring."""
        weights = {w.stream: w for w in calibrate.derive_fusion_weights({"a": 0.8, "b": 0.2})}
        assert weights["b"].weight == 0.0

    def test_all_streams_at_chance_yields_no_weights(self) -> None:
        weights = calibrate.derive_fusion_weights({"a": 0.5, "b": 0.48})
        assert all(w.weight == 0.0 for w in weights)
        assert all("cannot be weighted" in w.rationale or "chance" in w.rationale for w in weights)
