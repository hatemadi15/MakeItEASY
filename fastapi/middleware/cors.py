from __future__ import annotations

from typing import Any


class CORSMiddleware:
    def __init__(self, app: Any, **_: Any) -> None:
        self.app = app


__all__ = ["CORSMiddleware"]
