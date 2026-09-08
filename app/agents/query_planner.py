"""Query Planner: decomposes a free-text research query into a structured
ResearchPlan (PRD section 6).

Real path: an LLM extracts company mentions, period, requested metrics, and
question categories, and drafts targeted sub-queries. Company name strings
are then resolved to CompanyEntity objects via CompanyResolver - the LLM
never invents a ticker/CIK itself.

Mock path (DEMO_MODE / no LLM key): deterministic regex + directory-lookup
heuristics produce a plan of the same shape from a fixed sub-query template.
This is intentionally a weaker fallback than the real LLM path; it exists so
the full pipeline stays runnable and demonstrable without any API key.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.llm import LLMProvider, get_llm_provider
from app.retrieval.company_resolver import CompanyResolver
from app.schemas import CompanyEntity, ResearchPlan, SourceType, SubQuery

logger = logging.getLogger("financial_research_agent.agents.query_planner")

PERIOD_RE = re.compile(r"\b(Q[1-4]\s?20\d{2}|FY\s?20\d{2}|20\d{2})\b", re.IGNORECASE)

METRIC_KEYWORDS = {
    "revenue": "revenue",
    "sales": "revenue",
    "profit": "profitability",
    "profitability": "profitability",
    "margin": "operating_margin",
    "net income": "net_income",
    "earnings": "earnings",
    "eps": "eps",
    "cash": "cash_position",
    "debt": "debt",
    "growth": "growth",
    "ebitda": "ebitda",
}

RISK_KEYWORDS = ("risk", "risks", "headwind", "challenge", "exposure")


class _SubQueryDraft(BaseModel):
    text: str
    purpose: str
    company: str | None = Field(default=None, description="Which company_names entry this sub-query targets, if applicable")


class _PlannerLLMOutput(BaseModel):
    company_names: list[str] = Field(default_factory=list, description="Company names or tickers mentioned")
    period: str | None = None
    is_comparison: bool = False
    requested_metrics: list[str] = Field(default_factory=list)
    financial_questions: list[str] = Field(default_factory=list)
    qualitative_questions: list[str] = Field(default_factory=list)
    risk_questions: list[str] = Field(default_factory=list)
    sub_queries: list[_SubQueryDraft] = Field(default_factory=list)


PLANNER_SYSTEM_PROMPT = """You are the Query Planner of a financial research agent.
Given a user's research query about one or more public or private companies, extract a
structured research plan. Identify:
- every company name or ticker mentioned (do not invent tickers/CIKs, just names as written)
- the reporting period if any (e.g. "Q3 2024", "FY2024") - null if not specified
- whether this is a multi-company comparison request
- requested financial metrics (e.g. revenue, net_income, operating_margin, eps, cash_position, debt, ebitda, growth)
- distinct financial questions, qualitative questions (strategy/business developments), and risk-related questions implied by the query
- 4 to 6 targeted sub-queries suitable for a web/financial search engine that would help answer the request,
  each with a short "purpose" label (e.g. "revenue", "risks", "operating_margin") and, for a multi-company
  request, which company (matching one of the extracted company_names) it targets

Do not force a rigid structure if the query does not fit it (e.g. a broad "analyze X" query implies revenue,
profitability, and risk sub-queries even if not explicitly asked).
"""


class QueryPlanner:
    def __init__(self, llm: LLMProvider | None = None, resolver: CompanyResolver | None = None):
        self.llm = llm if llm is not None else get_llm_provider()
        self.resolver = resolver or CompanyResolver()

    def plan(self, query: str) -> ResearchPlan:
        if self.llm is None:
            return self._mock_plan(query)
        try:
            return self._llm_plan(query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM query planning failed (%s); falling back to mock planner", exc)
            return self._mock_plan(query)

    # ---- Real path -----------------------------------------------------

    def _llm_plan(self, query: str) -> ResearchPlan:
        extraction = self.llm.complete_json(
            system=PLANNER_SYSTEM_PROMPT,
            user=f"User query: {query}",
            schema_model=_PlannerLLMOutput,
        )
        companies = [self.resolver.resolve(name) for name in extraction.company_names]
        # Map the LLM's raw company_names strings to resolved canonical names,
        # so a sub-query's `company` field lines up with CompanyEntity.name -
        # this is what lets claim extraction attribute claims to the right
        # company in multi-company (comparison) queries.
        raw_to_resolved = {raw: entity.name for raw, entity in zip(extraction.company_names, companies)}

        sub_queries = [
            SubQuery(
                text=sq.text,
                purpose=sq.purpose,
                target_source_types=_source_types_for_purpose(sq.purpose),
                company=raw_to_resolved.get(sq.company, sq.company),
            )
            for sq in extraction.sub_queries
        ]

        return ResearchPlan(
            raw_query=query,
            companies=companies,
            period=extraction.period,
            requested_metrics=extraction.requested_metrics,
            financial_questions=extraction.financial_questions,
            qualitative_questions=extraction.qualitative_questions,
            risk_questions=extraction.risk_questions,
            required_source_types=[],
            sub_queries=sub_queries,
            is_comparison=extraction.is_comparison or len(companies) > 1,
        )

    # ---- Mock path -------------------------------------------------------

    def _mock_plan(self, query: str) -> ResearchPlan:
        mentioned_names = self.resolver.find_mentions(query)
        companies = [self.resolver.resolve(name) for name in mentioned_names]

        period_match = PERIOD_RE.search(query)
        period = period_match.group(1).replace(" ", "") if period_match else None
        if period:
            period = re.sub(r"^(Q[1-4])(\d{4})$", r"\1 \2", period, flags=re.IGNORECASE)
            period = re.sub(r"^FY(\d{4})$", r"FY \1", period, flags=re.IGNORECASE)

        lowered = query.lower()
        requested_metrics = sorted({v for k, v in METRIC_KEYWORDS.items() if k in lowered})
        risk_questions = [f"What are the major risks for {c.name}?" for c in companies] if any(
            k in lowered for k in RISK_KEYWORDS
        ) or not requested_metrics else []
        financial_questions = [f"What is {c.name}'s financial performance for {period or 'the most recent period'}?" for c in companies]

        is_comparison = "compare" in lowered or len(companies) > 1

        sub_queries: list[SubQuery] = []
        for company in companies:
            period_suffix = f" {period}" if period else ""
            for purpose, label in (
                ("revenue", "revenue"), ("net_income", "net income"),
                ("operating_margin", "operating margin"), ("risks", "major risks"),
            ):
                sub_queries.append(SubQuery(
                    text=f"{company.name}{period_suffix} {label}", purpose=purpose,
                    target_source_types=_source_types_for_purpose(purpose), company=company.name,
                ))

        from app.config import get_settings

        # Cap scales with company count so comparison queries don't have one
        # company's sub-queries silently dropped in favour of another's.
        max_sub = get_settings().max_subqueries_per_plan * max(1, len(companies))
        sub_queries = sub_queries[:max_sub] if sub_queries else sub_queries

        return ResearchPlan(
            raw_query=query,
            companies=companies,
            period=period,
            requested_metrics=requested_metrics,
            financial_questions=financial_questions,
            qualitative_questions=[],
            risk_questions=risk_questions,
            required_source_types=[],
            sub_queries=sub_queries,
            is_comparison=is_comparison,
        )


def _source_types_for_purpose(purpose: str) -> list[SourceType]:
    purpose = purpose.lower()
    if purpose in ("risks", "strategy", "qualitative", "commentary"):
        return [SourceType.WEB_ARTICLE]
    return [SourceType.SEC_FILING, SourceType.FINANCIAL_API, SourceType.WEB_ARTICLE]
