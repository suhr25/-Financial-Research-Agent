"""Multi-Source Retriever: fans a ResearchPlan's sub-queries and companies
out to the web search adapter and financial data adapters, deduplicates the
results, and persists every Source via the repository layer so provenance
(including full document_text) is never lost.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.retrieval.financial_data import get_financial_data_provider
from app.retrieval.sec_edgar import SECEdgarProvider
from app.retrieval.web_search import get_search_provider
from app.schemas import ResearchPlan, Source, SourceType
from app.storage import repositories as repo

logger = logging.getLogger("financial_research_agent.retrieval.source_retriever")


def _tag_company(sources: list[Source], company_name: str) -> list[Source]:
    """Stamps which company a retrieved source is about into its metadata,
    so the Claim Extractor can attribute claims to the right company in
    multi-company (comparison) research runs instead of guessing."""
    for source in sources:
        source.metadata["company_name"] = company_name
    return sources


class SourceRetriever:
    def __init__(self):
        self.search_provider = get_search_provider()
        self.financial_provider = get_financial_data_provider()
        self.sec_provider = SECEdgarProvider()

    def retrieve(self, db: Session, research_run_id: str, plan: ResearchPlan) -> list[Source]:
        collected: list[Source] = []
        seen_text_hashes: set[int] = set()

        for company in plan.companies:
            if SourceType.SEC_FILING in plan.required_source_types or not plan.required_source_types:
                collected.extend(_tag_company(self.sec_provider.fetch(company, plan.period), company.name))
            if SourceType.FINANCIAL_API in plan.required_source_types or not plan.required_source_types:
                collected.extend(_tag_company(self.financial_provider.fetch(company, plan.period), company.name))

        for sub_query in plan.sub_queries:
            if plan.required_source_types and SourceType.WEB_ARTICLE not in plan.required_source_types:
                continue
            if sub_query.target_source_types and SourceType.WEB_ARTICLE not in sub_query.target_source_types:
                continue
            web_sources = self.search_provider.search(sub_query.text, max_results=3)
            if sub_query.company:
                web_sources = _tag_company(web_sources, sub_query.company)
            collected.extend(web_sources)

        deduped: list[Source] = []
        for source in collected:
            h = hash(source.document_text)
            if h in seen_text_hashes:
                continue
            seen_text_hashes.add(h)
            deduped.append(source)

        for source in deduped:
            repo.save_source(db, research_run_id, source)

        logger.info(
            "Retrieved %d sources (%d after dedup) for research_run_id=%s",
            len(collected), len(deduped), research_run_id,
        )
        return deduped
