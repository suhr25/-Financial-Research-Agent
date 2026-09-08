"""Web search adapters (Tavily / SerpAPI), plus a deterministic mock used in
DEMO_MODE or when no search API key is configured.

Source tiering for web results (PRD 3.2.4: press/reputable publications >
aggregators): a small reputable-domain allowlist promotes a result to
SourceTier.PRESS; everything else is SourceTier.AGGREGATOR since a generic
web search gives no other reliable signal of publisher reputation.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from app.config import get_settings
from app.retrieval.base import SearchProvider
from app.schemas import Source, SourceTier, SourceType

logger = logging.getLogger("financial_research_agent.retrieval.web_search")

REPUTABLE_PRESS_DOMAINS = {
    "reuters.com", "bloomberg.com", "wsj.com", "ft.com", "cnbc.com",
    "apnews.com", "barrons.com", "marketwatch.com", "forbes.com",
    "businesswire.com", "prnewswire.com", "investor.com",
}


def _tier_for_url(url: str | None) -> SourceTier:
    if not url:
        return SourceTier.AGGREGATOR
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return SourceTier.PRESS if any(host == d or host.endswith("." + d) for d in REPUTABLE_PRESS_DOMAINS) else SourceTier.AGGREGATOR


class TavilyProvider(SearchProvider):
    name = "tavily"

    def __init__(self):
        self.settings = get_settings()

    def is_available(self) -> bool:
        return not self.settings.effective_demo_mode and bool(self.settings.tavily_api_key)

    def search(self, query: str, max_results: int = 5) -> list[Source]:
        if not self.is_available():
            return MockSearchProvider().search(query, max_results)
        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.settings.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_raw_content": True,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            sources = []
            for r in data.get("results", []):
                text = r.get("raw_content") or r.get("content") or ""
                if not text:
                    continue
                url = r.get("url")
                sources.append(
                    Source(
                        title=r.get("title") or url or "Untitled web result",
                        url=url,
                        source_type=SourceType.WEB_ARTICLE,
                        source_tier=_tier_for_url(url),
                        publisher=urlparse(url).netloc if url else "unknown",
                        document_text=text,
                        metadata={"query": query, "tavily_score": r.get("score")},
                    )
                )
            return sources
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tavily search failed for %r (%s); falling back to mock", query, exc)
            return MockSearchProvider().search(query, max_results)


class SerpAPIProvider(SearchProvider):
    name = "serpapi"

    def __init__(self):
        self.settings = get_settings()

    def is_available(self) -> bool:
        return not self.settings.effective_demo_mode and bool(self.settings.serpapi_api_key)

    def search(self, query: str, max_results: int = 5) -> list[Source]:
        if not self.is_available():
            return MockSearchProvider().search(query, max_results)
        try:
            resp = httpx.get(
                "https://serpapi.com/search.json",
                params={"q": query, "api_key": self.settings.serpapi_api_key, "num": max_results},
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            sources = []
            for r in data.get("organic_results", [])[:max_results]:
                text = r.get("snippet") or ""
                if not text:
                    continue
                url = r.get("link")
                sources.append(
                    Source(
                        title=r.get("title") or url or "Untitled web result",
                        url=url,
                        source_type=SourceType.WEB_ARTICLE,
                        source_tier=_tier_for_url(url),
                        publisher=urlparse(url).netloc if url else "unknown",
                        document_text=text,
                        metadata={"query": query},
                    )
                )
            return sources
        except Exception as exc:  # noqa: BLE001
            logger.warning("SerpAPI search failed for %r (%s); falling back to mock", query, exc)
            return MockSearchProvider().search(query, max_results)


class MockSearchProvider(SearchProvider):
    """Deterministic, clearly-labelled synthetic web results used in DEMO_MODE."""

    name = "mock_web_search"

    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5) -> list[Source]:
        lowered = query.lower()
        # Note: the header deliberately avoids ending in "." right after the
        # query text - a query like "...major risks" would otherwise get
        # mis-split by the (intentionally simple) mock claim extractor's
        # sentence splitter into a bogus "risk" sentence.
        header = f"[MOCK WEB SEARCH RESULT - DEMO MODE, NOT A REAL WEB SEARCH]\n\nCoverage related to search: {query}\n\n"
        if any(k in lowered for k in ("risk", "headwind", "challenge")):
            body = (
                "The company's management flagged several risks in recent commentary: ongoing supply chain "
                "constraints, foreign currency headwinds affecting international revenue, and intensifying "
                "competition in its core product categories. Analysts also warned that regulatory scrutiny in "
                "several major markets could pressure future margins if new compliance costs are imposed.\n"
            )
        elif any(k in lowered for k in ("margin", "ebitda", "profit")):
            body = (
                "Analysts noted that adjusted EBITDA came in at approximately $30.1 billion, a non-GAAP figure "
                "that differs from the operating income the company reports under GAAP in its own filings. "
                "Operating margin was estimated at around 29% by most sell-side analysts covering the stock, "
                "broadly consistent with the prior-year period.\n"
            )
        elif any(k in lowered for k in ("net income", "earnings")):
            body = (
                "Wire coverage pegged net income at roughly $21.4 billion for the period, modestly ahead of "
                "consensus analyst estimates, driven by resilient demand and disciplined cost control.\n"
            )
        else:
            body = (
                "Analysts noted that revenue for the period came in at $85.8 billion, roughly in line with "
                "consensus estimates, reflecting steady demand across the company's major product and "
                "service categories.\n"
            )
        text = header + body
        return [
            Source(
                title=f"[MOCK] Web coverage: {query}",
                url=None,
                source_type=SourceType.MOCK,
                source_tier=SourceTier.MOCK,
                publisher="Demo Mode - Mock Web Search",
                document_text=text,
                metadata={"mock": True, "query": query},
            )
        ]


def get_search_provider() -> SearchProvider:
    settings = get_settings()
    if settings.effective_demo_mode:
        return MockSearchProvider()
    if settings.search_provider == "tavily" and settings.tavily_api_key:
        return TavilyProvider()
    if settings.search_provider == "serpapi" and settings.serpapi_api_key:
        return SerpAPIProvider()
    return MockSearchProvider()
