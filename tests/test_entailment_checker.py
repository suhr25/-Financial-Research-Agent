from app.schemas import Basis, Claim, ClaimType, Evidence, VerificationVerdict
from app.verification.entailment_checker import EntailmentChecker


def _qualitative_claim(value: str, evidence_text: str) -> Claim:
    return Claim(
        research_run_id="run_test",
        claim_type=ClaimType.QUALITATIVE,
        entity="Apple Inc.",
        metric="risk_factor",
        value=value,
        basis=Basis.UNKNOWN,
        source_id="src_test",
        evidence_span=Evidence(source_id="src_test", start_char=0, end_char=len(evidence_text), evidence_text=evidence_text),
        statement=value,
    )


def test_qualitative_claim_directly_present_in_evidence_is_supported():
    evidence = "The company faces substantial competition in all of its markets."
    claim = _qualitative_claim(evidence, evidence)
    result = EntailmentChecker(llm=None).check(claim)
    assert result.verdict == VerificationVerdict.SUPPORTED
    assert 0.0 <= result.confidence <= 1.0


def test_qualitative_claim_unrelated_to_evidence_is_insufficient():
    evidence = "The weather was sunny with light winds across the region."
    claim = _qualitative_claim("The company faces significant regulatory risk in Europe.", evidence)
    result = EntailmentChecker(llm=None).check(claim)
    assert result.verdict == VerificationVerdict.INSUFFICIENT


def test_result_is_a_valid_structured_entailment_result():
    """PRD: entailment output must be a structured Pydantic result, not free text."""
    evidence = "Net income was $21.4 billion for the quarter."
    claim = _qualitative_claim(evidence, evidence)
    result = EntailmentChecker(llm=None).check(claim)
    assert result.verdict in (VerificationVerdict.SUPPORTED, VerificationVerdict.CONTRADICTED, VerificationVerdict.INSUFFICIENT)
    assert isinstance(result.reason, str) and result.reason
