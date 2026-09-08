"""Calibration analysis (PRD section 20): given (confidence, was_correct)
pairs from the evaluation harness, compute a Brier score and a reliability
(calibration) curve - reproducible from the evaluation dataset, not a
claimed/assumed number.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CalibrationBin:
    bin_range: str
    avg_confidence: float | None
    empirical_accuracy: float | None
    count: int


def brier_score(predictions: list[tuple[float, bool]]) -> float:
    """Mean squared error between predicted confidence (as a probability of
    being correct) and the actual binary outcome. 0.0 is a perfect score,
    0.25 is what a constant "always 50%" predictor would score on a
    balanced set, 1.0 is the worst possible score."""
    if not predictions:
        return float("nan")
    total = sum((conf - (1.0 if correct else 0.0)) ** 2 for conf, correct in predictions)
    return total / len(predictions)


def calibration_curve(predictions: list[tuple[float, bool]], n_bins: int = 10) -> list[CalibrationBin]:
    bins: list[CalibrationBin] = []
    edges = [i / n_bins for i in range(n_bins + 1)]
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        in_bin = [(c, correct) for c, correct in predictions if (lo <= c < hi) or (i == n_bins - 1 and c == hi)]
        if not in_bin:
            bins.append(CalibrationBin(f"{lo:.1f}-{hi:.1f}", None, None, 0))
            continue
        avg_conf = sum(c for c, _ in in_bin) / len(in_bin)
        accuracy = sum(1 for _, correct in in_bin if correct) / len(in_bin)
        bins.append(CalibrationBin(f"{lo:.1f}-{hi:.1f}", round(avg_conf, 4), round(accuracy, 4), len(in_bin)))
    return bins
