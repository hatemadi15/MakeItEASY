from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class GoogleSearchConfig:
    api_key: str | None
    search_engine_id: str | None


@dataclass
class GeminiConfig:
    api_key: str | None
    model: str


@dataclass
class ServiceConfig:
    google: GoogleSearchConfig
    gemini: GeminiConfig
    http_timeout: int = 15
    max_search_results: int = 10


DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


def load_config() -> ServiceConfig:
    google_key = os.getenv("GOOGLE_SEARCH_API_KEY")
    google_cse = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    gemini_key = os.getenv("GEMINI_API_KEY")
    gemini_model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    return ServiceConfig(
        google=GoogleSearchConfig(api_key=google_key, search_engine_id=google_cse),
        gemini=GeminiConfig(api_key=gemini_key, model=gemini_model),
    )
