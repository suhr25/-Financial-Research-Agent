"""SEC EDGAR adapter - primary filing source (SourceTier.PRIMARY_FILING).

Real implementation pulls company facts (XBRL) from SEC EDGAR's public
`companyfacts` API - no key required, only a descriptive User-Agent. Only
works for companies with a resolved CIK (i.e. SEC registrants).

Mock implementation is used in DEMO_MODE or when a company has no CIK
(e.g. a non-US company like Reliance Industries) or the live call fails.
Mock sources are always source_tier=MOCK, never PRIMARY_FILING, so they can
never be mistaken for a real SEC filing downstream.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.retrieval.base import FinancialDataProvider
from app.schemas import CompanyEntity, Source, SourceTier, SourceType

logger = logging.getLogger("financial_research_agent.retrieval.sec_edgar")

COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# XBRL us-gaap concept tags we pull, mapped to a human metric name.
METRIC_TAGS = {
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "NetIncomeLoss": "net_income",
    "OperatingIncomeLoss": "operating_income",
    "EarningsPerShareDiluted": "eps_diluted",
    "CashAndCashEquivalentsAtCarryingValue": "cash_and_equivalents",
    "LongTermDebtNoncurrent": "long_term_debt",
}


class SECEdgarProvider(FinancialDataProvider):
    name = "sec_edgar"

    def __init__(self):
        self.settings = get_settings()

    def is_available(self) -> bool:
        return not self.settings.effective_demo_mode

    def fetch(self, company: CompanyEntity, period: str | None) -> list[Source]:
        if not self.is_available() or not company.cik:
            return self._mock_fetch(company, period)
        try:
            return self._live_fetch(company, period)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SEC EDGAR live fetch failed for %s (%s); falling back to mock", company.name, exc)
            return self._mock_fetch(company, period)

    def _live_fetch(self, company: CompanyEntity, period: str | None) -> list[Source]:
        resp = httpx.get(
            COMPANY_FACTS_URL.format(cik=company.cik),
            headers={"User-Agent": self.settings.sec_edgar_user_agent},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        facts = data.get("facts", {}).get("us-gaap", {})

        lines: list[str] = [f"SEC EDGAR XBRL company facts for {company.name} (CIK {company.cik})."]
        for tag, metric_name in METRIC_TAGS.items():
            tag_data = facts.get(tag)
            if not tag_data:
                continue
            units = tag_data.get("units", {})
            for unit_name, entries in units.items():
                # Most recent few filed values for this concept.
                recent = sorted(entries, key=lambda e: e.get("end", ""), reverse=True)[:4]
                for entry in recent:
                    fp = entry.get("fp", "")
                    fy = entry.get("fy", "")
                    form = entry.get("form", "")
                    end = entry.get("end", "")
                    val = entry.get("val")
                    period_label = f"{fp}{fy}" if fp and fy else end
                    lines.append(
                        f"{metric_name} ({tag}) = {val} {unit_name} for period ending {end} "
                        f"(fiscal period {period_label}, form {form})."
                    )

        document_text = "\n".join(lines)
        source = Source(
            title=f"SEC EDGAR XBRL Company Facts - {company.name}",
            url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={company.cik}",
            source_type=SourceType.SEC_FILING,
            source_tier=SourceTier.PRIMARY_FILING,
            publisher="U.S. Securities and Exchange Commission (EDGAR)",
            document_text=document_text,
            metadata={"cik": company.cik, "ticker": company.ticker, "requested_period": period},
        )
        return [source]

    def _mock_fetch(self, company: CompanyEntity, period: str | None) -> list[Source]:
        period_label = period or "the most recent reported quarter"
        document_text = (
            f"[MOCK SEC FILING DATA - DEMO MODE, NOT A REAL SEC FILING]\n\n"
            f"{company.name} periodic filing excerpt for {period_label}.\n\n"
            f"Revenue was $85.8 billion for {period_label}, compared to $81.8 billion in the prior-year period, "
            f"an increase of approximately 5%.\n"
            f"Net income was $21.4 billion for {period_label}, representing a diluted earnings per share of $1.40.\n"
            f"Operating margin was approximately 29.6% on a GAAP basis for {period_label}.\n"
            f"Cash and cash equivalents totaled $28.4 billion as of the end of {period_label}.\n\n"
            f"Risk Factors: The Company's business, reputation, and results of operations could be materially "
            f"adversely affected by global and regional economic conditions, including inflation, changes in "
            f"interest rates, and currency fluctuations. The Company also faces substantial competition in all "
            f"of the markets in which it operates, and this competition could result in reduced margins and "
            f"loss of market share.\n"
        )
        source = Source(
            title=f"[MOCK] {company.name} Periodic Filing Excerpt - {period_label}",
            url=None,
            source_type=SourceType.MOCK,
            source_tier=SourceTier.MOCK,
            publisher="Demo Mode - Mock SEC Data",
            document_text=document_text,
            metadata={"mock": True, "requested_period": period},
        )
        return [source]
