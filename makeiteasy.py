"""Utility helpers for querying publicly available makeup data sources.

This module wraps the free Makeup API along with Google's Custom Search API so
that callers can quickly discover cosmetic products and relevant shopping links
without scraping social media platforms.
"""
from __future__ import annotations

import json
import os
import sys
import textwrap
import re
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Sequence, Tuple
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

try:
    import requests  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    requests = None  # type: ignore

MAKEUP_API_URL = "http://makeup-api.herokuapp.com/api/v1/products.json"
DEFAULT_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "AIzaSyAF9e9otuHHWCpv7MYacwle_qLZT17-08I")
DEFAULT_GOOGLE_CX = os.getenv("GOOGLE_CSE_ID", "151662c5c18ba4c4c")
DEFAULT_GOOGLE_DATE_RESTRICT = os.getenv("GOOGLE_DATE_RESTRICT", "m1")


def _clean_tags(tags: Optional[Iterable[str]]) -> Optional[str]:
    if not tags:
        return None
    if isinstance(tags, str):
        return tags
    return ",".join(tag.strip() for tag in tags if tag)


class HTTPRequestError(RuntimeError):
    """Raised when an HTTP call fails regardless of the backend used."""


def _proxy_hint() -> Optional[str]:
    proxy = os.getenv("http_proxy") or os.getenv("https_proxy")
    if not proxy:
        return None
    return proxy


def _friendly_http_error(exc: Exception, *, url: str) -> str:
    if isinstance(exc, urlerror.HTTPError) and exc.code == 403:
        proxy = _proxy_hint()
        if proxy:
            return (
                "HTTP 403 Forbidden — the network proxy "
                f"{proxy} blocked outbound access to {url}."
            )
        return f"HTTP 403 Forbidden while calling {url}"

    if requests is not None:
        from requests import HTTPError as RequestsHTTPError  # type: ignore

        if isinstance(exc, RequestsHTTPError) and exc.response is not None:
            if exc.response.status_code == 403:
                proxy = _proxy_hint()
                if proxy:
                    return (
                        "HTTP 403 Forbidden — the network proxy "
                        f"{proxy} blocked outbound access to {url}."
                    )
                return f"HTTP 403 Forbidden while calling {url}"

    return str(exc)


def _request_json(url: str, params: MutableMapping[str, Any]) -> Any:
    params = {key: value for key, value in params.items() if value is not None}

    if requests is not None:
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:  # type: ignore[attr-defined]
            raise HTTPRequestError(_friendly_http_error(exc, url=url)) from exc

    query_string = urlparse.urlencode(params)
    full_url = f"{url}?{query_string}" if query_string else url
    try:
        with urlrequest.urlopen(full_url, timeout=15) as resp:
            payload = resp.read().decode("utf-8")
    except urlerror.HTTPError as exc:  # pragma: no cover - exercised via network
        raise HTTPRequestError(_friendly_http_error(exc, url=url)) from exc
    except urlerror.URLError as exc:  # pragma: no cover - exercised via network
        raise HTTPRequestError(str(exc)) from exc

    return json.loads(payload)


def _coerce_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def search_makeup_products(
    query: Optional[str] = None,
    *,
    brand: Optional[str] = None,
    product_type: Optional[str] = None,
    product_category: Optional[str] = None,
    product_tags: Optional[Iterable[str]] = None,
    price_greater_than: Optional[float] = None,
    price_less_than: Optional[float] = None,
    rating_greater_than: Optional[float] = None,
    rating_less_than: Optional[float] = None,
    max_results: int = 10,
) -> List[Dict[str, Any]]:
    """Search products from the Makeup API and filter by the query string."""

    params: Dict[str, Any] = {}
    if brand:
        params["brand"] = brand
    if product_type:
        params["product_type"] = product_type
    if product_category:
        params["product_category"] = product_category
    if price_greater_than is not None:
        params["price_greater_than"] = price_greater_than
    if price_less_than is not None:
        params["price_less_than"] = price_less_than
    if rating_greater_than is not None:
        params["rating_greater_than"] = rating_greater_than
    if rating_less_than is not None:
        params["rating_less_than"] = rating_less_than

    tags = _clean_tags(product_tags)
    if tags:
        params["product_tags"] = tags

    products: List[Dict[str, Any]] = _request_json(MAKEUP_API_URL, params)

    if query:
        needle = query.lower()
        products = [
            product
            for product in products
            if needle in " ".join(
                filter(
                    None,
                    [
                        str(product.get("brand", "")),
                        str(product.get("name", "")),
                        str(product.get("description", "")),
                    ],
                )
            ).lower()
        ]

    if max_results > 0:
        products = products[:max_results]

    return products


