from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator

from app.schemas.enums import SourceTier, SourceType


class Source(BaseModel):
    """A single retrieved document, with the full original text preserved.

    The PRD is explicit: "Do not merely store a generated summary as the
    evidence. The actual source text must remain available." `document_text`
    is therefore the raw, retrieved text - never an LLM summary - and all
    Evidence spans are character offsets into this exact string.
    """

    source_id: str = Field(default_factory=lambda: f"src_{uuid4().hex[:12]}")
    title: str
    url: str | None = None
    source_type: SourceType
    source_tier: SourceTier
    publisher: str
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    document_text: str
    metadata: dict = Field(default_factory=dict)

    def slice(self, start_char: int, end_char: int) -> str:
        return self.document_text[start_char:end_char]


class Evidence(BaseModel):
    """A pointer into a specific Source's document_text. `evidence_text` is
    stored redundantly (denormalized) for convenience/display, but it must
    always equal source.document_text[start_char:end_char] - validated by
    whoever constructs it (see app/retrieval/base.py helpers)."""

    source_id: str
    start_char: int
    end_char: int
    evidence_text: str

    @model_validator(mode="after")
    def _validate_span(self) -> "Evidence":
        if self.start_char < 0 or self.end_char < self.start_char:
            raise ValueError(f"Invalid span [{self.start_char}, {self.end_char}]")
        return self
