from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.schemas import Claim, Conflict, ResearchRun, Source
from app.storage import repositories as repo
from app.storage.database import get_session

logger = logging.getLogger("financial_research_agent.api")

router = APIRouter()


def db_session():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


class ResearchRequest(BaseModel):
    query: str


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "demo_mode": settings.effective_demo_mode,
        "llm_provider": settings.llm_provider,
        "llm_available": settings.llm_available,
        "search_provider": settings.search_provider,
        "search_available": settings.search_available,
    }


@router.post("/research", response_model=ResearchRun)
def start_research(req: ResearchRequest, db: Session = Depends(db_session)):
    from app.agents.research_orchestrator import ResearchOrchestrator

    orchestrator = ResearchOrchestrator(db)
    try:
        run = orchestrator.run(req.query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Research run failed for query=%r", req.query)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return run


@router.get("/research/{research_id}", response_model=ResearchRun)
def get_research(research_id: str, db: Session = Depends(db_session)):
    run = repo.get_research_run(db, research_id)
    if not run:
        raise HTTPException(status_code=404, detail="research run not found")
    return run


@router.get("/research/{research_id}/claims", response_model=list[Claim])
def get_research_claims(research_id: str, db: Session = Depends(db_session)):
    return repo.get_claims_for_run(db, research_id)


@router.get("/research/{research_id}/sources", response_model=list[Source])
def get_research_sources(research_id: str, db: Session = Depends(db_session)):
    return repo.get_sources_for_run(db, research_id)


@router.get("/research/{research_id}/conflicts", response_model=list[Conflict])
def get_research_conflicts(research_id: str, db: Session = Depends(db_session)):
    return repo.get_conflicts_for_run(db, research_id)


@router.get("/research/{research_id}/report")
def get_research_report(research_id: str, db: Session = Depends(db_session)):
    report = repo.get_report_for_run(db, research_id)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report
