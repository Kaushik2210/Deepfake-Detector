"""Evaluation metrics.

Two decisions here matter more than the formulas.

First, TPR at a low FPR cannot be estimated from a sample that contains too few
negatives. With 1,000 authentic images the smallest observable false-positive
rate is 1/1000 = 0.1%, estimated from a single image — which is noise, not a
measurement. Rather than print a number that looks authoritative, these functions
return None and record why, and the report says so.

Second, a point estimate from a few thousand images carries real sampling error.
AUC is reported with a bootstrap confidence interval so the width is visible
instead of implied.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np


@dataclass
class ThresholdMetric:
    target_fpr: float
    tpr: float | None
    threshold: float | None
    measurable: bool
    note: str


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    count: int
    mean_confidence: float
    observed_frequency: float


@dataclass
class RocPoint:
    fpr: float
    tpr: float


@dataclass
class MetricSet:
    n: int
    n_positive: int
    n_negative: int
    auc: float
    auc_ci95: tuple[float, float]
    eer: float
    eer_threshold: float
    thresholds: list[ThresholdMetric] = field(default_factory=list)
    ece: float = 0.0
    calibration_bins: list[CalibrationBin] = field(default_factory=list)
    roc_points: list[RocPoint] = field(default_factory=list)
    mean_score_positive: float = 0.0
    mean_score_negative: float = 0.0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["auc_ci95"] = list(self.auc_ci95)
        return payload


def roc_curve(labels: np.ndarray, scores: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    from sklearn.metrics import roc_curve as sk_roc_curve

    fpr, tpr, thresholds = sk_roc_curve(labels, scores)
    return fpr, tpr, thresholds


def auc_score(labels: np.ndarray, scores: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(labels, scores))


def bootstrap_auc_ci(
    labels: np.ndarray,
    scores: np.ndarray,
    iterations: int = 500,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap interval for AUC.

    Resamples with replacement, keeping only draws that contain both classes.
    """
    rng = np.random.default_rng(seed)
    n = len(labels)
    values: list[float] = []

    for _ in range(iterations):
        index = rng.integers(0, n, n)
        sampled_labels = labels[index]
        if sampled_labels.min() == sampled_labels.max():
            continue
        values.append(auc_score(sampled_labels, scores[index]))

    if not values:
        return (float("nan"), float("nan"))

    return (
        float(np.percentile(values, 2.5)),
        float(np.percentile(values, 97.5)),
    )


def downsampled_roc_points(
    fpr: np.ndarray, tpr: np.ndarray, max_points: int = 60
) -> list[RocPoint]:
    """Thin a full ROC curve down to a bounded set of points for plotting.

    sklearn's roc_curve returns one point per distinct score, which for a few
    hundred samples is already small but for thousands would bloat the JSON
    report for no visual benefit -- a plotted curve at 60 points looks
    identical to one at 2,000. Endpoints are always kept so the curve still
    visibly starts at (0,0) and ends at (1,1) after thinning.
    """
    n = len(fpr)
    if n <= max_points:
        indices = np.arange(n)
    else:
        indices = np.unique(np.linspace(0, n - 1, max_points).astype(int))
    return [RocPoint(float(fpr[i]), float(tpr[i])) for i in indices]


def equal_error_rate(labels: np.ndarray, scores: np.ndarray) -> tuple[float, float]:
    """The rate at which false positives and false negatives are equal."""
    fpr, tpr, thresholds = roc_curve(labels, scores)
    fnr = 1.0 - tpr
    index = int(np.nanargmin(np.abs(fnr - fpr)))
    return float((fpr[index] + fnr[index]) / 2.0), float(thresholds[index])


def tpr_at_fpr(labels: np.ndarray, scores: np.ndarray, target_fpr: float) -> ThresholdMetric:
    """True-positive rate at a target false-positive rate.

    Returns an unmeasurable result rather than a misleading number when the
    negative set is too small to resolve the requested rate.
    """
    n_negative = int((labels == 0).sum())

    if n_negative == 0:
        return ThresholdMetric(
            target_fpr, None, None, False, "no authentic samples in this split"
        )

    smallest_resolvable = 1.0 / n_negative
    if target_fpr < smallest_resolvable:
        return ThresholdMetric(
            target_fpr,
            None,
            None,
            False,
            (
                f"not measurable: {n_negative} authentic samples resolve no finer than "
                f"{smallest_resolvable:.2%} FPR, so a {target_fpr:.2%} figure would rest "
                "on fewer than one false positive"
            ),
        )

    fpr, tpr, thresholds = roc_curve(labels, scores)
    eligible = np.where(fpr <= target_fpr)[0]
    if eligible.size == 0:
        return ThresholdMetric(
            target_fpr, None, None, False, "no threshold achieves this false-positive rate"
        )

    index = int(eligible[-1])
    expected_fps = target_fpr * n_negative
    note = f"based on ~{expected_fps:.0f} false positives out of {n_negative} authentic samples"
    if expected_fps < 10:
        note += "; fewer than 10 events, so this estimate is unstable"

    return ThresholdMetric(
        target_fpr, float(tpr[index]), float(thresholds[index]), True, note
    )


