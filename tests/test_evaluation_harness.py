"""Wires the evaluation harness into the regular pytest run, so the PRD's
success criteria are checked automatically rather than only via a manual
script. Failing this test means the pipeline has regressed against its own
hand-labelled ground truth.
"""
from evaluation.run_evaluation import run_conflict_eval, run_verification_eval


def test_verification_eval_has_full_citation_coverage():
    report = run_verification_eval()
    assert report["total_cases"] >= 60  # PRD section 18: ~60-100 claim/span pairs
    assert report["citation_verification_coverage"] == 1.0  # PRD success criterion


def test_verification_eval_accuracy_is_high():
    report = run_verification_eval()
    assert report["overall_accuracy"] >= 0.85


def test_brier_score_is_better_than_naive_baseline():
    """A Brier score is reported (PRD success criterion: "calibrated
    confidence scores with a reported Brier score") and beats the 0.25 a
    constant "always 50% confident" predictor would score."""
    report = run_verification_eval()
    assert report["brier_score"] is not None
    assert 0.0 <= report["brier_score"] < 0.25


def test_conflict_detection_meets_prd_90_percent_target():
    """PRD success criterion: '90%+ conflict flagging accuracy on the
    labelled evaluation set'."""
    report = run_conflict_eval()
    assert report["conflict_raised_precision"] >= 0.9
    assert report["conflict_raised_recall"] >= 0.9
    assert report["genuine_vs_explained_accuracy"] >= 0.9
