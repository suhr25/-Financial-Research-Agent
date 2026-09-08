"""Claim Extractor: pulls numeric and qualitative claims out of retrieved
Source documents into the canonical Claim schema (PRD section 10).

Hard rule enforced in both paths: a claim's evidence_span must point at text
that verbatim exists in the source's document_text. The LLM path asks the
model to quote evidence exactly and discards any claim whose quote cannot be
located in the source (never trusts an LLM-invented span). The mock path
never has this problem by construction - it extracts directly from regex
match spans in the real (mock-labelled) document_text.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.llm import LLMProvider, get_llm_provider
from app.retrieval.base import make_evidence
from app.schemas import Basis, Claim, ClaimType, Evidence, ResearchPlan, Source

logger = logging.getLogger("financial_research_agent.extraction.claim_extractor")

MAX_SOURCE_CHARS_FOR_LLM = 8000


class _ExtractedClaimDraft(BaseModel):
    claim_type: ClaimType
    entity: str
    metric: str
    value: str
    unit: str | None = None
    period: str | None = None
    basis: Basis = Basis.UNKNOWN
    statement: str
    quoted_evidence: str = Field(description="Exact verbatim substring copied from the source text")


class _ExtractionOutput(BaseModel):
    claims: list[_ExtractedClaimDraft] = Field(default_factory=list)


EXTRACTOR_SYSTEM_PROMPT = """You are the Claim Extractor of a financial research agent.
Given the text of ONE source document, extract every distinct factual claim about the
company/companies of interest that is EXPLICITLY stated in the text - do not infer or
invent anything not present.

Extract two kinds of claims:
- numeric claims: revenue, net income, EPS, operating margin, EBITDA, growth rates, debt,
  cash, and similar financial metrics, with their value, unit, period and basis (GAAP /
  non-GAAP / adjusted) if stated or implied by nearby text.
- qualitative claims: major risks, strategic changes, management commentary, business
  developments.