def expected_calibration_error(
    labels: np.ndarray, scores: np.ndarray, bins: int = 10
) -> tuple[float, list[CalibrationBin]]:
    """ECE plus the reliability-diagram bins it was computed from.

    A well-calibrated score of 0.8 should be right about 80% of the time. ECE is
    the average gap between claimed confidence and observed frequency, weighted
    by how many samples fall in each bin.
    """
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(scores)
    error = 0.0
    out: list[CalibrationBin] = []

    for i in range(bins):
        lower, upper = edges[i], edges[i + 1]
        mask = (scores >= lower) & (scores < upper if i < bins - 1 else scores <= upper)
        count = int(mask.sum())
        if count == 0:
            out.append(CalibrationBin(float(lower), float(upper), 0, 0.0, 0.0))
            continue

        confidence = float(scores[mask].mean())
        frequency = float(labels[mask].mean())
        error += (count / total) * abs(confidence - frequency)

        out.append(
            CalibrationBin(float(lower), float(upper), count, confidence, frequency)
        )

    return float(error), out


def evaluate(
    labels: np.ndarray,
    scores: np.ndarray,
    target_fprs: tuple[float, ...] = (0.01, 0.001),
) -> MetricSet:
    labels = np.asarray(labels).astype(int)
    scores = np.asarray(scores).astype(float)

    ece, bins = expected_calibration_error(labels, scores)
    eer, eer_threshold = equal_error_rate(labels, scores)
    fpr, tpr, _ = roc_curve(labels, scores)

    return MetricSet(
        n=len(labels),
        n_positive=int((labels == 1).sum()),
        n_negative=int((labels == 0).sum()),
        auc=auc_score(labels, scores),
        auc_ci95=bootstrap_auc_ci(labels, scores),
        eer=eer,
        eer_threshold=eer_threshold,
        thresholds=[tpr_at_fpr(labels, scores, fpr) for fpr in target_fprs],
        ece=ece,
        calibration_bins=bins,
        roc_points=downsampled_roc_points(fpr, tpr),
        mean_score_positive=float(scores[labels == 1].mean()) if (labels == 1).any() else 0.0,
        mean_score_negative=float(scores[labels == 0].mean()) if (labels == 0).any() else 0.0,
    )


@dataclass
class StreamComparison:
    stream_a: str
    stream_b: str
    n: int
    auc_a: float
    auc_b: float
    auc_diff: float
    auc_diff_ci95: tuple[float, float]
    p_value_two_sided: float
    significant_at_0_05: bool
    note: str

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["auc_diff_ci95"] = list(self.auc_diff_ci95)
        return payload


def compare_streams_auc(
    stream_a: str,
    stream_b: str,
    labels: np.ndarray,
    scores_a: np.ndarray,
    scores_b: np.ndarray,
    iterations: int = 2000,
    seed: int = 0,
) -> StreamComparison:
    """Is one stream's AUC advantage over another real, or sampling noise?

    A paired bootstrap: the same resampled indices are applied to both
    streams' scores on each iteration, since both were measured on the exact
    same clips -- that pairing is what makes this a legitimate significance
    test rather than two independent confidence intervals eyeballed for
    overlap (which under- and over-states significance in different regimes).
    The p-value is the two-sided fraction of bootstrap replicates on the
    other side of zero from the observed difference, doubled -- the
    percentile-bootstrap analogue of a two-sided test.
    """
    labels = np.asarray(labels).astype(int)
    scores_a = np.asarray(scores_a, dtype=float)
    scores_b = np.asarray(scores_b, dtype=float)

    observed_diff = auc_score(labels, scores_a) - auc_score(labels, scores_b)

    rng = np.random.default_rng(seed)
    n = len(labels)
    diffs: list[float] = []

    for _ in range(iterations):
        index = rng.integers(0, n, n)
        sampled_labels = labels[index]
        if sampled_labels.min() == sampled_labels.max():
            continue
        diffs.append(
            auc_score(sampled_labels, scores_a[index])
            - auc_score(sampled_labels, scores_b[index])
        )

    if not diffs:
        return StreamComparison(
            stream_a, stream_b, n, float("nan"), float("nan"), observed_diff,
            (float("nan"), float("nan")), float("nan"), False,
            "bootstrap could not resample both classes; too few samples to test",
        )

    diffs_arr = np.array(diffs)
    ci = (float(np.percentile(diffs_arr, 2.5)), float(np.percentile(diffs_arr, 97.5)))

    # Fraction of the bootstrap distribution that crosses zero from the side
    # the observed difference sits on -- doubled for a two-sided p-value,
    # capped at 1.0 since doubling a fraction already above 0.5 is meaningless.
    side_fraction = (
        float(np.mean(diffs_arr <= 0)) if observed_diff > 0 else float(np.mean(diffs_arr >= 0))
    )
    p_value = min(1.0, 2.0 * side_fraction)
    significant = p_value < 0.05

    note = (
        f"{stream_a} {'beats' if observed_diff > 0 else 'trails'} {stream_b} by "
        f"{abs(observed_diff):.4f} AUC; "
        + (
            f"significant at p={p_value:.4f} (the 95% CI on the difference excludes zero)"
            if significant
            else f"not significant at p={p_value:.4f} (the 95% CI on the difference includes zero) "
            "-- consistent with the two streams performing about the same"
        )
    )

    return StreamComparison(
        stream_a=stream_a,
        stream_b=stream_b,
        n=n,
        auc_a=auc_score(labels, scores_a),
        auc_b=auc_score(labels, scores_b),
        auc_diff=observed_diff,
        auc_diff_ci95=ci,
        p_value_two_sided=p_value,
        significant_at_0_05=significant,
        note=note,
    )
