from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error, parse, request

try:  # pragma: no cover - exercised in environments with requests installed
    import requests as _requests  # type: ignore
except Exception:  # pragma: no cover - fallback path
    _requests = None

if _requests is not None:  # pragma: no cover - defer to real requests if available
    RequestException = _requests.RequestException
    get = _requests.get
    post = _requests.post
else:

    class RequestException(Exception):
        """Fallback request exception when requests is unavailable."""

    @dataclass
    class _Response:
        body: bytes
        status_code: int
        headers: Dict[str, str]
        encoding: Optional[str] = None

        def __post_init__(self) -> None:
            if not self.encoding:
                self.encoding = self._detect_encoding()

        def raise_for_status(self) -> None:
            if 400 <= self.status_code:
                raise RequestException(f"HTTP {self.status_code}")

        @property
        def text(self) -> str:
            encoding = self.encoding or "utf-8"
            return self.body.decode(encoding, errors="replace")

        def json(self) -> Any:
            return json.loads(self.text)

        def _detect_encoding(self) -> str:
            content_type = self.headers.get("Content-Type", "")
            match = re.search(r"charset=([^;]+)", content_type)
            if match:
                return match.group(1)
            return "utf-8"

    def _open(url: str, *, data: Optional[bytes], timeout: Optional[int], headers: Dict[str, str]) -> _Response:
        req = request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                status = getattr(resp, "status", resp.getcode())
                header_map = {k: v for k, v in resp.headers.items()}
                return _Response(body=body, status_code=status, headers=header_map)
        except error.URLError as exc:  # pragma: no cover - network failures
            raise RequestException(str(exc)) from exc

    def _prepare_url(url: str, params: Optional[Dict[str, Any]]) -> str:
        if not params:
            return url
        query = parse.urlencode(params, doseq=True)
        separator = "&" if parse.urlsplit(url).query else "?"
        return f"{url}{separator}{query}"

    def get(url: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[int] = None):
        prepared = _prepare_url(url, params)
        return _open(prepared, data=None, timeout=timeout, headers={})

    def post(
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        timeout: Optional[int] = None,
    ):
        prepared = _prepare_url(url, params)
        data: Optional[bytes] = None
        headers: Dict[str, str] = {}
        if json is not None:
            data = json.dumps(json).encode("utf-8")
            headers["Content-Type"] = "application/json"
        return _open(prepared, data=data, timeout=timeout, headers=headers)
