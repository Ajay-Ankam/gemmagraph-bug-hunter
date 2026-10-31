"""GemmaGraph Bug Hunter - FastAPI backend and dashboard host.

Endpoints:
    GET  /                      Dashboard (frontend/index.html)
    GET  /api/health            Uptime, model, Graphify status, cache + env readiness
    POST /api/scan              Graphify graph + Gemma 4 audit (disk-cached)
    GET  /api/scan/{scan_id}    Fetch a cached scan (CDN/Varnish cacheable)
    POST /api/multimodal-audit  Gemma 4 vision: architecture diagram vs. real graph

Run locally (from backend/):  uvicorn main:app --port 8000
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import os
import platform
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
CACHE_FILE = Path(os.getenv("SCAN_CACHE_FILE", BACKEND_DIR / ".scan_cache.json"))

try:  # load GEMINI_API_KEY from the project-level .env when running locally
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:  # pragma: no cover - python-dotenv is in requirements.txt
    pass

import gemma_agent  # noqa: E402  (needs env loaded first)
from graph_engine import (  # noqa: E402
    GraphEngineError,
    InvalidTargetError,
    ScanTarget,
    analyze_repo_graph,
    validate_target,
)

logger = logging.getLogger("gemmagraph")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

STARTED_AT = time.time()
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# Declared MIME type -> required leading "magic" bytes. The Content-Type header is
# client-controlled, so the file signature is checked too.
IMAGE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/webp": (b"RIFF",),
}
CACHED_HEADERS = {"Cache-Control": "public, max-age=300"}
NO_STORE_HEADERS = {"Cache-Control": "no-store"}
# Live audits spend Gemini quota; cap concurrent ones per worker process.
_LIVE_SCAN_SLOTS = threading.BoundedSemaphore(int(os.getenv("MAX_LIVE_SCANS", "2")))

app = FastAPI(
    title="GemmaGraph Bug Hunter",
    description="Graphify AST knowledge graphs + Gemma 4 code-review agent.",
    version="1.0.0",
)

class CachedStaticFiles(StaticFiles):
    """StaticFiles that adds ``Cache-Control`` so Varnish/browsers cache the dashboard assets."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers.update(CACHED_HEADERS)
        return response


