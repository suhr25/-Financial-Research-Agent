from __future__ import annotations

import logging

from app.config import get_settings
from app.llm.base import LLMProvider

logger = logging.getLogger("financial_research_agent.llm")

_cached_provider: LLMProvider | None = None
_cache_key: tuple | None = None


def get_llm_provider() -> LLMProvider | None:
    """Returns a real LLMProvider, or None if the app is in demo mode / no
    API key is configured for the selected provider. Callers MUST handle the
    None case with their own deterministic mock heuristic - see each
    agent/extraction/verification module's `_mock_*` methods."""
    global _cached_provider, _cache_key
    settings = get_settings()
    if settings.effective_demo_mode:
        return None

    key = (settings.llm_provider, settings.anthropic_api_key, settings.openai_api_key)
    if _cached_provider is not None and _cache_key == key:
        return _cached_provider

    if settings.llm_provider == "claude" and settings.anthropic_api_key:
        from app.llm.claude_provider import ClaudeProvider

        _cached_provider = ClaudeProvider(settings)
    elif settings.llm_provider == "openai" and settings.openai_api_key:
        from app.llm.openai_provider import OpenAIProvider

        _cached_provider = OpenAIProvider(settings)
    else:
        logger.warning("LLM provider %s selected but no API key configured; falling back to mock heuristics")
        return None

    _cache_key = key
    return _cached_provider
