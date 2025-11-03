from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Optional

from . import compat_requests as requests
from .models import ExtractedOffer, GoogleSearchResult

logger = logging.getLogger(__name__)


@dataclass
class PageFetcher:
    timeout: int = 15

    def fetch(self, url: str) -> Optional[str]:
        try:
            response = requests.get(url, timeout=self.timeout)
            response.raise_for_status()
            response.encoding = response.encoding or "utf-8"
            return response.text
        except requests.RequestException as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return None


class PriceExtractor:
    PRICE_PATTERN = re.compile(
        r"(?P<currency>\$|€|£|AED|د\.إ|SAR|ر\.س|KWD|د\.ك|BHD|د\.ب|QAR|ر\.ق|OMR|ر\.ع|LBP|ل\.ل)\s*"
        r"(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)",
        re.IGNORECASE,
    )
    SHIPPING_PATTERN = re.compile(
        r"shipping\s*(?:cost|fee|from)?\s*(?P<currency>\$|€|£|AED|د\.إ|SAR|ر\.س|LBP|ل\.ل)?\s*(?P<amount>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?)",
        re.IGNORECASE,
    )

    CURRENCY_ALIASES = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "AED": "AED",
        "د.إ": "AED",
        "SAR": "SAR",
        "ر.س": "SAR",
        "KWD": "KWD",
        "د.ك": "KWD",
        "BHD": "BHD",
        "د.ب": "BHD",
        "QAR": "QAR",
        "ر.ق": "QAR",
        "OMR": "OMR",
        "ر.ع": "OMR",
        "LBP": "LBP",
        "ل.ل": "LBP",
    }

    def extract(
        self,
        *,
        html: str,
        url: str,
        query: str,
        result: GoogleSearchResult,
        country: Optional[str],
    ) -> Optional[ExtractedOffer]:
        text = self._normalise_text(html)
        price_match = self.PRICE_PATTERN.search(text)
        if not price_match:
            logger.debug("No price match found for %s", url)
            return None
        price_currency = self._normalize_currency(price_match.group("currency"))
        price_value = self._parse_amount(price_match.group("amount"))
        if price_value is None:
            return None

        shipping_value: Optional[Decimal] = None
        shipping_currency: Optional[str] = None
        shipping_match = self.SHIPPING_PATTERN.search(text)
        if shipping_match:
            shipping_currency = self._normalize_currency(shipping_match.group("currency") or price_match.group("currency"))
            shipping_value = self._parse_amount(shipping_match.group("amount"))

        brand, name, variant = self._derive_product_metadata(query)
        merchant_name = self._derive_merchant_name(result)
        merchant_country = country or self._infer_country_from_display_link(result.display_link)
        seen_at = datetime.utcnow()
        assumptions = [
            "Price extracted from live webpage copy.",
        ]
        if shipping_value is None:
            assumptions.append("Shipping not detected; treated as zero for ranking.")
        snippet = result.snippet or None
        confidence = "high" if price_currency in {"USD", "EUR", "GBP", "AED", "SAR", "LBP"} else "medium"
        confidence_details = (
            f"Price detected via heuristic pattern in page content ({price_currency})."
        )
        return ExtractedOffer(
            product_name=name or query,
            brand=brand,
            variant=variant,
            merchant_name=merchant_name,
            merchant_country=merchant_country,
            price_value=price_value,
            price_currency=price_currency,
            shipping_value=shipping_value,
            shipping_currency=shipping_currency,
            availability="unknown",
            condition="new",
            confidence=confidence,
            confidence_details=confidence_details,
            assumptions=assumptions,
            evidence_snippet=snippet,
            url=result.link,
            seen_at=seen_at,
        )

    def _normalise_text(self, html: str) -> str:
        text = unescape(html)
        text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        return " ".join(text.split())

    def _normalize_currency(self, raw: Optional[str]) -> str:
        if not raw:
            return "UNKNOWN"
        raw = raw.strip().upper()
        return self.CURRENCY_ALIASES.get(raw, raw)

    def _parse_amount(self, raw: str) -> Optional[Decimal]:
        cleaned = raw.strip()
        if cleaned.count(",") > 0 and cleaned.count(".") > 0:
            if cleaned.find(",") > cleaned.find("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            logger.debug("Could not parse amount %s", raw)
            return None

    def _derive_product_metadata(self, query: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        tokens = [token.strip() for token in query.split() if token.strip()]
        if not tokens:
            return None, query, None
        brand = tokens[0].title()
        name = " ".join(tokens[1:]).title() if len(tokens) > 1 else tokens[0].title()
        variant = None
        if tokens and tokens[-1].isnumeric():
            variant = tokens[-1]
        return brand, name, variant

    def _derive_merchant_name(self, result: GoogleSearchResult) -> str:
        if result.display_link:
            return result.display_link
        title = result.title or ""
        if "-" in title:
            return title.split("-")[-1].strip()
        return title[:60] or "Unknown Merchant"

    def _infer_country_from_display_link(self, display_link: Optional[str]) -> Optional[str]:
        if not display_link:
            return None
        lower = display_link.lower()
        if lower.endswith(".lb"):
            return "LB"
        if lower.endswith(".ae"):
            return "AE"
        if lower.endswith(".sa") or lower.endswith(".com.sa"):
            return "SA"
        if lower.endswith(".kw"):
            return "KW"
        if lower.endswith(".qa"):
            return "QA"
        if lower.endswith(".bh"):
            return "BH"
        if lower.endswith(".om"):
            return "OM"
        return None
