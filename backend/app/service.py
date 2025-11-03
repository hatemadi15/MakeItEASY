from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Iterable, List, Optional

from .clients.gemini import GeminiMerchantClient
from .clients.google_search import GoogleSearchClient
from .config import load_config
from .extraction import PageFetcher, PriceExtractor
from .models import ExtractedOffer, MerchantSuggestion, SearchPayload
from .rate_limiter import RateLimiter

RATE_LIMITER = RateLimiter(limit=30, window_seconds=60, burst=60)


@dataclass
class OfferSearchService:
    google_client: GoogleSearchClient
    merchant_client: GeminiMerchantClient
    fetcher: PageFetcher
    extractor: PriceExtractor
    max_results: int = 10

    def search(
        self,
        *,
        query: str,
        country: Optional[str],
        condition: Optional[str],
        limit: int,
    ) -> SearchPayload:
        suggestions = self._suggest_merchants(query=query, country=country)
        search_terms = self._build_search_terms(query=query, suggestions=suggestions)
        offers = self._collect_offers(
            search_terms=search_terms,
            country=country,
            condition=condition,
            limit=limit,
            base_query=query,
        )
        serialized = self._serialize_offers(offers)
        return SearchPayload(
            generated_at=datetime.utcnow(),
            offers=serialized,
            cached=False,
            currency_label="NATIVE",
        )

    def _suggest_merchants(
        self,
        *,
        query: str,
        country: Optional[str],
    ) -> List[MerchantSuggestion]:
        try:
            return self.merchant_client.suggest_merchants(query=query, country=country)
        except Exception:
            return []

    def _build_search_terms(
        self,
        *,
        query: str,
        suggestions: Iterable[MerchantSuggestion],
    ) -> List[str]:
        terms = [query]
        for suggestion in suggestions:
            suffix = suggestion.name
            if suffix:
                terms.append(f"{query} {suffix}")
        return terms

    def _collect_offers(
        self,
        *,
        search_terms: Iterable[str],
        country: Optional[str],
        condition: Optional[str],
        limit: int,
        base_query: str,
    ) -> List[ExtractedOffer]:
        collected: List[ExtractedOffer] = []
        seen_urls: set[str] = set()
        for term in search_terms:
            results = self.google_client.search(term, country=country, limit=self.max_results)
            for result in results:
                if result.link in seen_urls:
                    continue
                seen_urls.add(result.link)
                html = self.fetcher.fetch(result.link)
                if not html:
                    continue
                offer = self.extractor.extract(
                    html=html,
                    url=result.link,
                    query=base_query,
                    result=result,
                    country=country,
                )
                if not offer:
                    continue
                if condition and offer.condition.lower() != condition.lower():
                    continue
                if country and offer.merchant_country:
                    if offer.merchant_country.upper() != country.upper():
                        continue
                collected.append(offer)
                if len(collected) >= limit:
                    return self._rank_offers(collected)[:limit]
        return self._rank_offers(collected)[:limit]

    def _rank_offers(self, offers: Iterable[ExtractedOffer]) -> List[ExtractedOffer]:
        return sorted(
            offers,
            key=lambda offer: (offer.total_price(), offer.seen_at, offer.merchant_name),
        )

    def _serialize_offers(self, offers: List[ExtractedOffer]) -> List[dict]:
        if not offers:
            return []
        serialized = []
        cheapest_offer = offers[0]
        next_offer = offers[1] if len(offers) > 1 else None
        for index, offer in enumerate(offers):
            shipping_value = offer.shipping_value or Decimal("0")
            shipping_currency = offer.shipping_currency or offer.price_currency
            total_value = offer.price_value + shipping_value
            base_component = {
                "label": "Base price",
                "value": float(offer.price_value),
                "currency": offer.price_currency,
                "converted_value": float(offer.price_value),
                "converted_currency": offer.price_currency,
            }
            shipping_component = {
                "label": "Shipping",
                "value": float(shipping_value),
                "currency": shipping_currency,
                "converted_value": float(shipping_value),
                "converted_currency": shipping_currency,
                "source": "unknown" if offer.shipping_value is None else "vendor",
                "is_estimated": offer.shipping_value is None,
            }
            merchant_country = offer.merchant_country or "Unknown"
            payload = {
                "product": {
                    "brand": offer.brand or "",
                    "name": offer.product_name,
                    "variant": offer.variant,
                },
                "merchant": {
                    "name": offer.merchant_name,
                    "country": merchant_country,
                },
                "price": {
                    "value": float(offer.price_value),
                    "currency": offer.price_currency,
                    "converted_value": float(offer.price_value),
                    "converted_currency": offer.price_currency,
                },
                "shipping": {
                    "value": float(shipping_value),
                    "currency": shipping_currency,
                    "converted_value": float(shipping_value),
                    "converted_currency": shipping_currency,
                    "source": "unknown" if offer.shipping_value is None else "vendor",
                    "is_estimated": offer.shipping_value is None,
                },
                "confidence": offer.confidence,
                "confidence_details": offer.confidence_details,
                "availability": offer.availability,
                "condition": offer.condition,
                "total": {
                    "converted_value": float(total_value),
                    "currency": offer.price_currency,
                },
                "seen_at": offer.seen_at.isoformat() + "Z",
                "url": offer.url,
                "assumptions": list(offer.assumptions),
                "price_components": [base_component, shipping_component],
                "analysis": self._build_analysis(
                    index=index,
                    offer=offer,
                    cheapest_offer=cheapest_offer,
                    next_offer=next_offer,
                ),
                "evidence": {
                    "snippet": offer.evidence_snippet,
                    "screenshot": None,
                    "captured_at": offer.seen_at.isoformat() + "Z",
                },
            }
            serialized.append(payload)
        return serialized

    def _build_analysis(
        self,
        *,
        index: int,
        offer: ExtractedOffer,
        cheapest_offer: ExtractedOffer,
        next_offer: Optional[ExtractedOffer],
    ) -> dict:
        total_value = offer.total_price()
        currency = offer.price_currency
        analysis = {
            "cheapest": index == 0,
            "summary": "",
            "comparison": None,
        }
        if index == 0:
            analysis["summary"] = (
                f"Lowest observed total price {currency} {total_value:.2f} at {offer.merchant_name}."
            )
            if next_offer and next_offer.price_currency == currency:
                diff = next_offer.total_price() - total_value
                analysis["comparison"] = {
                    "type": "vs_next",
                    "difference": float(diff),
                    "currency": currency,
                    "next_merchant": next_offer.merchant_name,
                }
        else:
            if currency == cheapest_offer.price_currency:
                diff = total_value - cheapest_offer.total_price()
                analysis["comparison"] = {
                    "type": "vs_cheapest",
                    "difference": float(diff),
                    "currency": currency,
                    "cheapest_merchant": cheapest_offer.merchant_name,
                }
                analysis["summary"] = (
                    f"Total is {currency} {diff:.2f} higher than the cheapest option."
                )
            else:
                analysis["summary"] = (
                    "Total price reported in a different currency; manual comparison recommended."
                )
        return analysis


