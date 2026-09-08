"""Confidence Scorer (PRD section 14).

A transparent, inspectable weighted sum - never "ask the LLM to grade
itself a confidence score". Every component is independently computable and
the weights are named constants at module level so they are easy to find,
tune, and cite in the viva/README.

`confidence` here means: how confident the system is in its verification
VERDICT (whatever that verdict is - SUPPORTED, CONTRADICTED, or
INSUFFICIENT), not "how likely the underlying fact is to be true". A
confidently CONTRADICTED claim should score highly on this scale too - it
means the system is sure it caught an error.
"""
from __future__ import annotations

from app.schemas import Claim, ClaimType, Source, SourceTier, VerificationResult

# Documented, configurable weights (must sum to 1.0).
WEIGHTS = {
    "source_quality": 0.25,
    "evidence_match": 0.30,
    "corroboration": 0.20,
    "entailment": 0.25,
}

SOURCE_TIER_QUALITY = {
    SourceTier.PRIMARY_FILING: 1.00,
    SourceTier.FINANCIAL_API: 0.85,
    SourceTier.PRESS: 0.65,
    SourceTier.AGGREGATOR: 0.45,
    SourceTier.MOCK: 0.50,
}

CORROBORATION_TOLERANCE_PCT = 5.0


class ConfidenceScorer:
    def score_all(
        self,
        claims: list[Claim],
        verifications: dict[str, VerificationResult],
        sources: dict[str, Source],
    ) -> None:
        """Mutates each claim in place: sets `confidence` and `confidence_breakdown`."""
        for claim in claims:
            verification = verifications.get(claim.claim_id)
            if verification is None:
                continue
            source = sources.get(claim.source_id)
            breakdown = self._score_one(claim, verification, source, claims)
            claim.confidence = breakdown["final_confidence"]
            claim.confidence_breakdown = breakdown

    def _score_one(
        self, claim: Claim, verification: VerificationResult, source: Source | None, all_claims: list[Claim]
    ) -> dict[str, float]:
        source_quality = SOURCE_TIER_QUALITY.get(source.source_tier, 0.5) if source else 0.5

        numeric_result = verification.numeric_result
        if claim.claim_type == ClaimType.NUMERIC and numeric_result is not None and numeric_result.applicable:
            if numeric_result.exact_match:
                evidence_match = 1.0
            elif numeric_result.normalized_match:
                evidence_match = 0.95
            elif numeric_result.percent_difference is not None and numeric_result.percent_difference > 2.0:
                evidence_match = min(0.95, 0.5 + numeric_result.percent_difference / 100)
            else:
                evidence_match = 0.30
        else:
            evidence_match = verification.entailment_result.confidence

        entailment = verification.entailment_result.confidence
        corroboration = self._corroboration_score(claim, all_claims)

        final = (
            WEIGHTS["source_quality"] * source_quality
            + WEIGHTS["evidence_match"] * evidence_match
            + WEIGHTS["corroboration"] * corroboration
            + WEIGHTS["entailment"] * entailment
        )

        return {
            "source_quality": round(source_quality, 4),
            "evidence_match": round(evidence_match, 4),
            "corroboration": round(corroboration, 4),
            "entailment": round(entailment, 4),
            "final_confidence": round(min(1.0, max(0.0, final)), 4),
        }

    def _corroboration_score(self, claim: Claim, all_claims: list[Claim]) -> int | float:
        count = 0
        for other in all_claims:
            if other.claim_id == claim.claim_id or other.source_id == claim.source_id:
                continue
            if other.entity.strip().lower() != claim.entity.strip().lower() or other.metric != claim.metric:
                continue
            if claim.claim_type != ClaimType.NUMERIC:
                count += 1
                continue
            if (
                not other.normalized
                or other.normalized.magnitude is None
                or not claim.normalized
                or claim.normalized.magnitude is None
                or other.normalized.base_unit != claim.normalized.base_unit
            ):
                continue
            denom = max(abs(claim.normalized.magnitude), 1e-9)
            if abs(other.normalized.magnitude - claim.normalized.magnitude) / denom * 100 <= CORROBORATION_TOLERANCE_PCT:
                count += 1
        return min(1.0, 0.5 + 0.25 * count)