def google_custom_search(
    query: str,
    *,
    api_key: Optional[str] = None,
    search_engine_id: Optional[str] = None,
    num: int = 5,
    date_restrict: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a Google Custom Search query for additional product information."""

    api_key = api_key or DEFAULT_GOOGLE_API_KEY
    search_engine_id = search_engine_id or DEFAULT_GOOGLE_CX

    params = {
        "key": api_key,
        "cx": search_engine_id,
        "q": query,
        "num": max(1, min(num, 10)),
    }
    if date_restrict:
        params["dateRestrict"] = date_restrict
    return _request_json("https://www.googleapis.com/customsearch/v1", params)


_PRICE_RE = re.compile(r"([0-9]+(?:[.,][0-9]+)?)")


def _parse_price(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    match = _PRICE_RE.search(text.replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_price_from_google_item(item: Dict[str, Any]) -> Tuple[Optional[float], Optional[str]]:
    pagemap = item.get("pagemap") or {}
    currency: Optional[str] = None

    def from_offers(candidates: Any) -> Optional[float]:
        nonlocal currency
        if not candidates:
            return None
        if isinstance(candidates, dict):
            candidates = [candidates]
        for offer in candidates:
            if not isinstance(offer, dict):
                continue
            currency = offer.get("pricecurrency") or offer.get("priceCurrency") or currency
            for key in ("price", "priceamount", "priceAmount"):
                price = _parse_price(offer.get(key))
                if price is not None:
                    return price
        return None

    price = from_offers(pagemap.get("offer"))
    if price is None:
        price = from_offers(pagemap.get("offers"))

    if price is None and pagemap.get("product"):
        products = pagemap.get("product")
        if isinstance(products, dict):
            products = [products]
        if isinstance(products, list):
            for product in products:
                if not isinstance(product, dict):
                    continue
                price = from_offers(product.get("offers")) or _parse_price(product.get("price"))
                currency = product.get("pricecurrency") or product.get("priceCurrency") or currency
                if price is not None:
                    break

    if price is None and pagemap.get("metatags"):
        metatags = pagemap["metatags"]
        if isinstance(metatags, list):
            for tag in metatags:
                if not isinstance(tag, dict):
                    continue
                currency = tag.get("product:price:currency") or currency
                for key in ("product:price:amount", "og:price:amount"):
                    price = _parse_price(tag.get(key))
                    if price is not None:
                        return price, currency

    return price, currency


def _extract_summary(item: Dict[str, Any]) -> str:
    """Return the most descriptive snippet for the Google result."""

    pagemap = item.get("pagemap") or {}
    snippet = (item.get("snippet") or "").strip()

    meta_sources = [
        "og:description",
        "twitter:description",
        "og:title",
        "description",
    ]
    metatags = pagemap.get("metatags") or []
    if isinstance(metatags, dict):
        metatags = [metatags]

    for tag in metatags:
        if not isinstance(tag, dict):
            continue
        for key in meta_sources:
            candidate = (tag.get(key) or "").strip()
            if candidate:
                return candidate

    return snippet


def google_price_rank(
    query: str,
    *,
    num: int = 10,
    date_restrict: Optional[str] = None,
    search_response: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return Google Custom Search results sorted by the cheapest parsed price."""

    if search_response is None:
        search_response = google_custom_search(query, num=num, date_restrict=date_restrict)

    ranked: List[Dict[str, Any]] = []
    unpriced: List[Dict[str, Any]] = []
    for item in search_response.get("items", []) or []:
        price, currency = _extract_price_from_google_item(item)
        summary = _extract_summary(item)
        link = item.get("link")
        is_instagram = isinstance(link, str) and "instagram.com" in link.lower()
        payload = {
            "title": item.get("title") or "Untitled result",
            "link": link,
            "displayLink": item.get("displayLink"),
            "snippet": summary,
            "price": price,
            "currency": currency,
            "is_instagram": is_instagram,
        }
        if price is not None:
            ranked.append(payload)
        else:
            unpriced.append(payload)

    ranked.sort(key=lambda item: item["price"] or float("inf"))
    unpriced.sort(key=lambda item: (not item.get("is_instagram", False), item.get("title", "")))

    return {
        "ranked": ranked,
        "unpriced": unpriced,
        "info": search_response.get("searchInformation", {}),
        "raw": search_response,
    }


def format_product(product: Dict[str, Any]) -> str:
    """Pretty print a product dictionary for terminal output."""

    colors = ", ".join(color["colour_name"] for color in product.get("product_colors", []) if color.get("colour_name"))
    description = product.get("description") or "No description provided."
    description = textwrap.shorten(description.replace("\n", " "), width=140, placeholder="…")

    return textwrap.dedent(
        f"""
        {product.get('brand', 'Unknown Brand')} — {product.get('name', 'Unnamed Product')}
          Type: {product.get('product_type', 'n/a')}  |  Price: {product.get('price', 'n/a')} {product.get('currency', '')}
          Rating: {product.get('rating', 'n/a')}  |  Tags: {', '.join(product.get('tag_list', [])) or 'None'}
          Colors: {colors or 'n/a'}
          Link: {product.get('product_link') or product.get('website_link') or 'n/a'}
          Description: {description}
        """
    ).strip()


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def summarize_products(products: Sequence[Dict[str, Any]]) -> str:
    prices = [_coerce_float(product.get("price")) for product in products]
    prices = [price for price in prices if price is not None]
    ratings = [_coerce_float(product.get("rating")) for product in products]
    ratings = [rating for rating in ratings if rating is not None]

    summary_bits = [f"{len(products)} product(s) matched"]
    if prices:
        summary_bits.append(f"price range ${min(prices):.2f}-${max(prices):.2f} (median ${_median(prices):.2f})")
    if ratings:
        avg_rating = sum(ratings) / len(ratings)
        summary_bits.append(f"avg rating {avg_rating:.1f}/5")

    return ", ".join(summary_bits)


def build_table(products: Sequence[Dict[str, Any]]) -> str:
    """Render a simple ASCII table summarizing key product attributes."""

    if not products:
        return ""

    headers = ["#", "Brand", "Name", "Type", "Price", "Rating"]
    rows: List[List[str]] = []
    for idx, product in enumerate(products, 1):
        price = product.get("price")
        currency = product.get("currency")
        currency_suffix = f" {currency}" if currency else ""
        price_display = f"${price}{currency_suffix}" if price else "n/a"
        rating_display = product.get("rating") or "n/a"
        rows.append(
            [
                str(idx),
                str(product.get("brand", "Unknown")),
                str(product.get("name", "Unnamed")),
                str(product.get("product_type", "n/a")),
                price_display,
                str(rating_display),
            ]
        )

    col_widths = [
        max(len(row[col_idx]) for row in ([headers] + rows))
        for col_idx in range(len(headers))
    ]

    def format_row(row: Sequence[str]) -> str:
        return " | ".join(cell.ljust(col_widths[idx]) for idx, cell in enumerate(row))

    divider = "-+-".join("-" * width for width in col_widths)
    table_lines = [format_row(headers), divider]
    table_lines.extend(format_row(row) for row in rows)
    return "\n".join(table_lines)


def run_interactive_prompt(args: Any) -> Any:
    """Guide the user through common filters via stdin prompts."""

    print("Interactive search mode — press Enter to skip any step.")

    def prompt(text: str, default: Optional[str] = None) -> Optional[str]:
        suffix = f" [{default}]" if default else ""
        value = input(f"{text}{suffix}: ").strip()
        return value or default

    args.query = args.query or prompt("Product search phrase")
    if not args.query:
        print("A search phrase is required. Exiting.")
        sys.exit(1)

    args.brand = args.brand or prompt("Brand (optional)")
    args.product_type = args.product_type or prompt("Product type (lipstick, foundation, etc.)")
    args.product_category = args.product_category or prompt("Product category (liquid, pencil, powder, …)")

    if not args.product_tags:
        tags_answer = prompt("Product tags (comma separated: vegan, cruelty free, etc.)")
        if tags_answer:
            args.product_tags = [tag.strip() for tag in tags_answer.split(",") if tag.strip()]

    if args.price_min is None:
        price_min = prompt("Minimum price")
        args.price_min = _coerce_float(price_min)

    if args.price_max is None:
        price_max = prompt("Maximum price")
        args.price_max = _coerce_float(price_max)

    if args.rating_min is None:
        rating_min = prompt("Minimum rating (0-5)")
        args.rating_min = _coerce_float(rating_min)

    if args.rating_max is None:
        rating_max = prompt("Maximum rating (0-5)")
        args.rating_max = _coerce_float(rating_max)

    return args


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Search for makeup products and related shopping links.")
    parser.add_argument("query", nargs="?", help="Search phrase to look for in product names and descriptions.")
    parser.add_argument("--brand")
    parser.add_argument("--product-type")
    parser.add_argument("--product-category")
    parser.add_argument("--product-tags", nargs="*", help="One or more product tags such as vegan, cruelty free, etc.")
    parser.add_argument("--price-max", type=float, help="Upper price limit in the API request.")
    parser.add_argument("--price-min", type=float, help="Lower price limit in the API request.")
    parser.add_argument("--rating-min", type=float)
    parser.add_argument("--rating-max", type=float)
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--sort-by", choices=["price", "rating", "name"], help="Sort the Makeup API results by a field.")
    parser.add_argument("--descending", action="store_true", help="Reverse the sort order.")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for missing information instead of failing when the query is omitted.",
    )
    parser.add_argument("--include-google", action="store_true", help="Also perform a Google Custom Search for the query.")
    parser.add_argument("--google-results", type=int, default=5, help="How many Google results to show when --include-google is enabled.")
    parser.add_argument(
        "--google-cheapest",
        action="store_true",
        help="Rank Google Custom Search matches by extracted price information.",
    )
    parser.add_argument(
        "--google-date-restrict",
        default=DEFAULT_GOOGLE_DATE_RESTRICT,
        help=(
            "Limit Google results to a recent window, e.g. d7 (past 7 days), m1 (past month). "
            "Set to 'none' to disable."
        ),
    )

    args = parser.parse_args()

    if not args.query and not args.interactive:
        parser.error("Please supply a query or run with --interactive to be guided through the prompts.")

    if args.interactive:
        args = run_interactive_prompt(args)
    elif not args.query:
        # parser.error above prevents reaching this condition unless interactive is True.
        return

    date_restrict_arg = (args.google_date_restrict or "").strip()
    if date_restrict_arg.lower() in {"", "none", "off"}:
        google_date_restrict: Optional[str] = None
    else:
        google_date_restrict = date_restrict_arg

    try:
        products = search_makeup_products(
            args.query,
            brand=args.brand,
            product_type=args.product_type,
            product_category=args.product_category,
            product_tags=args.product_tags,
            price_less_than=args.price_max,
            price_greater_than=args.price_min,
            rating_greater_than=args.rating_min,
            rating_less_than=args.rating_max,
            max_results=args.max_results,
        )
    except HTTPRequestError as exc:
        print(f"Failed to query the Makeup API: {exc}")
        sys.exit(1)

    if args.sort_by:
        key_func = {
            "price": lambda product: _coerce_float(product.get("price")) or float("inf"),
            "rating": lambda product: _coerce_float(product.get("rating")) or -float("inf"),
            "name": lambda product: str(product.get("name", "")),
        }[args.sort_by]
        products.sort(key=key_func, reverse=args.descending)

    if not products:
        print("No products found for that query.")
    else:
        print(summarize_products(products))
        print("\n" + build_table(products))
        print("\nDetailed view:")
        for index, product in enumerate(products, 1):
            print(f"\n[{index}] {format_product(product)}")

    google_data: Optional[Dict[str, Any]] = None
    google_error: Optional[str] = None
    if args.include_google or args.google_cheapest:
        try:
            google_data = google_custom_search(
                args.query,
                num=args.google_results,
                date_restrict=google_date_restrict,
            )
        except HTTPRequestError as exc:
            google_error = str(exc)

    if args.include_google:
        print("\nGoogle Custom Search results:")
        if not google_data:
            print(f"  Google search failed: {google_error or 'Unknown error'}")
        else:
            items = google_data.get("items", [])
            if not items:
                print("  No results returned.")
            else:
                for idx, item in enumerate(items, 1):
                    snippet = textwrap.shorten(item.get("snippet", ""), width=120, placeholder="…")
                    print(
                        f"  {idx}. {item.get('title', 'Untitled')}\n     {item.get('link')}\n     {snippet}\n"
                    )

    if args.google_cheapest:
        print("\nCheapest Google offers:")
        if not google_data:
            print(f"  Unable to score Google results: {google_error or 'Unknown error'}")
            return

        ranking = google_price_rank(
            args.query,
            num=args.google_results,
            search_response=google_data,
            date_restrict=google_date_restrict,
        )
        priced = ranking["ranked"]
        if not priced:
            print("  None of the returned results included structured price information.")
        else:
            for idx, item in enumerate(priced, 1):
                price_text = f"${item['price']:.2f}" if item.get("price") is not None else ""
                if price_text and item.get("currency"):
                    price_text += f" {item['currency']}"
                snippet = textwrap.shorten(item.get("snippet", ""), width=100, placeholder="…")
                merchant = item.get("displayLink") or ""
                link = item.get("link") or ""
                if not price_text:
                    price_text = f"Contact merchant → {link}"
                print(
                    f"  {idx}. {price_text} — {item.get('title', 'Untitled')} ({merchant})\n"
                    f"     {link}\n"
                    f"     {snippet}\n"
                )

        if ranking["unpriced"]:
            print("  Additional results without price data:")
            for item in ranking["unpriced"][:3]:
                snippet = textwrap.shorten(item.get("snippet", ""), width=90, placeholder="…")
                marker = " (Instagram)" if item.get("is_instagram") else ""
                link = item.get("link") or ""
                print(f"    - Contact merchant → {link} | {item.get('title', 'Untitled')}{marker}\n"
                      f"      {snippet}")


if __name__ == "__main__":
    main()
