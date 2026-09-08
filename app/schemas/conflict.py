from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.enums import ConflictReasonType


class Conflict(BaseModel):
    """A detected disagreement between two claims about the same
    entity+metric+period (PRD section 13). `reason_type` distinguishes a
    genuine numeric disagreement from an explainable basis/period/unit
    mismatch - the system must not blindly report the latter as a
    contradiction."""

    conflict_id: str = Field(default_factory=lambda: f"cfl_{uuid4().hex[:12]}")
    entity: str
    metric: str
    claim_id_a: str
    claim_id_b: str
    source_id_a: str
    source_id_b: str
    value_a: str
    value_b: str
    reason_type: ConflictReasonType
    explanation: str
    is_genuine_conflict: bool
