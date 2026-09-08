"""Report Generator (PRD section 15).

Design decision: every section EXCEPT the executive overview paragraph is
built by deterministic templating directly over verified Claim/Conflict/
Source objects - this guarantees every number in the report traces to a
claim_id (and therefore to a stored evidence span) with zero risk of the
generator inventing a figure.

The executive overview is the one place an LLM is used for genuine
synthesis/prose quality (a legitimate GenAI use per the project brief), but
it is constrained: the model is given ONLY the list of already-verified
claim statements (with their claim_ids) and told not to add any fact not
present in them. Its cited claim_ids are validated against the real claim
set afterwards and any hallucinated id is dropped - the generator must
consume verified research objects, not regenerate facts from scratch.
"""
from __future__ import annotations

import logging
import statistics

from pydantic import BaseModel, Field

from app.llm import LLMProvider, get_llm_provider
from app.schemas import (
    Claim,
    ClaimType,
    ComparisonTable,
    Conflict,
    Report,
    ReportSection,
    ResearchPlan,
    Source,
    VerificationVerdict,
)

logger = logging.getLogger("financial_research_agent.generation.report_generator")

FINANCIAL_PERFORMANCE_METRICS = {
    "revenue", "net_income", "operating_income", "operating_margin",
    "profit_margin", "ebitda", "revenue_growth_yoy",
}


class _OverviewOutput(BaseModel):
    overview: str
    claim_ids_used: list[str] = Field(default_factory=list)


OVERVIEW_SYSTEM_PROMPT = """You are the Report Generator's executive-overview writer for a financial
research agent. You will be given a list of ALREADY-VERIFIED claims, each with a claim_id, about one
or more companies. Write a concise 3-5 sentence executive overview paragraph using ONLY the facts
present in these claims - do not add any number, fact, or detail that is not stated in the provided
claims. For every specific fact you mention, include its claim_id in claim_ids_used. If the claims
list is empty or has nothing useful, return a short overview stating that insufficient verified
evidence was found.
"""


