from app.analysis.normalizer import normalize_value
from app.schemas import Basis, Claim, ClaimType, Evidence, NormalizedValue
from app.verification.numeric_matcher import NumericMatcher


def _numeric_claim(value: str, unit: str, evidence_text: str, period="Q3 2024") -> Claim:
    magnitude, base_unit, note = normalize_value(value, unit, evidence_text)
    return Claim(
        research_run_id="run_test",
        claim_type=ClaimType.NUMERIC,
        entity="Apple Inc.",
        metric="revenue",
        value=value,
        unit=unit,
        period=period,
        basis=Basis.UNKNOWN,
        normalized=NormalizedValue(raw_value=value, magnitude=magnitude, base_unit=base_unit, scale_applied=note, period_label=period),
        source_id="src_test",
        evidence_span=Evidence(source_id="src_test", start_char=0, end_char=len(evidence_text), evidence_text=evidence_text),
        statement=f"Revenue was ${value} {unit}",
    )


def test_exact_value_in_evidence_is_supported_match():
    evidence = "Revenue was $85.8 billion for Q3 2024, up 5% year over year."
    claim = _numeric_claim("85.8", "billion", evidence)
    result = NumericMatcher().match(claim)
    assert result.applicable is True
    assert result.normalized_match is True
    assert result.percent_difference is None or result.percent_difference <= 0.5


def test_adversarial_wrong_number_is_flagged_as_mismatch():
    """PRD's canonical adversarial example: source says $85.8B, claim says $88.5B."""
    evidence = "Revenue was $85.8 billion for Q3 2024."
    claim = _numeric_claim("88.5", "billion", evidence)
    result = NumericMatcher().match(claim)
    assert result.applicable is True
    assert result.normalized_match is False
    assert result.percent_difference is not None and result.percent_difference > 2.0


def test_million_vs_billion_representations_still_match():
    evidence = "Revenue was $1,200 million for the quarter."
    claim = _numeric_claim("1.2", "billion", evidence)
    result = NumericMatcher().match(claim)
    assert result.normalized_match is True


def test_wrong_unit_is_not_falsely_matched():
    """A claim of '85.8 million' should NOT match evidence stating '85.8 billion' -
    these differ by 1000x even though the raw digits match."""
    evidence = "Revenue was $85.8 billion for Q3 2024."
    claim = _numeric_claim("85.8", "million", evidence)
    result = NumericMatcher().match(claim)
    assert result.normalized_match is False


def test_no_numeric_claim_type_is_not_applicable():
    from app.schemas import Evidence

    claim = Claim(
        research_run_id="run_test",
        claim_type=ClaimType.QUALITATIVE,
        entity="Apple Inc.",
        metric="risk_factor",
        value="Some risk statement.",
        source_id="src_test",
        evidence_span=Evidence(source_id="src_test", start_char=0, end_char=5, evidence_text="Some "),
        statement="Some risk statement.",
    )
    result = NumericMatcher().match(claim)
    assert result.applicable is False
