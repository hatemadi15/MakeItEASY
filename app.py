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
    DEFAULT_GOOGLE_DATE_RESTRICT,
    google_price_rank,
    search_makeup_products,
)

HOST = "0.0.0.0"
PORT = 8000

RECENCY_CHOICES = [
    ("d7", "Past 7 days"),
    ("m1", "Past month"),
    ("m3", "Past 3 months"),
    ("y1", "Past year"),
    ("none", "Any time"),
]


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


def _parse_int(
    value: str,
    label: str,
    errors: List[str],
    *,
    minimum: int,
    maximum: int,
    default: int,
) -> int:
    value = value.strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"{label} must be an integer. You entered '{value}'.")
        return default
    return max(minimum, min(parsed, maximum))


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


def _render_google_ranked(section: Dict[str, Any]) -> str:
    ranked = section.get("ranked", [])
    unpriced = section.get("unpriced", [])
    info = section.get("info", {})
    timing = info.get("searchTime")

    if not ranked and not unpriced:
        return ""

    out = io.StringIO()
    if timing:
        out.write(f"<p>Fetched in {html.escape(str(timing))} seconds.</p>")

    if ranked:
        out.write(
            "<div class=\"table\"><table><thead><tr><th>#</th><th>Merchant</th><th>Price</th><th>Summary</th></tr></thead><tbody>"
        )
        for idx, item in enumerate(ranked, 1):
            merchant = html.escape(item.get("displayLink") or "")
            title = html.escape(item.get("title") or "Untitled result")
            snippet = html.escape(item.get("snippet") or "")
            link = html.escape(item.get("link") or "#")
            price_value = item.get("price")
            currency = html.escape(item.get("currency") or "")
            price_html = "Unknown"
            if price_value is not None:
                price_html = f"${price_value:,.2f}"
                if currency:
                    price_html += f" {currency}"
            out.write(
                "<tr>"
                f"<td>{idx}</td>"
                f'<td><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a><br /><small>{merchant}</small></td>'
                f"<td>{price_html}</td>"
                f"<td>{snippet}</td>"
                "</tr>"
            )
        out.write("</tbody></table></div>")

    if unpriced:
        out.write("<details><summary>Show results without price data</summary><ul>")
        for item in unpriced:
            title = html.escape(item.get("title") or "Untitled result")
            link = html.escape(item.get("link") or "#")
            snippet = html.escape(item.get("snippet") or "")
            out.write(
                "<li>"
                f'<strong><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></strong> — {snippet}'
                "</li>"
            )
        out.write("</ul></details>")

    return out.getvalue()


