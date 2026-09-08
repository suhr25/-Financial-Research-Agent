from __future__ import annotations

from app.config import Settings
from app.llm.base import LLMProvider


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, settings: Settings):
        import anthropic

        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def _raw_complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
