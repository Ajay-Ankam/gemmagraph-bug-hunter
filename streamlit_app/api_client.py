"""HTTP client for the GemmaGraph Bug Hunter FastAPI backend.

The Streamlit app is a thin client: all validation, caching, Graphify and Gemma 4
work happens in the backend, exactly as for the HTML dashboard and the CLI.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_URL = os.getenv("GEMMAGRAPH_API_URL", "http://127.0.0.1:8000")
SCAN_TIMEOUT_S = 300.0  # live Graphify + Gemma 4 audits take ~15-45 s
VISION_TIMEOUT_S = 120.0


class ApiError(RuntimeError):
    """Backend returned an error envelope or could not be reached."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    """Minimal typed wrapper around the backend's REST endpoints."""

    def __init__(self, base_url: str = DEFAULT_API_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, timeout: float = 15.0, **kwargs: Any) -> dict[str, Any]:
        """Send a request and unwrap the ``{"error", "status"}`` envelope on failure."""
        try:
            res = httpx.request(method, f"{self.base_url}{path}", timeout=timeout, **kwargs)
        except httpx.TimeoutException as exc:
            raise ApiError("The backend took too long to respond.") from exc
        except httpx.HTTPError as exc:
            raise ApiError(f"Cannot reach the backend at {self.base_url}. Is uvicorn running?") from exc
        try:
            data = res.json()
        except ValueError:
            data = {}
        if res.is_error:
            raise ApiError(data.get("error") or data.get("detail") or f"HTTP {res.status_code}", res.status_code)
        return data

    def health(self) -> dict[str, Any]:
        """``GET /api/health``."""
        return self._request("GET", "/api/health")

    def scan(self, repo_url: str, force_refresh: bool = False) -> dict[str, Any]:
        """``POST /api/scan``: cached results return in milliseconds."""
        return self._request(
            "POST", "/api/scan", timeout=SCAN_TIMEOUT_S,
            json={"repo_url": repo_url, "force_refresh": force_refresh},
        )

    def multimodal_audit(self, scan_id: str, filename: str, data: bytes, mime_type: str) -> dict[str, Any]:
        """``POST /api/multimodal-audit``: Gemma 4 vision architecture-drift check."""
        return self._request(
            "POST", "/api/multimodal-audit", timeout=VISION_TIMEOUT_S,
            data={"scan_id": scan_id}, files={"image": (filename, data, mime_type)},
        )
