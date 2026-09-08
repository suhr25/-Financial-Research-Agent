"""Repository layer: translates between Pydantic schemas (app/schemas/) and
ORM rows (app/storage/models.py). Every other module in the app talks to
storage exclusively through these functions - nobody else touches the ORM
or writes raw SQL.
"""
from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.schemas import (
    Claim,
    Conflict,
    Evidence,
    Report,
    ResearchRun,
    Source,
    VerificationResult,
)
from app.storage.models import (
    ClaimORM,
    ConflictORM,
    EvidenceORM,
    ReportORM,
    ResearchRunORM,
    SourceORM,
    VerificationResultORM,
)


def _dump(model) -> dict:
    return json.loads(model.model_dump_json())


# ---- Research runs ----------------------------------------------------

def save_research_run(db: Session, run: ResearchRun) -> None:
    existing = db.get(ResearchRunORM, run.research_run_id)
    payload = _dump(run)
    if existing:
        existing.status = run.status.value
        existing.updated_at = run.updated_at
        existing.payload = payload
    else:
        db.add(
            ResearchRunORM(
                research_run_id=run.research_run_id,
                query=run.query,
                status=run.status.value,
                created_at=run.created_at,
                updated_at=run.updated_at,
                payload=payload,
            )
        )
    db.commit()


def get_research_run(db: Session, research_run_id: str) -> ResearchRun | None:
    row = db.get(ResearchRunORM, research_run_id)
    return ResearchRun.model_validate(row.payload) if row else None


# ---- Sources ------------------------------------------------------------

def save_source(db: Session, research_run_id: str, source: Source) -> None:
    db.add(
        SourceORM(
            source_id=source.source_id,
            research_run_id=research_run_id,
            source_type=source.source_type.value,
            source_tier=source.source_tier.value,
            retrieved_at=source.retrieved_at,
            payload=_dump(source),
        )
    )
    db.commit()


def get_sources_for_run(db: Session, research_run_id: str) -> list[Source]:
    rows = db.scalars(select(SourceORM).where(SourceORM.research_run_id == research_run_id)).all()
    return [Source.model_validate(r.payload) for r in rows]


def get_source(db: Session, source_id: str) -> Source | None:
    row = db.get(SourceORM, source_id)
    return Source.model_validate(row.payload) if row else None


# ---- Claims ---------------------------------------------------------------

def save_claim(db: Session, research_run_id: str, claim: Claim) -> None:
    db.merge(
        ClaimORM(
            claim_id=claim.claim_id,
            research_run_id=research_run_id,
            source_id=claim.source_id,
            entity=claim.entity,
            metric=claim.metric,
            verification_status=claim.verification_status.value if claim.verification_status else None,
            confidence=claim.confidence,
            payload=_dump(claim),
        )
    )
    db.commit()
    save_evidence(db, research_run_id, claim.source_id, claim.claim_id, claim.evidence_span)


def get_claims_for_run(db: Session, research_run_id: str) -> list[Claim]:
    rows = db.scalars(select(ClaimORM).where(ClaimORM.research_run_id == research_run_id)).all()
    return [Claim.model_validate(r.payload) for r in rows]


def get_claim(db: Session, claim_id: str) -> Claim | None:
    row = db.get(ClaimORM, claim_id)
    return Claim.model_validate(row.payload) if row else None


# ---- Evidence ---------------------------------------------------------------

def save_evidence(
    db: Session, research_run_id: str, source_id: str, claim_id: str | None, evidence: Evidence
) -> None:
    db.add(
        EvidenceORM(
            evidence_id=f"ev_{uuid4().hex[:12]}",
            research_run_id=research_run_id,
            source_id=source_id,
            claim_id=claim_id,
            payload=_dump(evidence),
        )
    )
    db.commit()


# ---- Verification results --------------------------------------------------

def save_verification_result(db: Session, research_run_id: str, result: VerificationResult) -> None:
    db.add(
        VerificationResultORM(
            verification_id=f"ver_{uuid4().hex[:12]}",
            research_run_id=research_run_id,
            claim_id=result.claim_id,
            final_verdict=result.final_verdict.value,
            payload=_dump(result),
        )
    )
    db.commit()


def get_verification_results_for_run(db: Session, research_run_id: str) -> list[VerificationResult]:
    rows = db.scalars(
        select(VerificationResultORM).where(VerificationResultORM.research_run_id == research_run_id)
    ).all()
    return [VerificationResult.model_validate(r.payload) for r in rows]


# ---- Conflicts ------------------------------------------------------------

def save_conflict(db: Session, research_run_id: str, conflict: Conflict) -> None:
    db.add(
        ConflictORM(
            conflict_id=conflict.conflict_id,
            research_run_id=research_run_id,
            entity=conflict.entity,
            metric=conflict.metric,
            is_genuine_conflict=conflict.is_genuine_conflict,
            payload=_dump(conflict),
        )
    )
    db.commit()


def get_conflicts_for_run(db: Session, research_run_id: str) -> list[Conflict]:
    rows = db.scalars(select(ConflictORM).where(ConflictORM.research_run_id == research_run_id)).all()
    return [Conflict.model_validate(r.payload) for r in rows]


# ---- Reports ------------------------------------------------------------

def save_report(db: Session, research_run_id: str, report: Report) -> None:
    existing = db.scalar(select(ReportORM).where(ReportORM.research_run_id == research_run_id))
    payload = _dump(report)
    if existing:
        existing.payload = payload
    else:
        db.add(ReportORM(report_id=report.report_id, research_run_id=research_run_id, payload=payload))
    db.commit()


def get_report_for_run(db: Session, research_run_id: str) -> Report | None:
    row = db.scalar(select(ReportORM).where(ReportORM.research_run_id == research_run_id))
    return Report.model_validate(row.payload) if row else None
