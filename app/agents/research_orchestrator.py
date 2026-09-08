"""Research Orchestrator: drives the full pipeline shown in the PRD's
high-level design diagram end to end for one query, and owns the bounded
follow-up loop (PRD section 16 / risk 5.1.3 "unbounded iterations").

Query -> Plan -> Retrieve -> Extract -> Normalize -> Verify -> Score ->
Conflict-detect -> [sufficiency check -> follow-up retrieve/extract/verify/
score, up to max_followup_iterations] -> Report -> persist everything.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.followup_research import FollowupResearch
from app.agents.query_planner import QueryPlanner
from app.analysis.conflict_detector import ConflictDetector
from app.analysis.confidence_scorer import ConfidenceScorer
from app.analysis.normalizer import ClaimNormalizer
from app.config import get_settings
from app.extraction.claim_extractor import ClaimExtractor
from app.generation.report_generator import ReportGenerator
from app.retrieval.source_retriever import SourceRetriever
from app.schemas import Claim, ResearchPlan, ResearchRun, ResearchStatus, Source, VerificationResult
from app.storage import repositories as repo
from app.verification.verification_engine import VerificationEngine

logger = logging.getLogger("financial_research_agent.agents.research_orchestrator")


class ResearchOrchestrator:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.query_planner = QueryPlanner()
        self.source_retriever = SourceRetriever()
        self.claim_extractor = ClaimExtractor()
        self.normalizer = ClaimNormalizer()
        self.verification_engine = VerificationEngine()
        self.conflict_detector = ConflictDetector()
        self.confidence_scorer = ConfidenceScorer()
        self.report_generator = ReportGenerator()
        self.followup_research = FollowupResearch()

    def run(self, query: str) -> ResearchRun:
        run = ResearchRun(query=query, status=ResearchStatus.PLANNING)
        repo.save_research_run(self.db, run)
        logger.info("research_run_id=%s started query=%r", run.research_run_id, query)

        try:
            plan = self.query_planner.plan(query)
            run.plan = plan
            self._touch(run, ResearchStatus.RETRIEVING)

            if not plan.companies or not any(c.resolved for c in plan.companies):
                run.status = ResearchStatus.FAILED
                run.error = (
                    "Could not resolve any company from the query. "
                    "Try including a clearer company name or ticker."
                )
                self._touch(run, run.status)
                return run

            all_sources: list[Source] = list(self.source_retriever.retrieve(self.db, run.research_run_id, plan))
            run.research_queries_used += len(plan.sub_queries)

            self._touch(run, ResearchStatus.EXTRACTING)
            claims = self.claim_extractor.extract(run.research_run_id, all_sources, plan)
            claims = self.normalizer.normalize(claims)

            self._touch(run, ResearchStatus.VERIFYING)
            verifications = self._verify_and_score(claims, all_sources)

            claims, all_sources, verifications = self._followup_loop(run, plan, claims, all_sources, verifications)

            conflicts = self.conflict_detector.detect(claims)

            self._persist_pipeline_outputs(run.research_run_id, claims, verifications, conflicts)

            report = self.report_generator.generate(run.research_run_id, plan, claims, conflicts, all_sources)
            repo.save_report(self.db, run.research_run_id, report)

            run.status = ResearchStatus.COMPLETE
            self._touch(run, run.status)
            verdict_counts = {v: sum(1 for c in claims if c.verification_status and c.verification_status.value == v)
                               for v in ("supported", "contradicted", "insufficient")}
            logger.info(
                "research_run_id=%s complete: %d sources, %d claims (%s), %d conflicts, "
                "followup_iterations=%d, research_queries_used=%d",
                run.research_run_id, len(all_sources), len(claims), verdict_counts, len(conflicts),
                run.followup_iterations_used, run.research_queries_used,
            )
            return run
        except Exception as exc:  # noqa: BLE001
            logger.exception("research_run_id=%s failed", run.research_run_id)
            run.status = ResearchStatus.FAILED
            run.error = str(exc)
            self._touch(run, run.status)
            raise

    # ---- Follow-up loop (bounded) -----------------------------------------

    def _followup_loop(
        self,
        run: ResearchRun,
        plan: ResearchPlan,
        claims: list[Claim],
        sources: list[Source],
        verifications: dict[str, VerificationResult],
    ) -> tuple[list[Claim], list[Source], dict[str, VerificationResult]]:
        for _ in range(self.settings.max_followup_iterations):
            if run.research_queries_used >= self.settings.max_research_queries:
                logger.info("research_run_id=%s: max_research_queries reached, stopping follow-up loop", run.research_run_id)
                break

            sufficient, followup_sub_queries, reasoning = self.followup_research.assess(plan, claims)
            if sufficient or not followup_sub_queries:
                logger.info("research_run_id=%s: evidence deemed sufficient (%s)", run.research_run_id, reasoning)
                break

            self._touch(run, ResearchStatus.FOLLOWUP)
            run.followup_iterations_used += 1

            budget_left = self.settings.max_research_queries - run.research_queries_used
            followup_sub_queries = followup_sub_queries[: max(0, budget_left)]
            if not followup_sub_queries:
                break

            followup_plan = plan.model_copy(update={"sub_queries": followup_sub_queries, "companies": plan.companies})
            new_sources = self.source_retriever.retrieve(self.db, run.research_run_id, followup_plan)
            run.research_queries_used += len(followup_sub_queries)

            if not new_sources:
                logger.info("research_run_id=%s: follow-up retrieval returned no new sources, stopping", run.research_run_id)
                break

            new_claims = self.claim_extractor.extract(run.research_run_id, new_sources, plan)
            new_claims = self.normalizer.normalize(new_claims)
            new_verifications = self._verify_and_score(new_claims, new_sources)

            claims = claims + new_claims
            sources = sources + new_sources
            verifications.update(new_verifications)

        self._touch(run, ResearchStatus.VERIFYING)
        return claims, sources, verifications

    # ---- Shared helpers -----------------------------------------------------

    def _verify_and_score(self, claims: list[Claim], sources: list[Source]) -> dict[str, VerificationResult]:
        sources_by_id = {s.source_id: s for s in sources}
        verifications: dict[str, VerificationResult] = {}
        for claim in claims:
            result = self.verification_engine.verify(claim)
            verifications[claim.claim_id] = result
            claim.verification_status = result.final_verdict
            claim.verification_reason = result.combined_reason
        self.confidence_scorer.score_all(claims, verifications, sources_by_id)
        return verifications

    def _persist_pipeline_outputs(self, research_run_id, claims, verifications, conflicts):
        for claim in claims:
            repo.save_claim(self.db, research_run_id, claim)
        for verification in verifications.values():
            repo.save_verification_result(self.db, research_run_id, verification)
        for conflict in conflicts:
            repo.save_conflict(self.db, research_run_id, conflict)

    def _touch(self, run: ResearchRun, status: ResearchStatus) -> None:
        run.status = status
        run.updated_at = datetime.now(timezone.utc)
        repo.save_research_run(self.db, run)
