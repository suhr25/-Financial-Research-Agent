from app.analysis.conflict_detector import ConflictDetector
from app.analysis.normalizer import normalize_value
from app.schemas import Basis, Claim, ClaimType, ConflictReasonType, Evidence, NormalizedValue


def _claim(entity, metric, value, unit, period, basis, source_id) -> Claim:
    magnitude, base_unit, note = normalize_value(value, unit, f"{value} {unit}")
    return Claim(
        research_run_id="run_test",
        claim_type=ClaimType.NUMERIC,
        entity=entity,
        metric=metric,
        value=value,
        unit=unit,
        period=period,
        basis=basis,
        normalized=NormalizedValue(raw_value=value, magnitude=magnitude, base_unit=base_unit, scale_applied=note, period_label=period),
        source_id=source_id,
        evidence_span=Evidence(source_id=source_id, start_char=0, end_char=5, evidence_text="dummy"),
        statement=f"{metric} was {value} {unit}",
    )


def test_genuine_numeric_disagreement_is_flagged():
    a = _claim("Apple Inc.", "revenue", "85.8", "billion", "Q3 2024", Basis.GAAP, "src_a")
    b = _claim("Apple Inc.", "revenue", "90.0", "billion", "Q3 2024", Basis.GAAP, "src_b")
    conflicts = ConflictDetector().detect([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].is_genuine_conflict is True
    assert conflicts[0].reason_type == ConflictReasonType.GENUINE_DISAGREEMENT


def test_gaap_vs_adjusted_basis_mismatch_is_not_a_genuine_conflict():
    """PRD section 13: EBITDA=$10B adjusted vs EBITDA=$8B GAAP should not be
    blindly reported as a contradiction - the basis mismatch explains it."""
    a = _claim("Apple Inc.", "ebitda", "10", "billion", "Q3 2024", Basis.ADJUSTED, "src_a")
    b = _claim("Apple Inc.", "ebitda", "8", "billion", "Q3 2024", Basis.GAAP, "src_b")
    conflicts = ConflictDetector().detect([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].is_genuine_conflict is False
    assert conflicts[0].reason_type == ConflictReasonType.BASIS_MISMATCH


def test_different_periods_are_not_flagged_as_conflicting():
    a = _claim("Apple Inc.", "revenue", "85.8", "billion", "Q3 2024", Basis.UNKNOWN, "src_a")
    b = _claim("Apple Inc.", "revenue", "300.0", "billion", "FY 2024", Basis.UNKNOWN, "src_b")
    conflicts = ConflictDetector().detect([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].is_genuine_conflict is False
    assert conflicts[0].reason_type == ConflictReasonType.PERIOD_MISMATCH


def test_currency_mismatch_is_not_a_genuine_conflict():
    a = _claim("Reliance Industries", "revenue", "100", "crore", "FY 2024", Basis.UNKNOWN, "src_a")
    b = _claim("Reliance Industries", "revenue", "12", "million", "FY 2024", Basis.UNKNOWN, "src_b")
    conflicts = ConflictDetector().detect([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].reason_type == ConflictReasonType.UNIT_CURRENCY_MISMATCH
    assert conflicts[0].is_genuine_conflict is False


def test_values_within_tolerance_are_not_flagged_at_all():
    a = _claim("Apple Inc.", "revenue", "85.80", "billion", "Q3 2024", Basis.UNKNOWN, "src_a")
    b = _claim("Apple Inc.", "revenue", "85.81", "billion", "Q3 2024", Basis.UNKNOWN, "src_b")
    conflicts = ConflictDetector().detect([a, b])
    assert conflicts == []


def test_same_source_claims_are_never_compared():
    a = _claim("Apple Inc.", "revenue", "85.8", "billion", "Q3 2024", Basis.UNKNOWN, "src_a")
    b = _claim("Apple Inc.", "revenue", "200.0", "billion", "Q3 2024", Basis.UNKNOWN, "src_a")
    conflicts = ConflictDetector().detect([a, b])
    assert conflicts == []
