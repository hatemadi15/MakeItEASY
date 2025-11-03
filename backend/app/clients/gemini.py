from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from .. import compat_requests as requests
from ..models import MerchantSuggestion

logger = logging.getLogger(__name__)


@dataclass
class GeminiMerchantClient:
    api_key: Optional[str]
    model: str = "gemini-2.0-flash"
    timeout: int = 15

    ENDPOINT_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def suggest_merchants(self, *, query: str, country: Optional[str]) -> List[MerchantSuggestion]:
        if not self.api_key:
            return []
        prompt = self._build_prompt(query=query, country=country)
        endpoint = self.ENDPOINT_TEMPLATE.format(model=self.model)
        params = {"key": self.api_key}
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                    ],
                }
            ]
        }
        try:
            response = requests.post(endpoint, params=params, json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Gemini merchant suggestion failed: %s", exc)
            return []
        try:
            data = response.json()
        except ValueError:
            logger.warning("Gemini returned non-JSON payload")
            return []
        text = self._extract_text(data)
        return self._parse_merchants(text)

    def _build_prompt(self, *, query: str, country: Optional[str]) -> str:
        country_hint = f" in {country}" if country else ""
        return (
            "You are helping source merchants that sell makeup products. "
            "Given the query \"{query}\", list up to 5 merchant names".format(query=query)
            + country_hint
            + ". Respond with a JSON array of objects with fields name and country (ISO2 or null)."
        )

    @staticmethod
    def _extract_text(payload: dict) -> str:
        candidates = payload.get("candidates") or []
        for candidate in candidates:
            content = candidate.get("content") or {}
            parts = content.get("parts") or []
            for part in parts:
                text = part.get("text")
                if text:
                    return text
        return ""

    def _parse_merchants(self, text: str) -> List[MerchantSuggestion]:
        text = text.strip()
        if not text:
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Gemini returned non-JSON merchant suggestions: %s", text)
            return []
        suggestions: List[MerchantSuggestion] = []
        if isinstance(data, list):
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                country = entry.get("country")
                if not name:
                    continue
                suggestions.append(MerchantSuggestion(name=str(name), country=country))
        return suggestions
