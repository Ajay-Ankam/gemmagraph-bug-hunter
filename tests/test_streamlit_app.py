"""Headless tests for the Streamlit client (streamlit.testing.AppTest).

The backend is replaced by a fake that serves the committed cached scan, so
these run offline with no server and no API key. Skipped if Streamlit is not
installed (it is an optional client, not a backend dependency).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "streamlit_app" / "app.py"
sys.path.insert(0, str(ROOT / "streamlit_app"))

import api_client  # noqa: E402
from components.topology import file_graph_to_dot  # noqa: E402

CACHE = json.loads((ROOT / "backend" / ".scan_cache.json").read_text(encoding="utf-8"))
DEMO_SCAN = CACHE[hashlib.sha1(b"demo_buggy_app").hexdigest()[:12]]

HEALTH = {
    "status": "ok", "ready": True, "model": "gemma-4-26b-a4b-it",
    "disk_cache": {"cached_scans": 2}, "checks": {"gemini_api_key": True},
}


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch ApiClient so the app talks to canned data; returns the scanned targets."""
    calls: list[str] = []

    def scan(self: Any, repo_url: str, force_refresh: bool = False) -> dict[str, Any]:
        calls.append(repo_url)
        if repo_url != "demo_buggy_app":
            raise api_client.ApiError("Unsupported target.", 422)
        return {**DEMO_SCAN, "cached": True, "latency_ms": 0.5}

    monkeypatch.setattr(api_client.ApiClient, "health", lambda self: HEALTH)
    monkeypatch.setattr(api_client.ApiClient, "scan", scan)
    return calls


def test_initial_page_prompts_for_a_scan(fake_backend: list[str]) -> None:
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    assert not at.exception
    assert any("Pick a demo" in i.value for i in at.info)
    assert any("API ok" in s.value for s in at.sidebar.success)
    assert fake_backend == []


def test_demo_preset_renders_full_audit(fake_backend: list[str]) -> None:
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.sidebar.button(key="preset_demo_buggy_app").click().run()

    assert not at.exception
    assert fake_backend == ["demo_buggy_app"]
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Import cycles"] == "1"
    assert metrics["Nodes"] == str(DEMO_SCAN["graph_summary"]["stats"]["nodes"])
    hotspots = [s for s in at.subheader if s.value.startswith("Security hotspots")]
    assert hotspots and hotspots[0].value != "Security hotspots (0)"
    diffs = [c.value for c in at.code if c.language == "diff"]
    assert diffs and diffs[0].startswith("--- a/db.py")
    assert any("auth.py → db.py → auth.py" in e.value for e in at.error)


def test_backend_errors_are_shown_not_raised(fake_backend: list[str]) -> None:
    at = AppTest.from_file(str(APP), default_timeout=30).run()
    at.sidebar.text_input[1].input("https://evil.com/x; rm -rf /")
    at.sidebar.button[0].click().run()  # form submit button
    assert not at.exception
    assert any("Scan failed: Unsupported target." in e.value for e in at.error)


def test_file_graph_to_dot_marks_cycles_and_quotes_ids() -> None:
    dot = file_graph_to_dot({
        "nodes": [{"id": 'a"b.py', "in_cycle": True}, {"id": "c.py", "in_cycle": False}],
        "edges": [{"source": 'a"b.py', "target": "c.py", "in_cycle": True}],
    })
    assert dot.startswith("digraph G {") and dot.endswith("}")
    assert '"a\\"b.py" -> "c.py" [color="#f43f5e", penwidth=2];' in dot
