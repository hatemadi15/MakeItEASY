from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .. import compat_requests as requests
from ..models import GoogleSearchResult

logger = logging.getLogger(__name__)


@dataclass
class GoogleSearchClient:
    api_key: Optional[str]
    search_engine_id: Optional[str]
    timeout: int = 15

    ENDPOINT = "https://www.googleapis.com/customsearch/v1"

    def search(
        self,
        query: str,
        *,
        country: Optional[str] = None,
        limit: int = 5,
    ) -> List[GoogleSearchResult]:
        if not self.api_key or not self.search_engine_id:
            logger.debug("Google search client missing configuration; returning no results")
            return []
        params = {
            "key": self.api_key,
            "cx": self.search_engine_id,
            "q": query,
            "num": max(1, min(limit, 10)),
        }
        if country:
            params["gl"] = country.lower()
        try:
            response = requests.get(self.ENDPOINT, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Google search request failed: %s", exc)
            return []
        try:
            payload = response.json()
        except ValueError:
            logger.warning("Google search returned non-JSON payload")
            return []
        items: Iterable[dict] = payload.get("items", []) or []
        results: List[GoogleSearchResult] = []
        for item in items:
            link = item.get("link")
            title = item.get("title") or query
            snippet = item.get("snippet") or ""
            display_link = item.get("displayLink")
            if not link:
                continue
            results.append(
                GoogleSearchResult(
                    title=title,
                    link=link,
                    snippet=snippet,
                    display_link=display_link,
                )
            )
        return results[:limit]
