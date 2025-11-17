"""Utility helpers for querying publicly available makeup data sources.

This module wraps the free Makeup API along with Google's Custom Search API so
that callers can quickly discover cosmetic products and relevant shopping links
without scraping social media platforms.
"""
from __future__ import annotations

import os
import textwrap
from typing import Any, Dict, Iterable, List, MutableMapping, Optional

import requests

MAKEUP_API_URL = "http://makeup-api.herokuapp.com/api/v1/products.json"
DEFAULT_GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "AIzaSyAF9e9otuHHWCpv7MYacwle_qLZT17-08I")
DEFAULT_GOOGLE_CX = os.getenv("GOOGLE_CSE_ID", "151662c5c18ba4c4c")


def _clean_tags(tags: Optional[Iterable[str]]) -> Optional[str]:
    if not tags:
        return None
    if isinstance(tags, str):
        return tags
    return ",".join(tag.strip() for tag in tags if tag)


def _request_json(url: str, params: MutableMapping[str, Any]) -> Any:
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()


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
    return _request_json("https://www.googleapis.com/customsearch/v1", params)


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


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Search for makeup products and related shopping links.")
    parser.add_argument("query", help="Search phrase to look for in product names and descriptions.")
    parser.add_argument("--brand")
    parser.add_argument("--product-type")
    parser.add_argument("--product-category")
    parser.add_argument("--product-tags", nargs="*", help="One or more product tags such as vegan, cruelty free, etc.")
    parser.add_argument("--price-max", type=float, help="Upper price limit in the API request.")
    parser.add_argument("--price-min", type=float, help="Lower price limit in the API request.")
    parser.add_argument("--rating-min", type=float)
    parser.add_argument("--rating-max", type=float)
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--include-google", action="store_true", help="Also perform a Google Custom Search for the query.")

    args = parser.parse_args()

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

    if not products:
        print("No products found for that query.")
    else:
        print(f"Top {len(products)} Makeup API result(s):")
        for index, product in enumerate(products, 1):
            print(f"\n[{index}] {format_product(product)}")

    if args.include_google:
        print("\nGoogle Custom Search results:")
        try:
            search_results = google_custom_search(args.query)
        except requests.HTTPError as exc:
            print(f"  Google search failed: {exc}")
            return

        items = search_results.get("items", [])
        if not items:
            print("  No results returned.")
            return

        for idx, item in enumerate(items, 1):
            snippet = textwrap.shorten(item.get("snippet", ""), width=120, placeholder="…")
            print(f"  {idx}. {item.get('title', 'Untitled')}\n     {item.get('link')}\n     {snippet}\n")


if __name__ == "__main__":
    main()
