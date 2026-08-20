import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.app import service
from backend.app.main import create_app
from backend.app.models import ExtractedOffer, GoogleSearchResult, MerchantSuggestion


class StubGoogleClient:
    def __init__(self, results_map):
        self.results_map = results_map

    def search(self, query, country=None, limit=5):
        return self.results_map.get(query, [])


class StubGeminiClient:
    def __init__(self, suggestions):
        self.suggestions = suggestions

    def suggest_merchants(self, *, query, country):
        return self.suggestions


class StubPageFetcher:
    def __init__(self, pages):
        self.pages = pages

    def fetch(self, url):
        return self.pages.get(url, "")


class StubExtractor:
    def __init__(self, offers):
        self.offers = offers

    def extract(self, *, html, url, query, result, country):
        return self.offers.get(url)


def make_offer(*, merchant, country, price, shipping=Decimal("0"), condition="new", snippet=None):
    now = datetime.utcnow()
    return ExtractedOffer(
        product_name="Radiant Creamy Concealer",
        brand="NARS",
        variant="Vanilla",
        merchant_name=merchant,
        merchant_country=country,
        price_value=Decimal(price),
        price_currency="USD",
        shipping_value=Decimal(shipping) if shipping is not None else None,
        shipping_currency="USD" if shipping not in (None, Decimal("0")) else None,
        availability="in_stock",
        condition=condition,
        confidence="high",
        confidence_details="Structured price detected.",
        assumptions=["Price extracted from fixture."],
        evidence_snippet=snippet,
        url=f"https://{merchant.lower().replace(' ', '')}.example.com/product",
        seen_at=now - timedelta(minutes=5),
    )


def build_stub_service():
    base_query = "nars radiant creamy concealer"
    offers = {
        "https://beautyhublb.example.com/product": make_offer(
            merchant="BeautyHub LB",
            country="LB",
            price=Decimal("21.40"),
            shipping=Decimal("2.00"),
            snippet="BeautyHub price $21.40",
        ),
        "https://glowupae.example.com/product": make_offer(
            merchant="GlowUp AE",
            country="AE",
            price=Decimal("23.00"),
            shipping=Decimal("4.00"),
            snippet="GlowUp price $23",
        ),
        "https://prelovedlb.example.com/product": make_offer(
            merchant="PreLoved LB",
            country="LB",
            price=Decimal("12.00"),
            shipping=Decimal("3.00"),
            condition="used",
            snippet="Tester listing",
        ),
    }
    results = {
        base_query: [
            GoogleSearchResult(
                title="NARS Concealer - BeautyHub",
                link="https://beautyhublb.example.com/product",
                snippet="BeautyHub price $21.40",
                display_link="beautyhublb.example.com",
            ),
            GoogleSearchResult(
                title="NARS Concealer - GlowUp",
                link="https://glowupae.example.com/product",
                snippet="GlowUp price $23",
                display_link="glowupae.example.com",
            ),
            GoogleSearchResult(
                title="NARS Concealer Tester",
                link="https://prelovedlb.example.com/product",
                snippet="Tester $12",
                display_link="prelovedlb.example.com",
            ),
        ],
    }
    pages = {url: "<html></html>" for url in offers}
    google_client = StubGoogleClient(results)
    gemini_client = StubGeminiClient([MerchantSuggestion(name="BeautyHub", country="LB")])
    fetcher = StubPageFetcher(pages)
    extractor = StubExtractor(offers)
    return service.OfferSearchService(
        google_client=google_client,
        merchant_client=gemini_client,
        fetcher=fetcher,
        extractor=extractor,
        max_results=5,
    )


client = TestClient(create_app(), client_host="203.0.113.10")


@pytest.fixture(autouse=True)
def configure_service():
    stub = build_stub_service()
    service.override_service(stub)
    service.RATE_LIMITER.reset()
    service.RATE_LIMITER.configure(limit=30, burst=60, window_seconds=60)
    yield
    service.override_service(None)
    service.reset_service()
    service.RATE_LIMITER.reset()
    service.RATE_LIMITER.configure(limit=30, burst=60, window_seconds=60)


def test_search_requires_query():
    response = client.get("/search")
    assert response.status_code == 422


def test_search_returns_sorted_offers():
    response = client.get("/search", params={"q": "nars radiant creamy concealer"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["currency"] == "NATIVE"
    offers = payload["offers"]
    assert len(offers) == 2
    totals = [offer["total"]["converted_value"] for offer in offers]
    assert totals == sorted(totals)
    assert payload["cached"] is False


def test_country_filter():
    response = client.get(
        "/search",
        params={"q": "nars radiant creamy concealer", "country": "LB"},
    )
    assert response.status_code == 200
    offers = response.json()["offers"]
    assert all(offer["merchant"]["country"] == "LB" for offer in offers)


def test_condition_filter_default_new_only():
    response = client.get("/search", params={"q": "nars radiant creamy concealer"})
    offers = response.json()["offers"]
    assert all(offer["condition"] == "new" for offer in offers)


def test_condition_filter_any_includes_used():
    response = client.get(
        "/search",
        params={"q": "nars radiant creamy concealer", "condition": "any"},
    )
    offers = response.json()["offers"]
    assert any(offer["condition"] != "new" for offer in offers)


def test_offer_analysis_includes_reasoning():
    response = client.get("/search", params={"q": "nars radiant creamy concealer"})
    offers = response.json()["offers"]
    assert offers[0]["analysis"]["cheapest"] is True
    assert offers[0]["analysis"]["comparison"]["type"] == "vs_next"
    assert offers[1]["analysis"]["comparison"]["type"] == "vs_cheapest"


def test_rate_limiting_returns_429():
    service.RATE_LIMITER.configure(limit=2, burst=2, window_seconds=60)
    service.RATE_LIMITER.reset()
    for _ in range(2):
        ok_response = client.get("/search", params={"q": "nars radiant creamy concealer"})
        assert ok_response.status_code == 200
    limited = client.get("/search", params={"q": "nars radiant creamy concealer"})
    assert limited.status_code == 429
    detail = limited.json()["detail"]
    assert detail["error"] == "rate_limited"
    assert detail["retry_after"] >= 1


def test_crawl_test_endpoint_acknowledges_url():
    response = client.post("/crawl/test", json={"url": "https://example.com/product"})
    assert response.status_code == 202
    payload = response.json()
    assert payload == {"status": "queued", "url": "https://example.com/product"}
