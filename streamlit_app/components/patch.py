"""Auto-generated fix patch: syntax-highlighted diff, copy (built into st.code) and download."""

from __future__ import annotations

import streamlit as st


def render_patch(patch: str, repo: str) -> None:
    """Show Gemma's git_diff_patch for fix #1."""
    st.subheader("Auto-generated fix patch")
    if not patch.strip():
        st.caption("No patch generated.")
        return
    st.code(patch, language="diff")
    st.download_button(
        "Download .patch", data=patch.rstrip("\n") + "\n",
        file_name=f"gemmagraph-fix-{repo.strip('./').replace('/', '_') or 'self'}.patch",
        mime="text/x-diff",
    )
    st.caption("Apply with `git apply --check gemmagraph-fix.patch && git apply gemmagraph-fix.patch`.")