def _render_page(context: Dict[str, Any]) -> str:
    makeup = context["makeup"]
    google = context["google"]

    makeup_results_section = ""
    if makeup["submitted"] and makeup["products"]:
        products_html = _render_products(makeup["products"])
        makeup_results_section = (
            f"<section class=\"results\"><h2>EasyDirectory results</h2>{products_html}</section>"
        )
    elif makeup["submitted"] and not makeup["errors"]:
        makeup_results_section = "<p>No products matched your filters. Try a broader query.</p>"

    makeup_errors = ""
    if makeup["errors"]:
        items = "".join(f"<li>{html.escape(err)}</li>" for err in makeup["errors"])
        makeup_errors = f"<div class=\"errors\"><strong>EasyDirectory issue:</strong><ul>{items}</ul></div>"

    google_errors = ""
    if google["errors"]:
        items = "".join(f"<li>{html.escape(err)}</li>" for err in google["errors"])
        google_errors = f"<div class=\"errors\"><strong>EasySearch issue:</strong><ul>{items}</ul></div>"

    google_section = ""
    if google["submitted"] and (google["ranked"] or google["unpriced"]):
        html_body = _render_google_ranked(
            {"ranked": google["ranked"], "unpriced": google["unpriced"], "info": google["info"]}
        )
        google_section = f"<section class=\"google-results\"><h2>EasySearch results</h2>{html_body}</section>"
    elif google["submitted"] and not google["errors"]:
        google_section = (
            "<p>No EasySearch results contained price information. Try a different query or increase the result count.</p>"
        )

    makeup_form = makeup["form_state"]
    google_form = google["form_state"]

    recency_value = google_form.get("recency") or ""
    recency_options = "".join(
        (
            f'<option value="{html.escape(value)}"'
            + (" selected" if value == recency_value else "")
            + f">{html.escape(label)}</option>"
        )
        for value, label in google_form.get("recency_choices", [])
    )

    return f"""<!doctype html>
<html lang=\"en\">
  <head>
    <meta charset=\"utf-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
    <title>EasyDirectory + EasySearch — Makeup Product Finder</title>
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
      .card {{ border: 1px solid #edf0f6; border-radius: 1rem; padding: 1.5rem; margin-bottom: 2rem; box-shadow: 0 10px 25px rgba(15,23,42,0.05); }}
      table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
      th, td {{ border-bottom: 1px solid #e5e7eb; padding: 0.75rem; text-align: left; }}
      th {{ text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.05em; color: #6b7280; }}
      td small {{ color: #94a3b8; }}
      @media (max-width: 640px) {{ main {{ margin: 0; border-radius: 0; }} .product-card {{ grid-template-columns: 1fr; text-align: center; }} .product-card img {{ margin: 0 auto; }} }}
    </style>
  </head>
  <body>
    <header>
      <h1>EasyDirectory + EasySearch</h1>
      <p>Explore EasyDirectory for curated Makeup API matches and EasySearch for fresh, price-ranked Google offers.</p>
    </header>
    <main>
      <section class=\"card\">
        <h2>EasyDirectory</h2>
        <form method=\"get\">
          <input type=\"hidden\" name=\"makeup_submitted\" value=\"1\" />
          <div><label for=\"query\">Search phrase</label><input id=\"query\" name=\"query\" value=\"{html.escape(makeup_form['query'])}\" placeholder=\"lipstick\" /></div>
          <div><label for=\"brand\">Brand</label><input id=\"brand\" name=\"brand\" value=\"{html.escape(makeup_form['brand'])}\" placeholder=\"maybelline\" /></div>
          <div><label for=\"product_type\">Product type</label><input id=\"product_type\" name=\"product_type\" value=\"{html.escape(makeup_form['product_type'])}\" placeholder=\"lipstick\" /></div>
          <div><label for=\"product_category\">Category</label><input id=\"product_category\" name=\"product_category\" value=\"{html.escape(makeup_form['product_category'])}\" placeholder=\"liquid\" /></div>
          <div><label for=\"product_tags\">Tags</label><input id=\"product_tags\" name=\"product_tags\" value=\"{html.escape(makeup_form['product_tags'])}\" placeholder=\"vegan, cruelty free\" /></div>
          <div><label for=\"price_min\">Min price</label><input id=\"price_min\" name=\"price_min\" value=\"{html.escape(makeup_form['price_min'])}\" /></div>
          <div><label for=\"price_max\">Max price</label><input id=\"price_max\" name=\"price_max\" value=\"{html.escape(makeup_form['price_max'])}\" /></div>
          <div><label for=\"rating_min\">Min rating</label><input id=\"rating_min\" name=\"rating_min\" value=\"{html.escape(makeup_form['rating_min'])}\" /></div>
          <div><label for=\"rating_max\">Max rating</label><input id=\"rating_max\" name=\"rating_max\" value=\"{html.escape(makeup_form['rating_max'])}\" /></div>
          <div class=\"actions\">
            <button type=\"submit\">Search products</button>
          </div>
        </form>
        {makeup_errors}
        {makeup_results_section}
      </section>
      <section class=\"card\">
        <h2>EasySearch</h2>
        <form method=\"get\">
          <input type=\"hidden\" name=\"google_submitted\" value=\"1\" />
          <div><label for=\"google_query\">Search phrase</label><input id=\"google_query\" name=\"google_query\" value=\"{html.escape(google_form['query'])}\" placeholder=\"maybelline superstay lipstick\" /></div>
          <div><label for=\"google_results\">Results to scan (1-10)</label><input id=\"google_results\" name=\"google_results\" value=\"{html.escape(google_form['results'])}\" /></div>
          <div><label for=\"google_recency\">Recency filter</label><select id=\"google_recency\" name=\"google_recency\">{recency_options}</select></div>
          <div class=\"actions\">
            <button type=\"submit\">Rank cheapest options</button>
          </div>
          </form>
        {google_errors}
        {google_section}
      </section>
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
        makeup_submitted = _first(params, "makeup_submitted") == "1"
        google_submitted = _first(params, "google_submitted") == "1"

        makeup_errors: List[str] = []
        google_errors: List[str] = []

        query = _first(params, "query").strip()
        brand = _first(params, "brand").strip() or None
        product_type = _first(params, "product_type").strip() or None
        product_category = _first(params, "product_category").strip() or None
        tags_raw = _first(params, "product_tags").strip()
        tag_list = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]

        price_min = _parse_float(_first(params, "price_min"), "Min price", makeup_errors)
        price_max = _parse_float(_first(params, "price_max"), "Max price", makeup_errors)
        rating_min = _parse_float(_first(params, "rating_min"), "Min rating", makeup_errors)
        rating_max = _parse_float(_first(params, "rating_max"), "Max rating", makeup_errors)

        products: List[Dict[str, Any]] = []

        if makeup_submitted and not makeup_errors:
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
                makeup_errors.append(str(exc))

        google_query = _first(params, "google_query").strip()
        google_results_requested = _parse_int(
            _first(params, "google_results"),
            "Results to scan",
            google_errors,
            minimum=1,
            maximum=10,
            default=5,
        )

        google_recency = _first(params, "google_recency").strip() or DEFAULT_GOOGLE_DATE_RESTRICT
        valid_recency_values = {value for value, _ in RECENCY_CHOICES}
        if google_recency not in valid_recency_values:
            google_errors.append("Select a valid recency filter.")
            google_recency = DEFAULT_GOOGLE_DATE_RESTRICT
        google_date_restrict = None if google_recency == "none" else google_recency

        google_ranked: List[Dict[str, Any]] = []
        google_unpriced: List[Dict[str, Any]] = []
        google_info: Dict[str, Any] = {}

        if google_submitted:
            if not google_query:
                google_errors.append("Please enter a Google search phrase.")
            elif not google_errors:
                try:
                    ranking = google_price_rank(
                        google_query,
                        num=google_results_requested,
                        date_restrict=google_date_restrict,
                    )
                    google_ranked = ranking["ranked"]
                    google_unpriced = ranking["unpriced"]
                    google_info = ranking["info"]
                except HTTPRequestError as exc:
                    google_errors.append(f"Google Search failed: {exc}")

        makeup_form_state = {
            "query": query,
            "brand": brand or "",
            "product_type": product_type or "",
            "product_category": product_category or "",
            "product_tags": tags_raw,
            "price_min": _first(params, "price_min"),
            "price_max": _first(params, "price_max"),
            "rating_min": _first(params, "rating_min"),
            "rating_max": _first(params, "rating_max"),
        }

        google_form_state = {
            "query": google_query,
            "results": str(google_results_requested),
            "recency": google_recency,
            "recency_choices": RECENCY_CHOICES,
        }

        html_body = _render_page(
            {
                "makeup": {
                    "submitted": makeup_submitted,
                    "products": products,
                    "errors": makeup_errors,
                    "form_state": makeup_form_state,
                },
                "google": {
                    "submitted": google_submitted,
                    "ranked": google_ranked,
                    "unpriced": google_unpriced,
                    "info": google_info,
                    "errors": google_errors,
                    "form_state": google_form_state,
                },
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
    print(f"Serving EasyDirectory + EasySearch UI on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
