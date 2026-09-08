"""Central application configuration.

All external credentials and tunables are read from environment variables
(see .env.example). Nothing is hardcoded. Providers check `settings.demo_mode`
(or the absence of their own API key) to decide whether to fall back to a
mock implementation - see app/retrieval/base.py and app/llm/base.py.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Mode
    demo_mode: bool = True

    # LLM
    llm_provider: Literal["claude", "openai"] = "claude"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # Search
    search_provider: Literal["tavily", "serpapi"] = "tavily"
    tavily_api_key: str | None = None
    serpapi_api_key: str | None = None

    # Financial data
    sec_edgar_user_agent: str = "Financial Research Agent OJT Project contact@example.com"
    alphavantage_api_key: str | None = None

    # Storage
    database_url: str = "sqlite:///./data/financial_research_agent.db"

    # Agent loop limits (see PRD 5.1: unbounded iterations is a named risk)
    max_followup_iterations: int = 2
    max_research_queries: int = 12
    max_subqueries_per_plan: int = 6

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    @property
    def llm_available(self) -> bool:
        if self.llm_provider == "claude":
            return bool(self.anthropic_api_key)
        return bool(self.openai_api_key)

    @property
    def search_available(self) -> bool:
        if self.search_provider == "tavily":
            return bool(self.tavily_api_key)
        return bool(self.serpapi_api_key)

    @property
    def alphavantage_available(self) -> bool:
        return bool(self.alphavantage_api_key)

    @property
    def effective_demo_mode(self) -> bool:
        """DEMO_MODE=true forces mocks. Otherwise, missing keys force mocks
        per-provider (handled in each provider's `is_available`), but if the
        LLM itself has no key we cannot run the real pipeline at all."""
        return self.demo_mode or not self.llm_available


@lru_cache
def get_settings() -> Settings:
    return Settings()
