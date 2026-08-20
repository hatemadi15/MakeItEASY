from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from . import service
from .rate_limiter import RateLimitExceeded


class MakeupFinderHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._write_json(200, {"status": "ok"})
            return

        if parsed.path == "/search":
            self._handle_search(parse_qs(parsed.query))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/crawl/test":
            self._handle_crawl_test()
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # pragma: no cover - silence default logging
        return

    def _handle_search(self, params: dict[str, list[str]]) -> None:
        query = self._first(params, "q")
        if not query:
            self._write_json(400, {"detail": "Query cannot be empty"})
            return

        country = self._first(params, "country")
        limit = self._int(params, "limit", default=20, minimum=1, maximum=50)
        condition = self._first(params, "condition") or "new"
        normalized_condition = condition.lower()
        if normalized_condition not in {"new", "any"}:
            self._write_json(400, {"detail": "Unsupported condition filter"})
            return
        effective_condition = None if normalized_condition == "any" else normalized_condition
        try:
            service.enforce_rate_limit(self.client_address[0])
        except RateLimitExceeded as exc:
            self._write_json(
                429,
                {"detail": {"error": "rate_limited", "retry_after": exc.retry_after}},
                headers={"Retry-After": str(exc.retry_after)},
            )
            return

        payload = service.perform_search(
            query=query,
            country=country,
            condition=effective_condition,
            limit=limit,
        )

        response_payload = {
            "query": query,
            "currency": payload.currency_label,
            "generated_at": payload.generated_at.isoformat() + "Z",
            "offers": payload.offers,
            "cached": payload.cached,
        }
        self._write_json(200, response_payload)

    def _handle_crawl_test(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(content_length) if content_length else b""
        if not body:
            self._write_json(400, {"detail": "Missing body"})
            return
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"detail": "Invalid JSON"})
            return
        url = payload.get("url")
        if not url or not isinstance(url, str):
            self._write_json(400, {"detail": "Missing url"})
            return
        response = {"status": "queued", "url": url}
        self._write_json(202, response)

    def _first(self, params: dict[str, list[str]], key: str) -> str | None:
        values = params.get(key)
        if not values:
            return None
        return values[0]

    def _int(
        self,
        params: dict[str, list[str]],
        key: str,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        value = self._first(params, key)
        if value is None:
            return default
        try:
            number = int(value)
        except ValueError:
            return default
        return max(minimum, min(maximum, number))

    def _write_json(
        self,
        status: int,
        payload: dict[str, object],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        data = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    httpd = HTTPServer((host, port), MakeupFinderHandler)
    print(f"Serving Cheapest Makeup Finder on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run()
