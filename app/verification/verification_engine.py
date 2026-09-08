"""Verification Engine: combines the deterministic NumericMatcher and the
LLM EntailmentChecker into one final verdict per claim (PRD section 12,
"dual-path verification").

Combination rule (documented, deterministic, and gives priority to
non-LLM evidence per the project's core instruction "do not use the LLM for
things that can be deterministically verified"):
  - If the NumericMatcher found a conclusive normalized match -> SUPPORTED,
    unless the LLM entailment check independently and confidently found a
    CONTRADICTION (e.g. it caught a period/basis mismatch prose alone can
    reveal but pure number-matching cannot) - in that case the LLM wins,
    since it's looking at more than just the raw number.
  - If the NumericMatcher found a conclusive numeric mismatch -> CONTRADICTED.
  - Otherwise (numeric check inconclusive, or claim is qualitative) -> defer
    to the LLM entailment verdict.
"""
from __future__ import annotations

from app.llm import LLMProvider
from app.schemas import Claim, ClaimType, VerificationResult, VerificationVerdict
from app.verification.entailment_checker import EntailmentChecker
from app.verification.numeric_matcher import NumericMatcher


class VerificationEngine:
    def __init__(self, llm: LLMProvider | None = None):
        self.numeric_matcher = NumericMatcher()
        self.entailment_checker = EntailmentChecker(llm)

    def verify(self, claim: Claim) -> VerificationResult:
        numeric_result = self.numeric_matcher.match(claim) if claim.claim_type == ClaimType.NUMERIC else None
        entailment_result = self.entailment_checker.check(claim)
        final_verdict, combined_reason = self._combine(numeric_result, entailment_result)
        return VerificationResult(
            claim_id=claim.claim_id,
            numeric_result=numeric_result,
            entailment_result=entailment_result,
            final_verdict=final_verdict,
            combined_reason=combined_reason,
        )

    def verify_all(self, claims: list[Claim]) -> list[VerificationResult]:
        return [self.verify(claim) for claim in claims]

    @staticmethod
    def _combine(numeric_result, entailment_result) -> tuple[VerificationVerdict, str]:
        if numeric_result is not None and numeric_result.applicable:
            if numeric_result.normalized_match:
                if numeric_result.period_match is False:
                    return (
                        VerificationVerdict.INSUFFICIENT,
                        f"Evidence contains a matching numeric value, but does not appear to reference the "
                        f"claimed period ({numeric_result.notes}); cannot confirm the figure applies to the "
                        f"stated period.",
                    )
                if entailment_result.verdict == VerificationVerdict.CONTRADICTED and entailment_result.confidence >= 0.75:
                    return (
                        VerificationVerdict.CONTRADICTED,
                        f"Deterministic numeric matcher found a matching value, but the LLM entailment "
                        f"check independently found a contradiction: {entailment_result.reason}",
                    )
                return (
                    VerificationVerdict.SUPPORTED,
                    f"Deterministic numeric match ({numeric_result.notes}). LLM entailment agreed: {entailment_result.reason}",
                )
            if numeric_result.percent_difference is not None and numeric_result.percent_difference > 2.0:
                return (
                    VerificationVerdict.CONTRADICTED,
                    f"Deterministic numeric mismatch ({numeric_result.notes}).",
                )

        return entailment_result.verdict, f"LLM entailment check: {entailment_result.reason}"
