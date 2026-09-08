"""Adversarial tests (PRD section 19): deliberately introduce subtly
incorrect claims and confirm the verification engine catches them, rather
than trusting whatever an LLM would have generated.
"""
from app.analysis.normalizer import normalize_value
from app.schemas import Basis, Claim, ClaimType, Evidence, NormalizedValue, VerificationVerdict
from app.verification.verification_engine import VerificationEngine


def _claim(value, unit, period, evidence_text, basis=Basis.UNKNOWN, metric="revenue") -> Claim:
    magnitude, base_unit, note = normalize_value(value, unit, evidence_text)
    return Claim(
        research_run_id="run_test", claim_type=ClaimType.NUMERIC, entity="Apple Inc.", metric=metric,
        value=value, unit=unit, period=period, basis=basis,
        normalized=NormalizedValue(raw_value=value, magnitude=magnitude, base_unit=base_unit, scale_applied=note, period_label=period),
        source_id="src_1", evidence_span=Evidence(source_id="src_1", start_char=0, end_char=len(evidence_text), evidence_text=evidence_text),
        statement=f"{metric} was {value} {unit} for {period}",
    )


def test_adversarial_wrong_number_is_contradicted():
    """PRD canonical example: source says $85.8B, planted claim says $88.5B."""
    evidence = "Revenue was $85.8 billion for Q3 2024."
    claim = _claim("88.5", "billion", "Q3 2024", evidence)
    result = VerificationEngine(llm=None).verify(claim)
    assert result.final_verdict == VerificationVerdict.CONTRADICTED


def test_adversarial_wrong_unit_is_not_supported():
    """Same digits, wrong magnitude: '85.8 million' claimed against a
    '85.8 billion' evidence statement - a 1000x error that naive string
    matching on the digits alone would miss."""
    evidence = "Revenue was $85.8 billion for Q3 2024."
    claim = _claim("85.8", "million", "Q3 2024", evidence)
    result = VerificationEngine(llm=None).verify(claim)
    assert result.final_verdict != VerificationVerdict.SUPPORTED


def test_adversarial_wrong_period_same_number_is_not_confidently_supported():
    """Same number, but the evidence is about a different quarter than the
    claim states - must not be blindly accepted just because the digits match."""
    evidence = "Revenue was $85.8 billion for Q2 2024."
    claim = _claim("85.8", "billion", "Q3 2024", evidence)
    result = VerificationEngine(llm=None).verify(claim)
    assert result.final_verdict != VerificationVerdict.SUPPORTED
    assert result.numeric_result.period_match is False


def test_adversarial_percentage_claimed_as_absolute_value_does_not_match():
    """A claim stating operating margin as a raw ratio (0.296) should not be
    confused with a source stating it as a percentage (29.6%) unless
    correctly normalized - here we deliberately give the WRONG absolute
    value (2.96) to confirm it's caught as a mismatch, not silently accepted."""
    evidence = "Operating margin was approximately 29.6% for the quarter."
    claim = _claim("2.96", None, "Q3 2024", evidence, metric="operating_margin")
    result = VerificationEngine(llm=None).verify(claim)
    assert result.final_verdict != VerificationVerdict.SUPPORTED


def test_adversarial_gaap_vs_non_gaap_basis_is_flagged_by_conflict_detector():
    """GAAP vs non-GAAP EBITDA is a common real-world 'adversarial-looking'
    discrepancy that must be explained, not silently merged or falsely
    flagged as a genuine disagreement - covered at the conflict-detector
    level since a single claim's basis alone can't reveal the mismatch."""
    from app.analysis.conflict_detector import ConflictDetector

    gaap_claim = _claim("8", "billion", "Q3 2024", "EBITDA (GAAP) was $8 billion.", basis=Basis.GAAP, metric="ebitda")
    gaap_claim.source_id = "src_a"
    gaap_claim.evidence_span.source_id = "src_a"
    adjusted_claim = _claim("10", "billion", "Q3 2024", "Adjusted EBITDA was $10 billion.", basis=Basis.ADJUSTED, metric="ebitda")
    adjusted_claim.source_id = "src_b"
    adjusted_claim.evidence_span.source_id = "src_b"

    conflicts = ConflictDetector().detect([gaap_claim, adjusted_claim])
    assert len(conflicts) == 1
    assert conflicts[0].is_genuine_conflict is False
    assert conflicts[0].reason_type.value == "basis_mismatch"


def test_adversarial_quarterly_vs_annual_period_type_is_not_a_genuine_conflict():
    from app.analysis.conflict_detector import ConflictDetector

    quarterly = _claim("85.8", "billion", "Q3 2024", "Revenue was $85.8 billion for Q3 2024.")
    quarterly.source_id, quarterly.evidence_span.source_id = "src_a", "src_a"
    annual = _claim("391.0", "billion", "FY 2024", "Full year revenue was $391.0 billion.")
    annual.source_id, annual.evidence_span.source_id = "src_b", "src_b"

    conflicts = ConflictDetector().detect([quarterly, annual])
    assert len(conflicts) == 1
    assert conflicts[0].is_genuine_conflict is False
    assert conflicts[0].reason_type.value == "period_mismatch"
