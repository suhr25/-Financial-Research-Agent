"""LLM Entailment Checker (PRD section 12).

Given ONLY a claim and its raw evidence text - never the generated report,
never other claims, never a summary - determines whether the evidence
supports, contradicts, or is insufficient for the claim. This isolation is
what prevents the "verifier grading its own homework" failure mode the PRD
explicitly calls out (section 5.1.4): the checker cannot see what the
Report Generator wrote, only the same primary evidence the claim itself was
extracted from.
"""
from __future__ import annotations

import logging

from app.llm import LLMProvider, get_llm_provider
from app.schemas import Claim, ClaimType, EntailmentResult, VerificationVerdict

logger = logging.getLogger("financial_research_agent.verification.entailment_checker")

ENTAILMENT_SYSTEM_PROMPT = """You are the Entailment Checker of a financial research agent's verification engine.

You will be given a CLAIM and a piece of SOURCE EVIDENCE - the verbatim, original text the claim
was supposedly extracted from. You have NO OTHER CONTEXT about this company or research task.

Determine whether the SOURCE EVIDENCE:
- SUPPORTED: clearly confirms the claim as stated (value, period and basis all consistent)
- CONTRADICTED: clearly conflicts with the claim (e.g. a different number, period, or basis is stated)
- INSUFFICIENT: does not contain enough information to confirm or deny the claim

Be strict: a claim is only SUPPORTED if the evidence text actually says what the claim says, not
merely something related. Do not use outside/world knowledge about the company - judge only from
the evidence text given.
"""


class EntailmentChecker:
    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm if llm is not None else get_llm_provider()

    def check(self, claim: Claim) -> EntailmentResult:
        if self.llm is not None:
            try:
                return self._llm_check(claim)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM entailment check failed for claim=%s (%s); using mock checker", claim.claim_id, exc)
        return self._mock_check(claim)

    def _llm_check(self, claim: Claim) -> EntailmentResult:
        user_prompt = (
            f"CLAIM:\n"
            f"  Statement: {claim.statement}\n"
            f"  Entity: {claim.entity}\n"
            f"  Metric: {claim.metric}\n"
            f"  Value: {claim.value} {claim.unit or ''}\n"
            f"  Period: {claim.period or 'unspecified'}\n"
            f"  Basis: {claim.basis.value}\n\n"
            f"SOURCE EVIDENCE (verbatim, this is the ONLY information you may use to judge the claim):\n"
            f"\"\"\"\n{claim.evidence_span.evidence_text}\n\"\"\"\n"
        )
        return self.llm.complete_json(
            system=ENTAILMENT_SYSTEM_PROMPT, user=user_prompt, schema_model=EntailmentResult, max_tokens=500
        )

    # ---- Mock path -------------------------------------------------------

    def _mock_check(self, claim: Claim) -> EntailmentResult:
        if claim.claim_type == ClaimType.NUMERIC:
            return self._mock_check_numeric(claim)
        return self._mock_check_qualitative(claim)

    def _mock_check_numeric(self, claim: Claim) -> EntailmentResult:
        from app.verification.numeric_matcher import NumericMatcher

        result = NumericMatcher().match(claim)
        if not result.applicable:
            return EntailmentResult(
                verdict=VerificationVerdict.INSUFFICIENT,
                reason="Claim value could not be parsed as a number to compare against evidence.",
                confidence=0.3,
            )
        if result.normalized_match:
            return EntailmentResult(
                verdict=VerificationVerdict.SUPPORTED,
                reason=f"Evidence contains a matching numeric value ({result.notes}).",
                confidence=0.92,
            )
        if result.percent_difference is not None and result.percent_difference > 2.0:
            return EntailmentResult(
                verdict=VerificationVerdict.CONTRADICTED,
                reason=f"Evidence contains a comparable figure that differs by {result.percent_difference:.2f}%, exceeding tolerance.",
                confidence=0.85,
            )
        return EntailmentResult(
            verdict=VerificationVerdict.INSUFFICIENT,
            reason="No comparable numeric value with a matching unit/currency found in evidence text.",
            confidence=0.4,
        )

    def _mock_check_qualitative(self, claim: Claim) -> EntailmentResult:
        evidence_lower = claim.evidence_span.evidence_text.lower()
        value_lower = claim.value.lower().strip()
        if value_lower and (value_lower in evidence_lower or evidence_lower in value_lower):
            return EntailmentResult(
                verdict=VerificationVerdict.SUPPORTED,
                reason="Claim text is directly present in the source evidence.",
                confidence=0.88,
            )
        overlap = _word_overlap_ratio(value_lower, evidence_lower)
        if overlap >= 0.6:
            return EntailmentResult(
                verdict=VerificationVerdict.SUPPORTED,
                reason=f"Claim substantially overlaps with source evidence (word overlap={overlap:.2f}).",
                confidence=0.7,
            )
        return EntailmentResult(
            verdict=VerificationVerdict.INSUFFICIENT,
            reason="Insufficient textual overlap between claim and evidence to confirm support.",
            confidence=0.35,
        )


def _word_overlap_ratio(a: str, b: str) -> float:
    words_a = set(w for w in a.split() if len(w) > 2)
    words_b = set(w for w in b.split() if len(w) > 2)
    if not words_a:
        return 0.0
    return len(words_a & words_b) / len(words_a)
