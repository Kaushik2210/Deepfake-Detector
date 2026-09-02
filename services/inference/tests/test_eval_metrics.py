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


class TestRocPoints:
    def test_endpoints_are_preserved_under_thinning(self, separable) -> None:
        labels, scores = separable
        fpr, tpr, _ = metrics.roc_curve(labels, scores)
        points = metrics.downsampled_roc_points(fpr, tpr, max_points=10)

        assert points[0].fpr == pytest.approx(float(fpr[0]))
        assert points[-1].fpr == pytest.approx(float(fpr[-1]))
        assert len(points) <= 10

    def test_small_curves_are_not_thinned(self) -> None:
        fpr = np.array([0.0, 0.5, 1.0])
        tpr = np.array([0.0, 0.8, 1.0])
        points = metrics.downsampled_roc_points(fpr, tpr, max_points=60)
        assert len(points) == 3

    def test_included_in_evaluate_output(self, separable) -> None:
        labels, scores = separable
        result = metrics.evaluate(labels, scores)
        assert len(result.roc_points) > 0
        assert all(0.0 <= p.fpr <= 1.0 and 0.0 <= p.tpr <= 1.0 for p in result.roc_points)


class TestStreamComparison:
    def test_identical_streams_are_not_significant(self, separable) -> None:
        labels, scores = separable
        result = metrics.compare_streams_auc("a", "b", labels, scores, scores, iterations=200)

        assert result.auc_diff == pytest.approx(0.0, abs=1e-9)
        assert result.significant_at_0_05 is False

    def test_a_clearly_better_stream_is_significant(self) -> None:
        rng = np.random.default_rng(6)
        labels = np.array([0] * 400 + [1] * 400)
        strong = np.concatenate([rng.beta(1.5, 6, 400), rng.beta(6, 1.5, 400)])
        noise = rng.uniform(0, 1, 800)

        result = metrics.compare_streams_auc(
            "strong", "noise", labels, strong, noise, iterations=500
        )

        assert result.auc_diff > 0
        assert result.significant_at_0_05 is True
        assert result.p_value_two_sided < 0.05

    def test_a_near_tied_small_sample_is_not_necessarily_significant(self) -> None:
        """The exact scenario this test exists for: two streams with a small
        measured AUC gap on a modest sample should not be over-claimed as a
        real difference just because one number is higher than the other."""
        rng = np.random.default_rng(7)
        labels = np.array([0] * 25 + [1] * 25)
        a = np.concatenate([rng.beta(2, 3, 25), rng.beta(3, 2, 25)])
        b = np.concatenate([rng.beta(2.1, 3, 25), rng.beta(2.9, 2, 25)])

        result = metrics.compare_streams_auc("a", "b", labels, a, b, iterations=500)
        # Not asserting the direction, only that the test correctly declines
        # to call a small, noisy gap significant.
        assert result.significant_at_0_05 is False

    def test_ci_direction_matches_observed_difference(self) -> None:
        rng = np.random.default_rng(8)
        labels = np.array([0] * 300 + [1] * 300)
        strong = np.concatenate([rng.beta(1.5, 6, 300), rng.beta(6, 1.5, 300)])
        weak = np.concatenate([rng.beta(2.5, 4, 300), rng.beta(4, 2.5, 300)])

        result = metrics.compare_streams_auc("strong", "weak", labels, strong, weak, iterations=500)
        lo, hi = result.auc_diff_ci95
        assert lo <= result.auc_diff <= hi


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


class TestWeightStability:
    def test_a_clearly_stronger_stream_gets_a_stable_high_weight(self) -> None:
        rng = np.random.default_rng(9)
        labels = np.array([0] * 200 + [1] * 200)
        strong = np.concatenate([rng.beta(1.5, 6, 200), rng.beta(6, 1.5, 200)])
        weak = np.concatenate([rng.beta(2.3, 3, 200), rng.beta(3, 2.3, 200)])

        result = calibrate.bootstrap_weight_stability(
            labels, {"strong": strong, "weak": weak}, iterations=300, seed=0
        )

        assert result["strong"]["median"] > result["weak"]["median"]
        # A clear winner should stay a clear winner across almost every resample.
        assert result["strong"]["p10"] > result["weak"]["p90"]

    def test_near_tied_streams_produce_overlapping_intervals(self) -> None:
        """The exact scenario the fusion-weight fix produced: two streams
        close enough in AUC that which one gets slightly more weight should
        not be presented as a settled question."""
        rng = np.random.default_rng(10)
        labels = np.array([0] * 100 + [1] * 100)
        a = np.concatenate([rng.beta(2, 3, 100), rng.beta(3, 2, 100)])
        b = np.concatenate([rng.beta(2.05, 3, 100), rng.beta(2.95, 2, 100)])

        result = calibrate.bootstrap_weight_stability(
            labels, {"a": a, "b": b}, iterations=300, seed=0
        )

        # Overlap means the p10-p90 spans intersect -- neither stream's
        # interval sits entirely above the other's.
        assert not (result["a"]["p10"] > result["b"]["p90"])
        assert not (result["b"]["p10"] > result["a"]["p90"])

    def test_weights_still_sum_to_one_per_replicate_on_average(self) -> None:
        rng = np.random.default_rng(11)
        labels = np.array([0] * 150 + [1] * 150)
        a = np.concatenate([rng.beta(2, 4, 150), rng.beta(4, 2, 150)])
        b = np.concatenate([rng.beta(2.5, 4, 150), rng.beta(4, 2.5, 150)])

        result = calibrate.bootstrap_weight_stability(
            labels, {"a": a, "b": b}, iterations=300, seed=0
        )
        assert result["a"]["median"] + result["b"]["median"] == pytest.approx(1.0, abs=0.05)