# Dashboard assets: /static/css/*.css, /static/js/*.js (ES modules).
app.mount("/static", CachedStaticFiles(directory=FRONTEND_DIR, check_dir=False), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# --------------------------------------------------------------------------- #
# Error handling: every error is clean JSON, never a traceback
# --------------------------------------------------------------------------- #

def _error(status: int, message: str, **extra: Any) -> JSONResponse:
    """Uniform error envelope: ``{"error": ..., "status": "error"}``."""
    return JSONResponse(
        status_code=status,
        content={"error": message, "status": "error", **extra},
        headers=NO_STORE_HEADERS,
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Convert raised HTTP errors (404, 413, 415, 429, ...) to the JSON envelope."""
    return _error(exc.status_code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return 422 with readable messages (never echoes internal objects)."""
    issues = [
        {"field": ".".join(str(p) for p in err.get("loc", ()) if p != "body"), "message": err.get("msg", "")}
        for err in exc.errors()
    ]
    summary = "; ".join(f"{i['field']}: {i['message']}" for i in issues) or "Invalid request"
    return _error(422, summary, details=issues)


@app.exception_handler(InvalidTargetError)
async def invalid_target_handler(_: Request, exc: InvalidTargetError) -> JSONResponse:
    """Rejected scan targets are client errors."""
    return _error(400, str(exc))


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: log the traceback server-side, return a generic message."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error(500, "Internal server error")


# --------------------------------------------------------------------------- #
# Persistent scan cache (survives restarts/redeploys; safe across workers)
# --------------------------------------------------------------------------- #

_SCANS_LOCK = threading.Lock()


def _load_cache() -> dict[str, dict[str, Any]]:
    """Read the on-disk cache; a missing or corrupt file yields an empty cache."""
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


_SCANS: dict[str, dict[str, Any]] = _load_cache()


def _get_cached(scan_id: str) -> dict[str, Any] | None:
    """Look up a scan in memory, falling back to disk (another worker may have written it)."""
    with _SCANS_LOCK:
        hit = _SCANS.get(scan_id)
        if hit is None:
            _SCANS.update(_load_cache())
            hit = _SCANS.get(scan_id)
        return hit


def _store(scan_id: str, result: dict[str, Any]) -> None:
    """Merge one scan into the on-disk cache with an atomic replace."""
    with _SCANS_LOCK:
        merged = {**_load_cache(), **_SCANS, scan_id: result}
        _SCANS.clear()
        _SCANS.update(merged)
        tmp = CACHE_FILE.with_name(f"{CACHE_FILE.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(merged, indent=1, sort_keys=True, default=str), encoding="utf-8")
        os.replace(tmp, CACHE_FILE)


def _scan_id(key: str) -> str:
    """Stable 12-char id derived from the portable target key."""
    return hashlib.sha1(key.encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #

class ScanRequest(BaseModel):
    """Body of ``POST /api/scan``."""

    repo_url: str = Field(
        ".", max_length=200,
        description="'.', 'demo_buggy_app', or https://github.com/<owner>/<repo>",
    )
    force_refresh: bool = Field(False, description="Bypass caches: re-run Graphify and Gemma 4.")

    @field_validator("repo_url")
    @classmethod
    def _check_target(cls, value: str) -> str:
        """Reject anything outside the allowlist before any work happens."""
        try:
            validate_target(value)
        except InvalidTargetError as exc:
            raise ValueError(str(exc)) from None
        return value


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page dashboard."""
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="frontend/index.html not found")
    return FileResponse(FRONTEND_INDEX, media_type="text/html", headers=CACHED_HEADERS)


def _graphify_status() -> dict[str, Any]:
    """Report the installed Graphify version and how its CLI will be invoked."""
    try:
        version = importlib.metadata.version("graphifyy")
    except importlib.metadata.PackageNotFoundError:
        return {"installed": False, "version": None, "cli": None}
    return {"installed": True, "version": version, "cli": shutil.which("graphify") or "python -m graphify"}


@app.get("/api/health")
def health() -> JSONResponse:
    """Liveness + readiness: uptime, runtime, model, Graphify, cache and env checks."""
    with _SCANS_LOCK:
        repos = sorted(str(s.get("repo")) for s in _SCANS.values())
    graphify = _graphify_status()
    checks = {
        "gemini_api_key": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "graphify_installed": graphify["installed"],
        "git_available": shutil.which("git") is not None,
        "frontend_present": FRONTEND_INDEX.exists(),
        "cache_dir_writable": os.access(CACHE_FILE.parent, os.W_OK),
    }
    return JSONResponse(
        {
            "status": "ok" if all(checks.values()) else "degraded",
            "uptime_seconds": round(time.time() - STARTED_AT, 1),
            "python_version": platform.python_version(),
            "model": gemma_agent.MODEL_ID,
            "graphify": graphify,
            "disk_cache": {"file": CACHE_FILE.name, "cached_scans": len(repos), "repos": repos},
            "ready": all(checks.values()),
            "checks": checks,
        },
        headers=CACHED_HEADERS,
    )


@app.post("/api/scan")
def scan(req: ScanRequest) -> JSONResponse:
    """Scan a repository: Graphify graph analysis followed by a Gemma 4 audit.

    Cached results (from ``backend/.scan_cache.json``) return in milliseconds and
    carry ``Cache-Control: public, max-age=300``. Live scans are ``no-store``.
    """
    started = time.perf_counter()
    target: ScanTarget = validate_target(req.repo_url)
    scan_id = _scan_id(target.key)

    if not req.force_refresh:
        cached = _get_cached(scan_id)
        if cached:  # instant demo playback: skip Graphify and Gemma entirely
            latency = round((time.perf_counter() - started) * 1000, 1)
            return JSONResponse({**cached, "cached": True, "latency_ms": latency}, headers=CACHED_HEADERS)

    if not _LIVE_SCAN_SLOTS.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Too many live scans in progress; retry shortly.")
    try:
        try:
            graph = analyze_repo_graph(target, use_cache=not req.force_refresh)
        except InvalidTargetError:
            raise
        except GraphEngineError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        graph_ms = (time.perf_counter() - started) * 1000

        audit_started = time.perf_counter()
        try:
            audit = gemma_agent.audit_code_graph(
                graph["graph_summary"], graph["report_md"], graph["code_snippets"]
            )
        except Exception as exc:  # surface model/API errors but still return the graph
            logger.warning("Gemma audit failed for %s: %s", target.key, exc)
            audit = {"error": f"Gemma audit failed: {type(exc).__name__}"}
        audit_ms = (time.perf_counter() - audit_started) * 1000
    finally:
        _LIVE_SCAN_SLOTS.release()

    result: dict[str, Any] = {
        "scan_id": scan_id,
        "repo": target.key,
        "model": gemma_agent.MODEL_ID,
        "graph_summary": graph["graph_summary"],
        "report_md": graph["report_md"],
        "critical_files": list(graph["code_snippets"].keys()),
        "audit": audit,
        "timings_ms": {"graphify": round(graph_ms, 1), "gemma": round(audit_ms, 1)},
        "scanned_at": int(time.time()),
    }
    if "error" not in audit:
        _store(scan_id, result)
    latency = round((time.perf_counter() - started) * 1000, 1)
    return JSONResponse({**result, "cached": False, "latency_ms": latency}, headers=NO_STORE_HEADERS)


@app.get("/api/scan/{scan_id}")
def get_scan(scan_id: str) -> JSONResponse:
    """Return a previously cached scan by id (GET, so HTTP caches can store it)."""
    if not (len(scan_id) == 12 and all(c in "0123456789abcdef" for c in scan_id)):
        raise HTTPException(status_code=404, detail="Unknown scan_id")
    result = _get_cached(scan_id)
    if not result:
        raise HTTPException(status_code=404, detail="Unknown scan_id")
    return JSONResponse({**result, "cached": True}, headers=CACHED_HEADERS)


def _validate_image(data: bytes, mime_type: str) -> None:
    """Enforce size, MIME allowlist and a matching file signature."""
    if mime_type not in IMAGE_SIGNATURES:
        raise HTTPException(status_code=415, detail="Unsupported image type. Allowed: PNG, JPEG, WebP.")
    if not data:
        raise HTTPException(status_code=400, detail="Empty image upload")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 5 MB limit")
    signature_ok = any(data.startswith(sig) for sig in IMAGE_SIGNATURES[mime_type])
    if mime_type == "image/webp":
        signature_ok = signature_ok and data[8:12] == b"WEBP"
    if not signature_ok:
        raise HTTPException(status_code=415, detail=f"File content is not a valid {mime_type} image")


@app.post("/api/multimodal-audit")
async def multimodal_audit(
    scan_id: str = Form(..., max_length=12),
    image: UploadFile = File(...),
) -> JSONResponse:
    """Compare an uploaded architecture diagram with the scanned code graph (Gemma 4 vision)."""
    scan_result = _get_cached(scan_id)
    if not scan_result:
        raise HTTPException(status_code=404, detail="Unknown scan_id - run POST /api/scan first")

    mime_type = (image.content_type or "").lower()
    if mime_type not in IMAGE_SIGNATURES:  # fail fast before reading the body
        raise HTTPException(status_code=415, detail="Unsupported image type. Allowed: PNG, JPEG, WebP.")
    data = await image.read(MAX_IMAGE_BYTES + 1)
    _validate_image(data, mime_type)

    started = time.perf_counter()
    try:
        analysis = await run_in_threadpool(
            gemma_agent.audit_architecture_diagram, data, mime_type, scan_result["graph_summary"]
        )
    except Exception as exc:
        logger.warning("Gemma vision audit failed: %s", exc)
        raise HTTPException(status_code=502, detail="Gemma vision audit failed; please retry.") from exc

    return JSONResponse(
        {
            "scan_id": scan_id,
            "repo": scan_result["repo"],
            "model": gemma_agent.MODEL_ID,
            "filename": os.path.basename(image.filename or "upload"),
            "analysis_markdown": analysis,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        },
        headers=NO_STORE_HEADERS,
    )