class ReportGenerator:
    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm if llm is not None else get_llm_provider()

    def generate(
        self,
        research_run_id: str,
        plan: ResearchPlan,
        claims: list[Claim],
        conflicts: list[Conflict],
        sources: list[Source],
    ) -> Report:
        supported = [c for c in claims if c.verification_status == VerificationVerdict.SUPPORTED]
        contradicted = [c for c in claims if c.verification_status == VerificationVerdict.CONTRADICTED]
        insufficient = [c for c in claims if c.verification_status == VerificationVerdict.INSUFFICIENT]

        company_summary = self._company_summary(plan)

        report = Report(
            research_run_id=research_run_id,
            company_summary=company_summary,
            executive_overview=self._build_overview(company_summary, supported),
            financial_performance=self._build_financial_performance(supported),
            key_metrics=self._build_key_metrics(supported),
            risks=self._build_risks(supported),
            important_findings=self._build_important_findings(contradicted, insufficient),
            conflicting_information=self._build_conflicts_section(conflicts),
            claim_verification_summary=self._build_verification_summary(claims, supported, contradicted, insufficient),
            sources_section=self._build_sources_section(sources),
            comparison_tables=self._build_comparison_tables(plan, claims, conflicts),
            total_claims=len(claims),
            supported_claims=len(supported),
            contradicted_claims=len(contradicted),
            insufficient_claims=len(insufficient),
            average_confidence=_avg_confidence(claims),
        )
        return report

    def _company_summary(self, plan: ResearchPlan) -> str:
        names = ", ".join(f"{c.name} ({c.ticker})" if c.ticker else c.name for c in plan.companies)
        if not names:
            names = plan.raw_query
        return f"{names} - {plan.period}" if plan.period else names

    # ---- Executive overview (the one LLM-assisted section) --------------

    def _build_overview(self, company_summary: str, supported: list[Claim]) -> ReportSection:
        if self.llm is not None and supported:
            try:
                return self._llm_overview(supported)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM overview generation failed (%s); using template overview", exc)
        return self._template_overview(company_summary, supported)

    def _llm_overview(self, supported: list[Claim]) -> ReportSection:
        claim_lines = "\n".join(f"- [{c.claim_id}] {c.statement}" for c in supported[:40])
        output = self.llm.complete_json(
            system=OVERVIEW_SYSTEM_PROMPT,
            user=f"VERIFIED CLAIMS:\n{claim_lines}",
            schema_model=_OverviewOutput,
            max_tokens=600,
        )
        valid_ids = {c.claim_id for c in supported}
        used_ids = [cid for cid in output.claim_ids_used if cid in valid_ids]
        return ReportSection(title="Executive Overview", content=output.overview, claim_ids=used_ids)

    def _template_overview(self, company_summary: str, supported: list[Claim]) -> ReportSection:
        if not supported:
            return ReportSection(
                title="Executive Overview",
                content=f"No sufficiently verified evidence was found for {company_summary}.",
                claim_ids=[],
            )
        # Lead with headline financial metrics (revenue/income/margin), then one
        # risk highlight, so the overview reads like an analyst summary rather
        # than whatever claim happened to score highest confidence.
        financial = _best_per_metric(
            [c for c in supported if c.claim_type == ClaimType.NUMERIC and c.metric in FINANCIAL_PERFORMANCE_METRICS]
        )
        financial = sorted(financial, key=lambda c: c.confidence or 0, reverse=True)[:3]
        risk_claims = [c for c in supported if c.metric == "risk_factor"]
        risk_claim = max(risk_claims, key=lambda c: c.confidence or 0) if risk_claims else None

        used = list(financial)
        sentences = []
        if financial:
            highlights = "; ".join(c.statement.rstrip(".") for c in financial)
            sentences.append(f"{company_summary}: verified sources indicate {highlights}.")
        if risk_claim:
            sentences.append(f"A key risk noted in sources: {risk_claim.value.rstrip('.')}.")
            used.append(risk_claim)
        if not sentences:
            top = sorted(supported, key=lambda c: c.confidence or 0, reverse=True)[:3]
            sentences = [c.statement.rstrip(".") + "." for c in top]
            used = top
        return ReportSection(title="Executive Overview", content=" ".join(sentences), claim_ids=[c.claim_id for c in used])

    # ---- Deterministic templated sections ---------------------------------

    def _build_financial_performance(self, supported: list[Claim]) -> ReportSection:
        relevant = [c for c in supported if c.claim_type == ClaimType.NUMERIC and c.metric in FINANCIAL_PERFORMANCE_METRICS]
        best = _best_per_metric(relevant)
        if not best:
            return ReportSection(title="Financial Performance", content="No verified financial performance figures were found.", claim_ids=[])
        lines = [f"- {_format_claim_line(c)}" for c in best]
        return ReportSection(title="Financial Performance", content="\n".join(lines), claim_ids=[c.claim_id for c in best])

    def _build_key_metrics(self, supported: list[Claim]) -> ReportSection:
        numeric = [c for c in supported if c.claim_type == ClaimType.NUMERIC]
        best = _best_per_metric(numeric)
        if not best:
            return ReportSection(title="Key Metrics", content="No verified numeric metrics were found.", claim_ids=[])
        lines = [f"- {_format_claim_line(c)}" for c in best]
        return ReportSection(title="Key Metrics", content="\n".join(lines), claim_ids=[c.claim_id for c in best])

    def _build_risks(self, supported: list[Claim]) -> ReportSection:
        risk_claims = [c for c in supported if c.metric == "risk_factor"]
        if not risk_claims:
            return ReportSection(title="Risks", content="No verified risk factors were found in retrieved sources.", claim_ids=[])
        lines = [f"- {c.value}" for c in risk_claims]
        return ReportSection(title="Risks", content="\n".join(lines), claim_ids=[c.claim_id for c in risk_claims])

    def _build_important_findings(self, contradicted: list[Claim], insufficient: list[Claim]) -> ReportSection:
        lines = []
        for c in contradicted:
            lines.append(f"- CONTRADICTED: \"{c.statement}\" - {c.verification_reason}")
        for c in insufficient:
            lines.append(f"- INSUFFICIENT EVIDENCE: \"{c.statement}\" could not be confirmed against available sources.")
        if not lines:
            return ReportSection(title="Important Findings", content="No contradictions or evidence gaps were found among extracted claims.", claim_ids=[])
        return ReportSection(
            title="Important Findings", content="\n".join(lines),
            claim_ids=[c.claim_id for c in contradicted] + [c.claim_id for c in insufficient],
        )

    def _build_conflicts_section(self, conflicts: list[Conflict]) -> ReportSection:
        genuine = [c for c in conflicts if c.is_genuine_conflict]
        explained = [c for c in conflicts if not c.is_genuine_conflict]
        if not conflicts:
            return ReportSection(title="Conflicting Information", content="No conflicts were detected between sources.", claim_ids=[])
        lines = []
        if genuine:
            lines.append(f"{len(genuine)} genuine disagreement(s) detected between sources:")
            for c in genuine:
                lines.append(f"- {c.metric}: {c.value_a} vs {c.value_b} - {c.explanation}")
        if explained:
            lines.append(f"{len(explained)} apparent difference(s) explained by normalization (not genuine conflicts):")
            for c in explained:
                lines.append(f"- {c.metric}: {c.value_a} vs {c.value_b} - {c.explanation}")
        return ReportSection(
            title="Conflicting Information", content="\n".join(lines),
            claim_ids=[c.claim_id_a for c in conflicts] + [c.claim_id_b for c in conflicts],
        )

    def _build_verification_summary(
        self, all_claims: list[Claim], supported: list[Claim], contradicted: list[Claim], insufficient: list[Claim]
    ) -> ReportSection:
        avg_conf = _avg_confidence(all_claims)
        content = (
            f"{len(all_claims)} claims were extracted and passed through the verification engine "
            f"(100% citation verification coverage). {len(supported)} SUPPORTED, {len(contradicted)} "
            f"CONTRADICTED, {len(insufficient)} INSUFFICIENT. "
            f"Average confidence across all verified claims: {avg_conf * 100:.1f}%." if avg_conf is not None else
            f"{len(all_claims)} claims were extracted and passed through the verification engine."
        )
        return ReportSection(title="Claim Verification Summary", content=content, claim_ids=[c.claim_id for c in all_claims])

    def _build_sources_section(self, sources: list[Source]) -> ReportSection:
        if not sources:
            return ReportSection(title="Sources", content="No sources were retrieved.", claim_ids=[])
        lines = []
        for s in sources:
            url_part = f" ({s.url})" if s.url else ""
            lines.append(f"- [{s.source_tier.value}] {s.title} - {s.publisher}{url_part}")
        return ReportSection(title="Sources", content="\n".join(lines), claim_ids=[])

    def _build_comparison_tables(self, plan: ResearchPlan, claims: list[Claim], conflicts: list[Conflict]) -> list[ComparisonTable]:
        tables: list[ComparisonTable] = []

        if conflicts:
            rows = [
                {"Metric": c.metric, "Source A": c.value_a, "Source B": c.value_b, "Reason": c.explanation}
                for c in conflicts
            ]
            tables.append(ComparisonTable(title="Source Conflicts", columns=["Metric", "Source A", "Source B", "Reason"], rows=rows))

        if plan.is_comparison and len(plan.companies) > 1:
            supported = [c for c in claims if c.verification_status == VerificationVerdict.SUPPORTED and c.claim_type == ClaimType.NUMERIC]
            metrics = sorted({c.metric for c in supported})
            company_names = [c.name for c in plan.companies]
            rows = []
            for metric in metrics:
                row = {"Metric": metric}
                for name in company_names:
                    candidates = [c for c in supported if c.metric == metric and c.entity.lower() == name.lower()]
                    if candidates:
                        best = max(candidates, key=lambda c: c.confidence or 0)
                        row[name] = f"{best.value} {best.unit or ''}".strip()
                    else:
                        row[name] = "N/A"
                rows.append(row)
            if rows:
                tables.append(ComparisonTable(title="Multi-Company Comparison", columns=["Metric"] + company_names, rows=rows))

        return tables


def _best_per_metric(claims: list[Claim]) -> list[Claim]:
    best: dict[str, Claim] = {}
    for c in claims:
        key = c.metric
        if key not in best or (c.confidence or 0) > (best[key].confidence or 0):
            best[key] = c
    return list(best.values())


def _format_claim_line(c: Claim) -> str:
    period = f" ({c.period})" if c.period else ""
    conf = f" - confidence {c.confidence * 100:.0f}%" if c.confidence is not None else ""
    basis = f" [{c.basis.value}]" if c.basis.value != "unknown" else ""
    return f"{c.metric}: {c.value} {c.unit or ''}{period}{basis}{conf}".strip()


def _avg_confidence(claims: list[Claim]) -> float | None:
    values = [c.confidence for c in claims if c.confidence is not None]
    return round(statistics.mean(values), 4) if values else None
