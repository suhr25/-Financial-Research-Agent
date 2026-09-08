"""Retrieval abstractions.

SearchProvider and FinancialDataProvider are the two adapter families the
PRD's architecture diagram shows feeding the Multi-Source Retriever. Every
concrete adapter (real or mock) returns fully-formed Source objects with
document_text preserved verbatim - no adapter is allowed to hand back a
summary in place of the source text.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import CompanyEntity, Evidence, Source


class SearchProvider(ABC):
    name: str = "base_search"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[Source]: ...


class FinancialDataProvider(ABC):
    name: str = "base_financial_data"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def fetch(self, company: CompanyEntity, period: str | None) -> list[Source]: ...


def make_evidence(source: Source, snippet: str, occurrence: int = 0) -> Evidence | None:
    """Locate `snippet` verbatim inside source.document_text and return an
    Evidence span for it. Returns None if the snippet cannot be found -
    callers must treat that as "no evidence", never fabricate a span.
    """
    text = source.document_text
    start = -1
    idx = -1
    for i in range(occurrence + 1):
        idx = text.find(snippet, idx + 1)
        if idx == -1:
            return None
        start = idx
    end = start + len(snippet)
    return Evidence(source_id=source.source_id, start_char=start, end_char=end, evidence_text=snippet)


def full_document_evidence(source: Source) -> Evidence:
    return Evidence(
        source_id=source.source_id,
        start_char=0,
        end_char=len(source.document_text),
        evidence_text=source.document_text,
    )
