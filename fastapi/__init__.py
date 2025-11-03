from __future__ import annotations

import inspect
from dataclasses import asdict, is_dataclass
from types import SimpleNamespace
from typing import Any, Callable, Dict, Optional, Tuple, get_args, get_origin


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def Query(default: Any = None, **_: Any) -> Any:
    return default


class Request:
    def __init__(self, *, client_host: str = "testclient", headers: Optional[Dict[str, str]] = None) -> None:
        self.client = SimpleNamespace(host=client_host, port=None)
        self.headers = headers or {}


class FastAPI:
    def __init__(self, *, title: str = "FastAPI", version: str = "0.1.0") -> None:
        self.title = title
        self.version = version
        self._routes: Dict[Tuple[str, str], tuple[Callable[..., Any], int]] = {}
        self._middlewares: list[tuple[type, dict[str, Any]]] = []

    def add_middleware(self, middleware_cls: type, **options: Any) -> None:
        self._middlewares.append((middleware_cls, options))

    def get(
        self,
        path: str,
        response_model: Any | None = None,
        *,
        status_code: int = 200,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._routes[("GET", path)] = (func, status_code)
            return func

        return decorator

    def post(
        self,
        path: str,
        response_model: Any | None = None,
        *,
        status_code: int = 200,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._routes[("POST", path)] = (func, status_code)
            return func

        return decorator

    def handle(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        client_host: str = "testclient",
        headers: Optional[Dict[str, str]] = None,
    ) -> tuple[int, Any]:
        key = (method.upper(), path)
        if key not in self._routes:
            raise HTTPException(status_code=404, detail="Not found")
        func, default_status = self._routes[key]
        params = dict(params or {})
        params.setdefault("request", Request(client_host=client_host, headers=headers))
        kwargs = self._resolve_params(func, params)
        result = func(**kwargs)
        status_code = default_status
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], int):
            status_code, result = result
        if is_dataclass(result):
            result = asdict(result)
        return status_code, result

    @staticmethod
    def _resolve_params(func: Callable[..., Any], params: Dict[str, Any]) -> Dict[str, Any]:
        signature = inspect.signature(func)
        resolved: Dict[str, Any] = {}
        for name, parameter in signature.parameters.items():
            value = params.get(name, parameter.default)
            if value is inspect._empty:
                value = None
            if value is Ellipsis:
                raise HTTPException(status_code=422, detail=f"Missing required parameter: {name}")
            if value is None:
                resolved[name] = None
                continue
            annotation = parameter.annotation
            resolved[name] = _convert_value(value, annotation)
        return resolved


def _convert_value(value: Any, annotation: Any) -> Any:
    if isinstance(value, Request):
        return value

    origin = get_origin(annotation)
    if origin is not None:
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            annotation = args[0]

    if annotation is int:
        return int(value)
    if annotation is float:
        return float(value)
    if annotation is bool:
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}
    if annotation is Request:
        return value
    return value


__all__ = ["FastAPI", "HTTPException", "Query", "Request"]