_SERVICE: OfferSearchService | None = None
_OVERRIDE: OfferSearchService | None = None


def get_service() -> OfferSearchService:
    global _SERVICE
    if _OVERRIDE is not None:
        return _OVERRIDE
    if _SERVICE is None:
        config = load_config()
        google_client = GoogleSearchClient(
            api_key=config.google.api_key,
            search_engine_id=config.google.search_engine_id,
            timeout=config.http_timeout,
        )
        merchant_client = GeminiMerchantClient(
            api_key=config.gemini.api_key,
            model=config.gemini.model,
            timeout=config.http_timeout,
        )
        fetcher = PageFetcher(timeout=config.http_timeout)
        extractor = PriceExtractor()
        _SERVICE = OfferSearchService(
            google_client=google_client,
            merchant_client=merchant_client,
            fetcher=fetcher,
            extractor=extractor,
            max_results=config.max_search_results,
        )
    return _SERVICE


def override_service(service: OfferSearchService | None) -> None:
    global _OVERRIDE
    _OVERRIDE = service


def reset_service() -> None:
    global _SERVICE
    _SERVICE = None


def perform_search(
    *,
    query: str,
    country: Optional[str],
    condition: Optional[str],
    limit: int,
) -> SearchPayload:
    service = get_service()
    return service.search(
        query=query,
        country=country,
        condition=condition,
        limit=limit,
    )


def enforce_rate_limit(client_key: str) -> None:
    outcome = RATE_LIMITER.consume(client_key)
    if not outcome.allowed:
        from .rate_limiter import RateLimitExceeded

        raise RateLimitExceeded(outcome.retry_after)
