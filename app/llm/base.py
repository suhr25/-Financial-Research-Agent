"""LLM provider abstraction.

This is the ONLY place agent modules should talk to an LLM API. It is
intentionally a "real LLM" abstraction only - Claude and OpenAI - with no
mock branch inside it. Mock/DEMO_MODE behaviour lives at the call-site
(QueryPlanner, ClaimExtractor, EntailmentChecker, ReportGenerator etc. each
implement their own deterministic heuristic fallback) so that "the LLM was
never actually called" is always an explicit, visible code path rather than
a fake LLM pretending to reason. See app/llm/factory.py.

complete_json() asks the model to emit JSON matching a Pydantic schema and
validates the result, retrying once with the validation error appended to
the prompt if parsing/validation fails.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger("financial_research_agent.llm")

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def _raw_complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str: ...

    def complete(self, system: str, user: str, max_tokens: int = 2048, temperature: float = 0.0) -> str:
        return self._raw_complete(system, user, max_tokens, temperature)

    def complete_json(
        self,
        system: str,
        user: str,
        schema_model: type[T],
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> T:
        schema_instructions = (
            f"\n\nRespond with ONLY a single valid JSON object matching this JSON schema "
            f"(no markdown fences, no commentary, no extra text before or after):\n"
            f"{json.dumps(schema_model.model_json_schema())}"
        )
        full_system = system + schema_instructions
        last_error: Exception | None = None
        user_msg = user
        for attempt in range(2):
            raw = self._raw_complete(full_system, user_msg, max_tokens, temperature)
            cleaned = _strip_code_fences(raw)
            try:
                data = json.loads(cleaned)
                return schema_model.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                logger.warning("complete_json parse failure (attempt %d): %s", attempt + 1, exc)
                user_msg = (
                    f"{user}\n\nYour previous response was invalid: {exc}\n"
                    f"Previous response was:\n{raw}\n"
                    f"Return ONLY corrected valid JSON matching the schema."
                )
        raise LLMError(f"LLM failed to produce valid JSON for schema {schema_model.__name__}: {last_error}")


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
