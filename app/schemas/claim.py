from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.enums import Basis, ClaimType, PeriodType, VerificationVerdict
from app.schemas.source import Evidence


class NormalizedValue(BaseModel):
    """Deterministic normalization output for a numeric claim (PRD section 11).

    Converts things like "$1.2 billion" / "$1,200 million" / "Rs. 100 crore"
    into a single comparable magnitude so the ConflictDetector and
    NumericMatcher never have to guess at raw strings.
    """

    raw_value: str
    magnitude: float | None = None  # value expressed in `base_unit`
    base_unit: str | None = None  # e.g. "USD", "%", "count"
    scale_applied: str | None = None  # e.g. "billion->unit", "crore->unit"
    period_type: PeriodType = PeriodType.UNKNOWN
    period_label: str | None = None  # e.g. "Q3 2024", "FY2024"
    basis: Basis = Basis.UNKNOWN
    normalization_notes: str | None = None


class Claim(BaseModel):
    """Canonical claim schema (PRD section 9 / 3.2.3).

    entity/metric/value/unit/period/basis is the tuple used for conflict
    detection; the rest is provenance and verification bookkeeping.
    """

    claim_id: str = Field(default_factory=lambda: f"clm_{uuid4().hex[:12]}")
    research_run_id: str

    claim_type: ClaimType

    # Canonical tuple
    entity: str  # company name the claim is about
    metric: str  # e.g. "revenue", "net_income", "operating_margin", "risk_factor"
    value: str  # original textual value as extracted, e.g. "$85.8 billion"
    unit: str | None = None
    period: str | None = None  # original textual period, e.g. "Q3 2024"
    basis: Basis = Basis.UNKNOWN

    normalized: NormalizedValue | None = None

    # Provenance - the claim must point at real, stored source text.
    source_id: str
    evidence_span: Evidence

    # Verification bookkeeping (filled in by later pipeline stages)
    verification_status: VerificationVerdict | None = None
    verification_reason: str | None = None
    confidence: float | None = None
    confidence_breakdown: dict[str, float] | None = None

    # Free-text statement as it would appear in a report, used for display
    # and as the entailment checker's claim text.
    statement: str
