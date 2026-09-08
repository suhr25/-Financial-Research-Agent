"""Structured financial data adapter (SourceTier.FINANCIAL_API): Alpha
Vantage first (if a key is configured), falling back to yfinance (free,
no key required) or a mock when both are disabled/fail.
"""
from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.retrieval.base import FinancialDataProvider
from app.schemas import CompanyEntity, Source, SourceTier, SourceType

logger = logging.getLogger("financial_research_agent.retrieval.financial_data")


class AlphaVantageProvider(FinancialDataProvider):
    name = "alpha_vantage"

    def __init__(self):
        self.settings = get_settings()

    def is_available(self) -> bool:
        return not self.settings.effective_demo_mode and bool(self.settings.alphavantage_api_key)

    def fetch(self, company: CompanyEntity, period: str | None) -> list[Source]:
        if not self.is_available() or not company.ticker:
            return YFinanceProvider().fetch(company, period)
        try:
            resp = httpx.get(
                "https://www.alphavantage.co/query",
                params={
                    "function": "OVERVIEW",
                    "symbol": company.ticker,
                    "apikey": self.settings.alphavantage_api_key,
                },
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data or "Symbol" not in data:
                raise ValueError(f"No Alpha Vantage overview data for {company.ticker}")

            lines = [f"Alpha Vantage company overview for {company.name} ({company.ticker})."]
            fields = [
                ("MarketCapitalization", "market_cap"),
                ("EBITDA", "ebitda"),
                ("PERatio", "pe_ratio"),
                ("RevenueTTM", "revenue_ttm"),
                ("GrossProfitTTM", "gross_profit_ttm"),
                ("ProfitMargin", "profit_margin"),
                ("OperatingMarginTTM", "operating_margin_ttm"),
                ("ReturnOnEquityTTM", "return_on_equity_ttm"),
                ("QuarterlyRevenueGrowthYOY", "quarterly_revenue_growth_yoy"),
                ("QuarterlyEarningsGrowthYOY", "quarterly_earnings_growth_yoy"),
            ]
            for key, label in fields:
                if data.get(key) not in (None, "None", ""):
                    lines.append(f"{label} = {data[key]} (TTM basis unless noted).")

            source = Source(
                title=f"Alpha Vantage Company Overview - {company.name}",
                url=f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={company.ticker}",
                source_type=SourceType.FINANCIAL_API,
                source_tier=SourceTier.FINANCIAL_API,
                publisher="Alpha Vantage",
                document_text="\n".join(lines),
                metadata={"ticker": company.ticker, "requested_period": period},
            )
            return [source]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Alpha Vantage fetch failed for %s (%s); falling back to yfinance", company.name, exc)
            return YFinanceProvider().fetch(company, period)


class YFinanceProvider(FinancialDataProvider):
    """Free, no-API-key financial data via Yahoo Finance. Used as the
    default real financial_api source when Alpha Vantage is not configured."""

    name = "yfinance"

    def __init__(self):
        self.settings = get_settings()

    def is_available(self) -> bool:
        return not self.settings.effective_demo_mode

    def fetch(self, company: CompanyEntity, period: str | None) -> list[Source]:
        if not self.is_available() or not company.ticker:
            return MockFinancialDataProvider().fetch(company, period)
        try:
            import yfinance as yf

            ticker = yf.Ticker(company.ticker)
            info = ticker.info
            if not info or info.get("regularMarketPrice") is None and info.get("marketCap") is None:
                raise ValueError(f"No yfinance data for {company.ticker}")

            lines = [f"Yahoo Finance data for {company.name} ({company.ticker})."]
            field_map = [
                ("totalRevenue", "revenue_ttm"),
                ("netIncomeToCommon", "net_income_ttm"),
                ("operatingMargins", "operating_margin_ttm"),
                ("profitMargins", "profit_margin_ttm"),
                ("ebitda", "ebitda"),
                ("trailingEps", "eps_trailing"),
                ("totalCash", "cash_and_equivalents"),
                ("totalDebt", "total_debt"),
                ("marketCap", "market_cap"),
            ]
            for key, label in field_map:
                val = info.get(key)
                if val is not None:
                    lines.append(f"{label} = {val}.")

            source = Source(
                title=f"Yahoo Finance Data - {company.name}",
                url=f"https://finance.yahoo.com/quote/{company.ticker}",
                source_type=SourceType.FINANCIAL_API,
                source_tier=SourceTier.FINANCIAL_API,
                publisher="Yahoo Finance",
                document_text="\n".join(lines),
                metadata={"ticker": company.ticker, "requested_period": period},
            )
            return [source]
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance fetch failed for %s (%s); falling back to mock", company.name, exc)
            return MockFinancialDataProvider().fetch(company, period)


class MockFinancialDataProvider(FinancialDataProvider):
    name = "mock_financial_data"

    def is_available(self) -> bool:
        return True

    def fetch(self, company: CompanyEntity, period: str | None) -> list[Source]:
        period_label = period or "trailing twelve months"
        text = (
            f"[MOCK FINANCIAL API DATA - DEMO MODE, NOT A REAL FINANCIAL DATA PROVIDER]\n\n"
            f"Structured financial data snapshot for {company.name} ({company.ticker or 'N/A'}), {period_label}.\n\n"
            f"revenue_ttm = 85800000000 USD.\n"
            f"net_income_ttm = 21400000000 USD.\n"
            f"operating_margin_ttm = 0.296.\n"
            f"ebitda = 30100000000 USD (adjusted, non-GAAP basis).\n"
            f"eps_diluted = 1.40 USD.\n"
            f"cash_and_equivalents = 28400000000 USD.\n"
            f"total_debt = 95000000000 USD.\n"
        )
        source = Source(
            title=f"[MOCK] Financial Data Snapshot - {company.name}",
            url=None,
            source_type=SourceType.MOCK,
            source_tier=SourceTier.MOCK,
            publisher="Demo Mode - Mock Financial API",
            document_text=text,
            metadata={"mock": True, "requested_period": period},
        )
        return [source]


def get_financial_data_provider() -> FinancialDataProvider:
    settings = get_settings()
    if settings.effective_demo_mode:
        return MockFinancialDataProvider()
    if settings.alphavantage_available:
        return AlphaVantageProvider()
    return YFinanceProvider()
