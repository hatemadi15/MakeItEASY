"""Minimal HTTP server that exposes a web UI for the Makeup API."""
from __future__ import annotations

import html
import io
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Iterable, List, Optional
from urllib import parse

from makeiteasy import (
    HTTPRequestError,
    google_custom_search,
    search_makeup_products,
)

HOST = "0.0.0.0"
PORT = 8000


def _first(query_params: Dict[str, List[str]], key: str) -> str:
    values = query_params.get(key, [""])
    return values[0]


def _parse_float(value: str, label: str, errors: List[str]) -> Optional[float]:
    value = value.strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        errors.append(f"{label} must be a number. You entered '{value}'.")
        return None


def _render_tags(tags: Iterable[str]) -> str:
    snippets = [f'<span class="tag">{html.escape(tag)}</span>' for tag in tags]
    return "".join(snippets)


def _render_products(products: List[Dict[str, Any]]) -> str:
    html_out = io.StringIO()
    for product in products:
        brand = html.escape(product.get("brand") or "Unknown brand")
        name = html.escape(product.get("name") or "Unnamed product")
        price = html.escape(str(product.get("price") or "n/a"))
        currency = html.escape(str(product.get("currency") or ""))
        rating = html.escape(str(product.get("rating") or "n/a"))
        description = html.escape(product.get("description") or "No description provided.")
        image = html.escape(
            product.get("image_link")
            or "https://via.placeholder.com/120x120?text=No+Image"
        )
        product_link = product.get("product_link") or product.get("website_link")
        link_html = ""
        if product_link:
            link_html = (
                f'<p><a href="{html.escape(product_link)}" target="_blank" '
                "rel=\"noopener noreferrer\">View product</a></p>"
            )
        tags_html = ""
        if product.get("tag_list"):
            tags_html = f'<div class="tags">{_render_tags(product["tag_list"])}</div>'

        html_out.write(
            f"<article class=\"product-card\">"
            f'<img src="{image}" alt="{name}" />'
            "<div>"
            f"<h3>{brand} — {name}</h3>"
            f"<p><strong>Price:</strong> {price} {currency} | "
            f"<strong>Rating:</strong> {rating}</p>"
            f"<p>{description}</p>"
            f"{tags_html}"
            f"{link_html}"
            "</div></article>"
        )
    return html_out.getvalue()


def _render_google_results(results: List[Dict[str, Any]], info: Dict[str, Any]) -> str:
    if not results:
        return ""
    out = io.StringIO()
    timing = info.get("searchTime")
    if timing:
        out.write(f"<p>Fetched in {html.escape(str(timing))} seconds.</p>")
    out.write("<ul>")
    for result in results:
        title = html.escape(result.get("title") or "Untitled result")
        snippet = html.escape(result.get("snippet") or "")
        link = html.escape(result.get("link") or "#")
        out.write(
            "<li>"
            f'<h4><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></h4>'
            f"<p>{snippet}</p>"
            "</li>"
        )
    out.write("</ul>")
    return out.getvalue()


