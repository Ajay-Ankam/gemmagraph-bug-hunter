"""Graphify topology section: metrics, dependency graph, god nodes, cycles, report."""

from __future__ import annotations

from typing import Any

import streamlit as st

CYCLE_COLOR = "#f43f5e"
NODE_COLOR = "#8b5cf6"
EDGE_COLOR = "#475569"


def _dot_id(value: str) -> str:
    """Quote a file path as a Graphviz identifier."""
    return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'


def file_graph_to_dot(file_graph: dict[str, Any]) -> str:
    """Convert ``graph_summary.file_graph`` to Graphviz DOT; import cycles are red."""
    lines = [
        "digraph G {",
        '  graph [bgcolor="transparent", rankdir=LR, pad=0.2, nodesep=0.35, ranksep=0.6];',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, '
        'fontcolor="white", color="#c4b5fd", penwidth=0.8];',
        f'  edge [color="{EDGE_COLOR}", arrowsize=0.6];',
    ]
    for node in file_graph.get("nodes", []):
        color = CYCLE_COLOR if node.get("in_cycle") else NODE_COLOR
        label = node["id"].split("/")[-1]
        lines.append(f'  {_dot_id(node["id"])} [label={_dot_id(label)}, fillcolor="{color}", tooltip={_dot_id(node["id"])}];')
    for edge in file_graph.get("edges", []):
        style = f'color="{CYCLE_COLOR}", penwidth=2' if edge.get("in_cycle") else ""
        lines.append(f"  {_dot_id(edge['source'])} -> {_dot_id(edge['target'])} [{style}];")
    lines.append("}")
    return "\n".join(lines)


def render_metrics(graph: dict[str, Any], audit: dict[str, Any]) -> None:
    """Top-line numbers."""
    stats = graph.get("stats", {})
    cycles = len(graph.get("circular_dependencies", []))
    cols = st.columns(5)
    cols[0].metric("Nodes", stats.get("nodes", 0))
    cols[1].metric("Edges", stats.get("edges", 0))
    cols[2].metric("Files", stats.get("files", 0))
    cols[3].metric("Import cycles", cycles)
    score = audit.get("health_score")
    cols[4].metric("Health score", f"{score}/100" if isinstance(score, (int, float)) else "n/a")


def render_topology(graph: dict[str, Any], report_md: str) -> None:
    """Dependency graph, god nodes, cycles and the raw GRAPH_REPORT.md."""
    left, right = st.columns([3, 2], gap="large")

    with left:
        st.subheader("File dependency graph")
        file_graph = graph.get("file_graph") or {}
        if file_graph.get("nodes"):
            st.graphviz_chart(file_graph_to_dot(file_graph), width="stretch")
            st.caption("Red nodes and edges form an import cycle.")
        else:
            st.info("No cross-file dependencies found.")

    with right:
        st.subheader("God nodes")
        gods = graph.get("god_nodes", [])
        if gods:
            top = max(n["degree"] for n in gods) or 1
            for i, node in enumerate(gods, 1):
                st.markdown(f"**{i}. `{node['label']}`** · {node['degree']} edges")
                st.caption(f"`{node.get('source_file') or ''}`")
                st.progress(node["degree"] / top)
        else:
            st.caption("No god nodes detected.")

        st.subheader("Circular dependency loops")
        cycles = graph.get("circular_dependencies", [])
        if not cycles:
            st.success("No import cycles.")
        for cycle in cycles:
            st.error(" → ".join(cycle["cycle"]))
            for ev in cycle.get("evidence", []):
                st.caption(f"`{ev['location']}` · {ev['from']} *{ev['relation']}* {ev['to']}")

    with st.expander("GRAPH_REPORT.md (Graphify)"):
        st.markdown(report_md or "_No report._")
