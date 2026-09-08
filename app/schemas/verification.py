from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.enums import VerificationVerdict


class NumericMatchResult(BaseModel):
    """Output of the deterministic NumericMatcher. Only applies to numeric
    claims; qualitative claims skip straight to the EntailmentChecker."""

    applicable: bool
    exact_match: bool = False
    normalized_match: bool = False
    percent_difference: float | None = None
    period_match: bool | None = None
    basis_match: bool | None = None
    unit_currency_converted: bool = False
    notes: str = ""


class EntailmentResult(BaseModel):
    """Structured output of the LLM EntailmentChecker.

    Critically: the checker is given ONLY the claim + the raw source
    evidence text - never the final generated report - so it cannot simply
    grade the report's own homework (PRD 5.1.4 / section 12).
    """

    verdict: VerificationVerdict
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class VerificationResult(BaseModel):
    """Combined result of the dual-path VerificationEngine for one claim."""

    claim_id: str
    numeric_result: NumericMatchResult | None = None
    entailment_result: EntailmentResult
    final_verdict: VerificationVerdict
    combined_reason: str
