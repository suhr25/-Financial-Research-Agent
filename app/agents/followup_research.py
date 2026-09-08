"""Follow-Up Research Loop decision module (PRD section 16).

Answers two questions the PRD explicitly wants an LLM for when available:
"is the evidence gathered so far sufficient to answer the research
question?" and "if not, what should we search for next?". The actual
iteration loop (bounded by max_followup_iterations / max_research_queries)
lives in ResearchOrchestrator - this module only makes the sufficiency
judgement and proposes targeted sub-queries for one round.

Mock path is a deterministic rule: any claim whose metric was explicitly
requested (or is a core financial metric) and came back INSUFFICIENT
triggers a follow-up query for that exact metric/entity/period.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.llm import LLMProvider, get_llm_provider
from app.schemas import Claim, ResearchPlan, SourceType, SubQuery, VerificationVerdict

logger = logging.getLogger("financial_research_agent.agents.followup_research")

CORE_METRICS = {"revenue", "net_income", "operating_margin", "operating_income", "risk_factor"}


class _FollowupQueryDraft(BaseModel):
    text: str
    purpose: str


class _SufficiencyOutput(BaseModel):
    sufficient: bool
    reasoning: str
    followup_queries: list[_FollowupQueryDraft] = Field(default_factory=list)


SUFFICIENCY_SYSTEM_PROMPT = """You are the evidence-sufficiency judge in an agentic financial research pipeline.
You will be given the original research plan/question and the list of claims extracted so far, each with
its verification verdict (SUPPORTED / CONTRADICTED / INSUFFICIENT) and confidence.

Decide: is there sufficient SUPPORTED evidence to answer the user's research question? If any explicitly
requested metric or question has no SUPPORTED claim backing it (i.e. it is missing or only INSUFFICIENT/
CONTRADICTED claims exist for it), mark sufficient=false and propose up to 3 short, targeted follow-up
search queries (each with a purpose label) that would plausibly find that missing evidence. Do not propose
follow-ups for things that already have solid SUPPORTED evidence.
"""


class FollowupResearch:
    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm if llm is not None else get_llm_provider()

    def assess(self, plan: ResearchPlan, claims: list[Claim]) -> tuple[bool, list[SubQuery], str]:
        """Returns (sufficient, followup_sub_queries, reasoning)."""
        if self.llm is not None:
            try:
                return self._llm_assess(plan, claims)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM sufficiency check failed (%s); using rule-based fallback", exc)
        return self._rule_based_assess(plan, claims)

    def _llm_assess(self, plan: ResearchPlan, claims: list[Claim]) -> tuple[bool, list[SubQuery], str]:
        claim_lines = "\n".join(
            f"- entity={c.entity} metric={c.metric} value={c.value}{c.unit or ''} period={c.period} "
            f"verdict={c.verification_status.value if c.verification_status else 'unknown'} "
            f"confidence={c.confidence if c.confidence is not None else 'n/a'}"
            for c in claims
        )
        user_prompt = (
            f"RESEARCH QUERY: {plan.raw_query}\n"
            f"Requested metrics: {plan.requested_metrics}\n"
            f"Financial questions: {plan.financial_questions}\n"
            f"Risk questions: {plan.risk_questions}\n\n"
            f"CLAIMS SO FAR:\n{claim_lines or '(none)'}"
        )
        output = self.llm.complete_json(
            system=SUFFICIENCY_SYSTEM_PROMPT, user=user_prompt, schema_model=_SufficiencyOutput, max_tokens=800
        )
        sub_queries = [
            SubQuery(text=q.text, purpose=q.purpose, target_source_types=[SourceType.WEB_ARTICLE, SourceType.FINANCIAL_API], is_followup=True)
            for q in output.followup_queries
        ]
        if not output.sufficient and not sub_queries:
            # Safety net: LLM said insufficient but gave nothing to search for - fall back to rules.
            _, sub_queries, _ = self._rule_based_assess(plan, claims)
        return output.sufficient, sub_queries, output.reasoning

    def _rule_based_assess(self, plan: ResearchPlan, claims: list[Claim]) -> tuple[bool, list[SubQuery], str]:
        watched_metrics = CORE_METRICS | set(plan.requested_metrics)
        gaps: dict[tuple[str, str], Claim] = {}
        for c in claims:
            if c.metric not in watched_metrics:
                continue
            key = (c.entity, c.metric)
            if c.verification_status == VerificationVerdict.SUPPORTED:
                gaps.pop(key, None)
            elif key not in gaps:
                gaps[key] = c

        if not gaps:
            return True, [], "All watched metrics have at least one SUPPORTED claim."

        sub_queries = []
        for (entity, metric), c in gaps.items():
            period_part = f" {c.period}" if c.period else ""
            sub_queries.append(
                SubQuery(
                    text=f"{entity}{period_part} {metric.replace('_', ' ')}",
                    purpose=metric,
                    target_source_types=[SourceType.WEB_ARTICLE, SourceType.FINANCIAL_API],
                    is_followup=True,
                )
            )
        return False, sub_queries, f"{len(gaps)} watched metric(s) lack SUPPORTED evidence: {[m for _, m in gaps]}."
