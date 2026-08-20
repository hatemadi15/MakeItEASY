from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from . import service
from .rate_limiter import RateLimitExceeded


@dataclass
class SearchResponse:
    query: str
    currency: str
    generated_at: str
    offers: list[dict]
    cached: bool


def create_app() -> FastAPI:
    app = FastAPI(title="Cheapest Makeup Finder", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/search", response_model=SearchResponse)
    def search(
        q: str = Query(..., min_length=1, max_length=200, description="Free text makeup query"),
        country: Optional[str] = Query(None, min_length=2, max_length=2, description="ISO2 country code"),
        limit: int = Query(20, ge=1, le=50),
        fresh: bool = Query(False, description="Placeholder flag for forcing recrawl"),
        condition: str = Query("new", min_length=3, max_length=10, description="Condition filter (new|any)"),
        currency: Optional[str] = Query(None, min_length=3, max_length=3, description="ISO3 currency code"),
        request: Request | None = None,
    ) -> SearchResponse:
        if not q.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")

        normalized_condition = (condition or "").lower().strip()
        if normalized_condition not in {"new", "any"}:
            raise HTTPException(status_code=400, detail="Unsupported condition filter")
        effective_condition = None if normalized_condition == "any" else normalized_condition

        client_host = "unknown"
        if request is not None and getattr(request, "client", None) is not None:
            client_host = getattr(request.client, "host", None) or "unknown"

        try:
            service.enforce_rate_limit(client_host)
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail={"error": "rate_limited", "retry_after": exc.retry_after},
            ) from exc

        payload = service.perform_search(
            query=q,
            country=country,
            condition=effective_condition,
            limit=limit,
        )

        return SearchResponse(
            query=q,
            currency=payload.currency_label,
            generated_at=payload.generated_at.isoformat() + "Z",
            offers=payload.offers,
            cached=payload.cached,
        )

    @app.post("/crawl/test", status_code=202)
    def crawl_test(url: str = Query(..., min_length=5, description="URL to crawl")) -> dict[str, str]:
        if not url.strip():
            raise HTTPException(status_code=400, detail="URL cannot be empty")
        return {"status": "queued", "url": url}

    return app


app = create_app()
