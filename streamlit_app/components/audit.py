"""Gemma 4 audit section: verdict, security hotspots, cycles, dead code, fixes."""

from __future__ import annotations

from typing import Any

import streamlit as st

SEVERITY_ICONS = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}


def render_hotspot(hotspot: dict[str, Any]) -> None:
    """One security finding as a bordered card."""
    severity = str(hotspot.get("severity", "low")).lower()
    location = f"{hotspot.get('file', '?')}:{hotspot.get('line', '?')}"
    with st.container(border=True):
        st.markdown(f"{SEVERITY_ICONS.get(severity, '⚪')} **{severity.upper()}** · {hotspot.get('category', '')}")
        st.code(location, language=None)
        st.write(hotspot.get("explanation", ""))
        radius = hotspot.get("blast_radius") or []
        if radius:
            st.caption("Blast radius: " + ", ".join(f"`{r}`" for r in radius))


def render_audit(audit: dict[str, Any]) -> None:
    """Full Gemma 4 audit."""
    if audit.get("error"):
        st.warning(audit["error"])
    if audit.get("summary"):
        st.info(audit["summary"])

    hotspots = audit.get("security_hotspots", [])
    st.subheader(f"Security hotspots ({len(hotspots)})")
    if not hotspots:
        st.success("No security hotspots reported.")
    cols = st.columns(2)
    for i, hotspot in enumerate(hotspots):
        with cols[i % 2]:
            render_hotspot(hotspot)

    left, right = st.columns(2, gap="large")
    with left:
        st.subheader("Circular dependencies")
        cycles = audit.get("circular_dependencies", [])
        if not cycles:
            st.caption("Gemma confirmed no circular dependencies.")
        for cycle in cycles:
            path = cycle.get("cycle")
            st.markdown(f"**{' → '.join(path) if isinstance(path, list) else path}**")
            if cycle.get("impact"):
                st.write(f"Impact: {cycle['impact']}")
            if cycle.get("fix"):
                st.write(f"Fix: {cycle['fix']}")

        st.subheader("Prioritized fixes")
        for fix in audit.get("prioritized_fixes", []):
            st.markdown(f"{fix.get('rank')}. **{fix.get('title')}** (`{fix.get('file')}`)  \n{fix.get('reason', '')}")

    with right:
        st.subheader("Dead code")
        dead = audit.get("dead_code", [])
        if dead:
            st.dataframe(
                [{"Symbol": d.get("symbol"), "File": d.get("file"), "Confidence": d.get("confidence"),
                  "Reason": d.get("reason")} for d in dead],
                hide_index=True, width="stretch",
            )
        else:
            st.caption("No dead code reported.")
