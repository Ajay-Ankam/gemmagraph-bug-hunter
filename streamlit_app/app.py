"""GemmaGraph Bug Hunter - Streamlit client.

An all-Python alternative to the HTML dashboard. It talks to the same FastAPI
backend, so validation, caching, Graphify and Gemma 4 behave identically.

Run (backend must be running on :8000):
    streamlit run streamlit_app/app.py
Point at another backend with GEMMAGRAPH_API_URL=https://your-app.example.com
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from api_client import DEFAULT_API_URL, ApiClient, ApiError  # noqa: E402
from components.audit import render_audit  # noqa: E402
from components.patch import render_patch  # noqa: E402
from components.topology import render_metrics, render_topology  # noqa: E402
from components.vision import render_vision  # noqa: E402

PRESETS = {
    "Demo 1: Buggy app": "demo_buggy_app",
    "Demo 2: Scan self": ".",
}

st.set_page_config(page_title="GemmaGraph Bug Hunter", page_icon="🕸️", layout="wide")


def run_scan(client: ApiClient, repo: str, force: bool) -> None:
    """Call the backend and store the result (or error) in session state."""
    st.session_state.pop("vision_result", None)
    started = time.perf_counter()
    spinner = "Running Graphify + live Gemma 4 audit…" if force else "Scanning…"
    with st.spinner(spinner):
        try:
            st.session_state["scan"] = client.scan(repo, force_refresh=force)
            st.session_state["scan_error"] = None
        except ApiError as exc:
            st.session_state["scan_error"] = str(exc)
            return
    st.session_state["round_trip_ms"] = round((time.perf_counter() - started) * 1000)


def sidebar() -> ApiClient:
    """Backend status, scan controls and presets. Returns the API client."""
    with st.sidebar:
        st.title("🕸️ GemmaGraph")
        st.caption("Graphify AST knowledge graph + Gemma 4 code review")
        api_url = st.text_input("Backend URL", value=DEFAULT_API_URL)
        client = ApiClient(api_url)

        try:
            health = client.health()
            cached = health["disk_cache"]["cached_scans"]
            (st.success if health.get("ready") else st.warning)(
                f"API {health['status']} · {cached} cached scans · {health['model']}"
            )
        except ApiError as exc:
            st.error(str(exc))

        st.divider()
        with st.form("scan_form"):
            repo = st.text_input("Repository", value="demo_buggy_app",
                                 help="'.', 'demo_buggy_app' or https://github.com/<owner>/<repo>")
            force = st.checkbox("Force refresh (live Gemma 4 audit)")
            submitted = st.form_submit_button("Scan repository", type="primary", width="stretch")
        if submitted:
            run_scan(client, repo.strip() or ".", force)

        st.caption("One-click demos")
        for label, target in PRESETS.items():
            if st.button(label, key=f"preset_{target}", width="stretch"):
                run_scan(client, target, False)

        st.divider()
        st.caption("Powered by Gemma 4 (26B-A4B MoE) · Graphify AST engine · FastAPI")
    return client


def scan_header(scan: dict) -> None:
    """Repo name, cache badge and latency."""
    badge = "⚡ CACHE HIT" if scan.get("cached") else "🧠 LIVE GEMMA 4 AUDIT"
    st.markdown(f"### `{scan['repo']}`")
    parts = [f"**{badge}**", f"{st.session_state.get('round_trip_ms', 0):,} ms round trip"]
    timings = scan.get("timings_ms") or {}
    if not scan.get("cached") and timings:
        parts.append(f"graphify {timings.get('graphify', 0) / 1000:.1f}s · gemma {timings.get('gemma', 0) / 1000:.1f}s")
    if scan.get("scanned_at"):
        parts.append("scanned " + time.strftime("%Y-%m-%d %H:%M", time.localtime(scan["scanned_at"])))
    st.caption(" · ".join(parts))


def main() -> None:
    """Page entry point."""
    client = sidebar()
    st.title("GemmaGraph Bug Hunter")

    if st.session_state.get("scan_error"):
        st.error(f"Scan failed: {st.session_state['scan_error']}")

    scan = st.session_state.get("scan")
    if not scan:
        st.info("Pick a demo in the sidebar, or enter a public GitHub URL to run an architecture health-check.")
        return

    audit = scan.get("audit") or {}
    graph = scan.get("graph_summary") or {}
    scan_header(scan)
    render_metrics(graph, audit)

    tab_audit, tab_graph, tab_patch, tab_vision = st.tabs(
        ["🛡️ Gemma 4 audit", "🕸️ Graphify topology", "🩹 Fix patch", "👁️ Architecture drift"]
    )
    with tab_audit:
        render_audit(audit)
    with tab_graph:
        render_topology(graph, scan.get("report_md", ""))
    with tab_patch:
        render_patch(audit.get("git_diff_patch", ""), scan["repo"])
    with tab_vision:
        render_vision(client, scan)


main()
