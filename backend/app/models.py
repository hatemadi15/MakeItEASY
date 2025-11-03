from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Sequence


@dataclass
class GoogleSearchResult:
    title: str
    link: str
    snippet: str
    display_link: str | None = None


@dataclass
class ExtractedOffer:
    product_name: str
    brand: Optional[str]
    variant: Optional[str]
    merchant_name: str
    merchant_country: Optional[str]
    price_value: Decimal
    price_currency: str
    shipping_value: Optional[Decimal]
    shipping_currency: Optional[str]
    availability: str
    condition: str
    confidence: str
    confidence_details: Optional[str]
    assumptions: Sequence[str]
    evidence_snippet: Optional[str]
    url: str
    seen_at: datetime

    def total_price(self) -> Decimal:
        shipping = self.shipping_value or Decimal("0")
        return self.price_value + shipping


@dataclass
class MerchantSuggestion:
    name: str
    country: Optional[str]


@dataclass
class SearchPayload:
    generated_at: datetime
    offers: list[dict]
    cached: bool
    currency_label: str
