from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional

from . import FastAPI, HTTPException


class _Response:
    def __init__(self, status_code: int, json_data: Any) -> None:
        self.status_code = status_code
        self._json_data = json_data

    def json(self) -> Any:
        return self._json_data


class TestClient:
    def __init__(self, app: FastAPI, *, client_host: str = "testclient") -> None:
        self.app = app
        self._client_host = client_host

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> _Response:
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
    ) -> _Response:
        return self._request("POST", path, params=json)

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> _Response:
        try:
            status_code, body = self.app.handle(
                method,
                path,
                params=params,
                client_host=self._client_host,
            )
            if is_dataclass(body):
                body = asdict(body)
        except HTTPException as exc:  # pragma: no cover - simple error path
            status_code = exc.status_code
            body = {"detail": exc.detail}
        return _Response(status_code=status_code, json_data=body)


__all__ = ["TestClient"]