For every single claim, `quoted_evidence` MUST be an exact, verbatim, character-for-character
substring copied from the SOURCE TEXT below (not paraphrased, not summarized) that supports the
claim - this will be programmatically located in the source text, so it must match exactly.
If the source contains nothing relevant, return an empty claims list.
"""


class ClaimExtractor:
    def __init__(self, llm: LLMProvider | None = None):
        self.llm = llm if llm is not None else get_llm_provider()

    def extract(self, research_run_id: str, sources: list[Source], plan: ResearchPlan) -> list[Claim]:
        claims: list[Claim] = []
        for source in sources:
            if self.llm is not None:
                try:
                    claims.extend(self._llm_extract(research_run_id, source, plan))
                    continue
                except Exception as exc:  # noqa: BLE001
                    logger.warning("LLM claim extraction failed for source=%s (%s); using mock extractor", source.source_id, exc)
            claims.extend(self._mock_extract(research_run_id, source, plan))
        return claims

    # ---- Real path -----------------------------------------------------

    def _llm_extract(self, research_run_id: str, source: Source, plan: ResearchPlan) -> list[Claim]:
        entities = ", ".join(c.name for c in plan.companies) or "the company/companies mentioned"
        company_hint = source.metadata.get("company_name")
        text = source.document_text[:MAX_SOURCE_CHARS_FOR_LLM]
        user_prompt = (
            f"Companies of interest: {entities}\n"
            + (f"This specific source was retrieved for: {company_hint}\n" if company_hint else "")
            + f"Requested period: {plan.period or 'not specified'}\n\n"
            f"SOURCE TITLE: {source.title}\n"
            f"SOURCE PUBLISHER: {source.publisher}\n"
            f"SOURCE TEXT:\n{text}"
        )
        output = self.llm.complete_json(
            system=EXTRACTOR_SYSTEM_PROMPT, user=user_prompt, schema_model=_ExtractionOutput, max_tokens=3000
        )

        claims: list[Claim] = []
        for draft in output.claims:
            evidence = make_evidence(source, draft.quoted_evidence)
            if evidence is None:
                logger.warning(
                    "Discarding LLM-extracted claim with unlocatable evidence quote in source=%s: %r",
                    source.source_id, draft.quoted_evidence[:120],
                )
                continue
            claims.append(_build_claim(research_run_id, source, draft, evidence))
        return claims

    # ---- Mock path -------------------------------------------------------

    def _mock_extract(self, research_run_id: str, source: Source, plan: ResearchPlan) -> list[Claim]:
        entity = _resolve_entity_for_source(source, plan)
        claims: list[Claim] = []
        seen_metrics: set[str] = set()

        for metric, matched_text, num, unit, start, end, basis in _extract_numeric_matches(source.document_text):
            if metric in seen_metrics:
                continue
            seen_metrics.add(metric)
            evidence = Evidence(source_id=source.source_id, start_char=start, end_char=end, evidence_text=matched_text)
            claims.append(
                Claim(
                    research_run_id=research_run_id,
                    claim_type=ClaimType.NUMERIC,
                    entity=entity,
                    metric=metric,
                    value=num,
                    unit=unit or None,
                    period=plan.period,
                    basis=basis,
                    source_id=source.source_id,
                    evidence_span=evidence,
                    statement=matched_text.strip().rstrip("."),
                )
            )

        for sentence, start, end in _extract_risk_sentences(source.document_text):
            evidence = Evidence(source_id=source.source_id, start_char=start, end_char=end, evidence_text=sentence)
            claims.append(
                Claim(
                    research_run_id=research_run_id,
                    claim_type=ClaimType.QUALITATIVE,
                    entity=entity,
                    metric="risk_factor",
                    value=sentence.strip(),
                    unit=None,
                    period=plan.period,
                    basis=Basis.UNKNOWN,
                    source_id=source.source_id,
                    evidence_span=evidence,
                    statement=sentence.strip(),
                )
            )

        return claims


def _build_claim(research_run_id: str, source: Source, draft: _ExtractedClaimDraft, evidence: Evidence) -> Claim:
    return Claim(
        research_run_id=research_run_id,
        claim_type=draft.claim_type,
        entity=draft.entity,
        metric=_slugify_metric(draft.metric),
        value=draft.value,
        unit=draft.unit,
        period=draft.period,
        basis=draft.basis,
        source_id=source.source_id,
        evidence_span=evidence,
        statement=draft.statement,
    )


def _slugify_metric(metric: str) -> str:
    return re.sub(r"\s+", "_", metric.strip().lower())


def _resolve_entity_for_source(source: Source, plan: ResearchPlan) -> str:
    """Determines which company a source is about, for the mock extractor.
    Prefers the explicit company_name tag SourceRetriever stamps onto every
    source's metadata; falls back to the single company in a single-company
    plan, then to a substring match against the source title/text, and only
    then to the first company as a last resort."""
    tagged = source.metadata.get("company_name")
    if tagged:
        return tagged
    if len(plan.companies) == 1:
        return plan.companies[0].name
    for company in plan.companies:
        if company.name.lower() in source.title.lower() or company.name.lower() in source.document_text.lower():
            return company.name
    return plan.companies[0].name if plan.companies else "Unknown Entity"


# ---- Mock-mode deterministic extraction helpers ----------------------------

METRIC_ALIASES = {
    "revenue": "revenue", "revenue_ttm": "revenue", "revenues": "revenue", "total revenue": "revenue",
    "net income": "net_income", "net_income_ttm": "net_income",
    "operating margin": "operating_margin", "operating_margin_ttm": "operating_margin",
    "operating income": "operating_income", "operating_income": "operating_income",
    "ebitda": "ebitda", "adjusted ebitda": "ebitda",
    "cash and cash equivalents": "cash_and_equivalents", "cash_and_equivalents": "cash_and_equivalents",
    "total debt": "total_debt", "total_debt": "total_debt",
    "diluted earnings per share": "eps_diluted", "earnings per share": "eps_diluted",
    "eps_diluted": "eps_diluted", "eps_trailing": "eps_diluted",
    "profit margin": "profit_margin", "profit_margin_ttm": "profit_margin",
}

_PATTERN_KV = re.compile(r"(?P<label>[a-z_]+)\s*=\s*(?P<num>[\d,]+(?:\.\d+)?)\s*(?P<unit>USD|%)?")
_PATTERN_DOLLAR = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z &]{2,45}?)\s+(?:was|is|totaled|totalled)\s+(?:approximately\s+)?"
    r"\$\s?(?P<num>[\d,]+(?:\.\d+)?)\s*(?P<scale>billion|million|thousand)?",
    re.IGNORECASE,
)
_PATTERN_PERCENT = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z &]{2,45}?)\s+(?:was|is)\s+(?:approximately\s+)?(?P<num>[\d]+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_PATTERN_EPS = re.compile(r"(?:diluted\s+)?earnings per share(?:\s+of)?\s+\$?(?P<num>[\d.]+)", re.IGNORECASE)

RISK_KEYWORDS = ("risk", "faces", "warns", "challenge", "competition", "adversely affected", "headwind")


def _infer_basis(text: str, start: int) -> Basis:
    window = text[max(0, start - 60):start].lower()
    if "non-gaap" in window:
        return Basis.NON_GAAP
    if "adjusted" in window:
        return Basis.ADJUSTED
    if "gaap" in window:
        return Basis.GAAP
    return Basis.UNKNOWN


def _extract_numeric_matches(text: str):
    """Yields (metric, matched_text, num, unit, start, end, basis) tuples
    with offsets guaranteed correct (computed directly from regex match
    spans against the real document_text, never LLM-provided)."""
    for m in _PATTERN_KV.finditer(text):
        metric = METRIC_ALIASES.get(m.group("label").lower())
        if not metric:
            continue
        yield metric, m.group(0), m.group("num"), m.group("unit") or "", m.start(), m.end(), _infer_basis(text, m.start())

    for m in _PATTERN_DOLLAR.finditer(text):
        metric = METRIC_ALIASES.get(m.group("label").strip().lower())
        if not metric:
            continue
        yield metric, m.group(0), m.group("num"), m.group("scale") or "", m.start(), m.end(), _infer_basis(text, m.start())

    for m in _PATTERN_PERCENT.finditer(text):
        metric = METRIC_ALIASES.get(m.group("label").strip().lower())
        if not metric:
            continue
        yield metric, m.group(0), m.group("num"), "%", m.start(), m.end(), _infer_basis(text, m.start())

    for m in _PATTERN_EPS.finditer(text):
        yield "eps_diluted", m.group(0), m.group("num"), "USD", m.start(), m.end(), _infer_basis(text, m.start())


_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]")


def _extract_risk_sentences(text: str):
    for m in _SENTENCE_RE.finditer(text):
        raw = m.group(0)
        # Trim leading/trailing whitespace while keeping start/end tightly
        # aligned to the trimmed text, so evidence_text always exactly
        # equals source.document_text[start:end].
        lstrip_len = len(raw) - len(raw.lstrip())
        rstrip_len = len(raw) - len(raw.rstrip())
        start, end = m.start() + lstrip_len, m.end() - rstrip_len
        sentence = text[start:end]
        if len(sentence) < 15:
            continue
        if any(k in sentence.lower() for k in RISK_KEYWORDS):
            yield sentence, start, end
