from __future__ import annotations

from enum import StrEnum


class SourceType(StrEnum):
    SEC_FILING = "sec_filing"
    FINANCIAL_API = "financial_api"
    WEB_ARTICLE = "web_article"
    PRESS_RELEASE = "press_release"
    MOCK = "mock"


class SourceTier(StrEnum):
    """Ordering matters: lower value = higher trust.

    PRD 3.2.4: primary filings > licensed/structured financial APIs >
    press / reputable publications > aggregators.
    """

    PRIMARY_FILING = "primary_filing"
    FINANCIAL_API = "financial_api"
    PRESS = "press"
    AGGREGATOR = "aggregator"
    MOCK = "mock"

    @property
    def rank(self) -> int:
        # Lower = more trustworthy. Used by confidence scorer & conflict resolution.
        order = {
            SourceTier.PRIMARY_FILING: 0,
            SourceTier.FINANCIAL_API: 1,
            SourceTier.PRESS: 2,
            SourceTier.AGGREGATOR: 3,
            SourceTier.MOCK: 4,
        }
        return order[self]


class ClaimType(StrEnum):
    NUMERIC = "numeric"
    QUALITATIVE = "qualitative"


class PeriodType(StrEnum):
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    TTM = "ttm"
    UNKNOWN = "unknown"


class Basis(StrEnum):
    GAAP = "gaap"
    NON_GAAP = "non_gaap"
    ADJUSTED = "adjusted"
    UNKNOWN = "unknown"


class VerificationVerdict(StrEnum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT = "insufficient"


class ResearchStatus(StrEnum):
    PENDING = "pending"
    PLANNING = "planning"
    RETRIEVING = "retrieving"
    EXTRACTING = "extracting"
    VERIFYING = "verifying"
    FOLLOWUP = "followup"
    COMPLETE = "complete"
    FAILED = "failed"


class ConflictReasonType(StrEnum):
    GENUINE_DISAGREEMENT = "genuine_disagreement"
    BASIS_MISMATCH = "basis_mismatch"
    PERIOD_MISMATCH = "period_mismatch"
    UNIT_CURRENCY_MISMATCH = "unit_currency_mismatch"
