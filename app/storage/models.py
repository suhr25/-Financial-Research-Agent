"""SQLAlchemy ORM models.

Design choice: each table stores its corresponding Pydantic model as a JSON
blob (`payload`) plus a handful of indexed columns needed for querying and
joins. This keeps the storage layer simple (single source of truth is the
Pydantic schema in app/schemas/, not a parallel hand-maintained ORM schema)
while still preserving the PRD's required conceptual separation between
sources / claims / evidence / verification_results / conflicts /
research_runs / reports as distinct tables.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.storage.database import Base


class ResearchRunORM(Base):
    __tablename__ = "research_runs"

    research_run_id: Mapped[str] = mapped_column(String, primary_key=True)
    query: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    payload: Mapped[dict] = mapped_column(JSON)


class SourceORM(Base):
    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    research_run_id: Mapped[str] = mapped_column(String, index=True)
    source_type: Mapped[str] = mapped_column(String)
    source_tier: Mapped[str] = mapped_column(String)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)
    payload: Mapped[dict] = mapped_column(JSON)


class ClaimORM(Base):
    __tablename__ = "claims"

    claim_id: Mapped[str] = mapped_column(String, primary_key=True)
    research_run_id: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    entity: Mapped[str] = mapped_column(String, index=True)
    metric: Mapped[str] = mapped_column(String, index=True)
    verification_status: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class EvidenceORM(Base):
    """Evidence is embedded inside Claim.evidence_span in the Pydantic model
    and inside VerificationResult, but is also persisted standalone here so
    it can be queried/audited independent of a claim (PRD section 8)."""

    __tablename__ = "evidence"

    evidence_id: Mapped[str] = mapped_column(String, primary_key=True)
    research_run_id: Mapped[str] = mapped_column(String, index=True)
    source_id: Mapped[str] = mapped_column(String, index=True)
    claim_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)


class VerificationResultORM(Base):
    __tablename__ = "verification_results"

    verification_id: Mapped[str] = mapped_column(String, primary_key=True)
    research_run_id: Mapped[str] = mapped_column(String, index=True)
    claim_id: Mapped[str] = mapped_column(String, index=True)
    final_verdict: Mapped[str] = mapped_column(String, index=True)
    payload: Mapped[dict] = mapped_column(JSON)


class ConflictORM(Base):
    __tablename__ = "conflicts"

    conflict_id: Mapped[str] = mapped_column(String, primary_key=True)
    research_run_id: Mapped[str] = mapped_column(String, index=True)
    entity: Mapped[str] = mapped_column(String, index=True)
    metric: Mapped[str] = mapped_column(String, index=True)
    is_genuine_conflict: Mapped[bool] = mapped_column()
    payload: Mapped[dict] = mapped_column(JSON)


class ReportORM(Base):
    __tablename__ = "reports"

    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    research_run_id: Mapped[str] = mapped_column(String, index=True, unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