def _render_page(context: Dict[str, Any]) -> str:
    form = context["form_state"]
    products_section = ""
    if context["submitted"] and context["products"]:
        products_html = _render_products(context["products"])
        products_section = f"<section class=\"results\"><h2>Products</h2>{products_html}</section>"
    elif context["submitted"] and not context["errors"]:
        products_section = "<p>No products matched your filters. Try a broader query.</p>"

    errors_section = ""
    if context["errors"]:
        items = "".join(f"<li>{html.escape(err)}</li>" for err in context["errors"])
        errors_section = f"<div class=\"errors\"><strong>We hit a snag:</strong><ul>{items}</ul></div>"

    google_section = ""
    if context["google_results"]:
        google_html = _render_google_results(context["google_results"], context["google_info"])
        google_section = f"<section class=\"google-results\"><h2>Google Shopping Links</h2>{google_html}</section>"

    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>MakeItEASY — Makeup Product Finder</title>
    <style>
      :root {{ font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif; color: #1f2933; background: #f4f6f8; }}
      body {{ margin: 0; padding: 0; background: #f4f6f8; }}
      header {{ background: linear-gradient(135deg, #f472b6, #f59e0b); color: #fff; padding: 2rem 1rem; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
      main {{ max-width: 960px; margin: -3rem auto 2rem auto; padding: 2rem; background: #fff; border-radius: 1rem; box-shadow: 0 20px 60px rgba(15,23,42,0.15); }}
      form {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin-bottom: 1.5rem; }}
      label {{ display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 0.25rem; text-transform: uppercase; letter-spacing: 0.04em; color: #64748b; }}
      input {{ width: 100%; padding: 0.65rem; border-radius: 0.5rem; border: 1px solid #d5d9e2; font-size: 1rem; box-sizing: border-box; }}
      input:focus {{ outline: 2px solid #f472b6; border-color: transparent; }}
      .actions {{ grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 1rem; }}
      button {{ background: #f472b6; color: #fff; border: none; border-radius: 999px; padding: 0.9rem 1.5rem; font-size: 1rem; font-weight: 600; cursor: pointer; }}
      .checkbox {{ display: flex; align-items: center; gap: 0.5rem; }}
      .results {{ margin-top: 2rem; }}
      .product-card {{ border: 1px solid #edf0f6; border-radius: 1rem; padding: 1.25rem; margin-bottom: 1rem; display: grid; grid-template-columns: 120px 1fr; gap: 1rem; align-items: center; box-shadow: 0 10px 25px rgba(15,23,42,0.05); }}
      .product-card img {{ width: 120px; height: 120px; object-fit: contain; background: #f8fafc; border-radius: 0.75rem; padding: 0.5rem; }}
      .tags {{ margin-top: 0.5rem; display: flex; flex-wrap: wrap; gap: 0.35rem; }}
      .tag {{ font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; padding: 0.25rem 0.55rem; background: #f1f5f9; border-radius: 999px; }}
      .errors {{ background: #fee2e2; border: 1px solid #fecaca; color: #991b1b; padding: 1rem; border-radius: 0.75rem; margin-bottom: 1.5rem; }}
      .google-results {{ margin-top: 2rem; }}
      @media (max-width: 640px) {{ main {{ margin: 0; border-radius: 0; }} .product-card {{ grid-template-columns: 1fr; text-align: center; }} .product-card img {{ margin: 0 auto; }} }}
    </style>
  </head>
  <body>
    <header>
      <h1>MakeItEASY</h1>
      <p>Search the free Makeup API and curated Google shopping links without any scraping.</p>
    </header>
    <main>
      <form method=\"get\">
        <input type=\"hidden\" name=\"submitted\" value=\"1\" />
        <div><label for=\"query\">Search phrase</label><input id=\"query\" name=\"query\" value=\"{html.escape(form['query'])}\" placeholder=\"lipstick\" /></div>
        <div><label for=\"brand\">Brand</label><input id=\"brand\" name=\"brand\" value=\"{html.escape(form['brand'])}\" placeholder=\"maybelline\" /></div>
        <div><label for=\"product_type\">Product type</label><input id=\"product_type\" name=\"product_type\" value=\"{html.escape(form['product_type'])}\" placeholder=\"lipstick\" /></div>
        <div><label for=\"product_category\">Category</label><input id=\"product_category\" name=\"product_category\" value=\"{html.escape(form['product_category'])}\" placeholder=\"liquid\" /></div>
        <div><label for=\"product_tags\">Tags</label><input id=\"product_tags\" name=\"product_tags\" value=\"{html.escape(form['product_tags'])}\" placeholder=\"vegan, cruelty free\" /></div>
        <div><label for=\"price_min\">Min price</label><input id=\"price_min\" name=\"price_min\" value=\"{html.escape(form['price_min'])}\" /></div>
        <div><label for=\"price_max\">Max price</label><input id=\"price_max\" name=\"price_max\" value=\"{html.escape(form['price_max'])}\" /></div>
        <div><label for=\"rating_min\">Min rating</label><input id=\"rating_min\" name=\"rating_min\" value=\"{html.escape(form['rating_min'])}\" /></div>
        <div><label for=\"rating_max\">Max rating</label><input id=\"rating_max\" name=\"rating_max\" value=\"{html.escape(form['rating_max'])}\" /></div>
        <div class=\"actions\">
          <label class=\"checkbox\"><input type=\"checkbox\" name=\"include_google\" {'checked' if form['include_google'] else ''} /> Include Google shopping links</label>
          <button type=\"submit\">Search products</button>
        </div>
      </form>
      {errors_section}
      {products_section}
      {google_section}
    </main>
  </body>
</html>
"""


class MakeupHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # pragma: no cover - exercised manually
        parsed = parse.urlparse(self.path)
        if parsed.path not in ("/", ""):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        params = parse.parse_qs(parsed.query)
        submitted = _first(params, "submitted") == "1"
        errors: List[str] = []

        query = _first(params, "query").strip()
        brand = _first(params, "brand").strip() or None
        product_type = _first(params, "product_type").strip() or None
        product_category = _first(params, "product_category").strip() or None
        tags_raw = _first(params, "product_tags").strip()
        tag_list = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]

        price_min = _parse_float(_first(params, "price_min"), "Min price", errors)
        price_max = _parse_float(_first(params, "price_max"), "Max price", errors)
        rating_min = _parse_float(_first(params, "rating_min"), "Min rating", errors)
        rating_max = _parse_float(_first(params, "rating_max"), "Max rating", errors)

        include_google = _first(params, "include_google") in {"on", "true", "1"}

        products: List[Dict[str, Any]] = []
        google_results: List[Dict[str, Any]] = []
        google_info: Dict[str, Any] = {}

        if submitted and not errors:
            try:
                products = search_makeup_products(
                    query or None,
                    brand=brand,
                    product_type=product_type,
                    product_category=product_category,
                    product_tags=tag_list,
                    price_greater_than=price_min,
                    price_less_than=price_max,
                    rating_greater_than=rating_min,
                    rating_less_than=rating_max,
                    max_results=12,
                )
            except HTTPRequestError as exc:
                errors.append(str(exc))

            if include_google and query and not errors:
                try:
                    google_data = google_custom_search(query, num=5)
                    google_results = google_data.get("items", []) or []
                    google_info = google_data.get("searchInformation", {})
                except HTTPRequestError as exc:
                    errors.append(f"Google Search failed: {exc}")

        form_state = {
            "query": query,
            "brand": brand or "",
            "product_type": product_type or "",
            "product_category": product_category or "",
            "product_tags": tags_raw,
            "price_min": _first(params, "price_min"),
            "price_max": _first(params, "price_max"),
            "rating_min": _first(params, "rating_min"),
            "rating_max": _first(params, "rating_max"),
            "include_google": include_google,
        }

        html_body = _render_page(
            {
                "submitted": submitted,
                "form_state": form_state,
                "products": products,
                "errors": errors,
                "google_results": google_results,
                "google_info": google_info,
            }
        )

        body_bytes = html_body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - reduce noise
        return


def main() -> None:
    server = HTTPServer((HOST, PORT), MakeupHandler)
    print(f"Serving MakeItEASY UI on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
