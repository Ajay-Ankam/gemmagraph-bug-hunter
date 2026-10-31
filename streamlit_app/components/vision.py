"""Multimodal architecture-drift check (Gemma 4 vision)."""

from __future__ import annotations

from typing import Any

import streamlit as st

from api_client import ApiClient, ApiError

ALLOWED_EXTENSIONS = ["png", "jpg", "jpeg", "webp"]
MAX_BYTES = 5 * 1024 * 1024


def render_vision(client: ApiClient, scan: dict[str, Any]) -> None:
    """Upload a diagram and compare it with the scanned code graph."""
    st.subheader("Multimodal architecture drift check")
    st.caption("Upload your intended architecture diagram. Gemma 4 vision compares it with the real Graphify structure.")

    upload = st.file_uploader("Architecture diagram (PNG, JPEG or WebP, up to 5 MB)", type=ALLOWED_EXTENSIONS)
    if upload is None:
        return
    st.image(upload, width=360)
    if upload.size > MAX_BYTES:
        st.error("Image must be 5 MB or smaller.")
        return

    if st.button("Run drift check", type="primary"):
        with st.spinner("Gemma 4 is comparing the diagram with the code graph…"):
            try:
                result = client.multimodal_audit(scan["scan_id"], upload.name, upload.getvalue(), upload.type)
            except ApiError as exc:
                st.error(f"Vision audit failed: {exc}")
                return
        st.session_state["vision_result"] = result

    result = st.session_state.get("vision_result")
    if result and result.get("scan_id") == scan["scan_id"]:
        st.caption(f"Gemma 4 vision · {result.get('latency_ms', 0):,.0f} ms")
        st.markdown(result.get("analysis_markdown", ""))
