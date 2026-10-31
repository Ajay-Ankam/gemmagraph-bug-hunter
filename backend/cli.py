"""Command-line interface for GemmaGraph Bug Hunter.

Examples (from the repository root):
    python backend/cli.py demo_buggy_app
    python backend/cli.py path/to/any/local/project --graph-only
    python backend/cli.py https://github.com/owner/repo --json > report.json
    python backend/cli.py . --patch-out fix.patch

Unlike the web API, the CLI may scan any local directory: the person running
it is already trusted with that filesystem. Remote targets are still limited
to https://github.com/<owner>/<repo>.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover
    pass

from graph_engine import GraphEngineError, analyze_repo_graph, validate_target  # noqa: E402


def _render_markdown(graph: dict[str, Any], audit: dict[str, Any] | None) -> str:
    """Human/agent-readable report of the graph findings and the Gemma audit."""
    g = graph["graph_summary"]
    st = g["stats"]
    out = [
        f"# GemmaGraph Bug Hunter report: `{graph['repo']}`",
        "",
        f"**Graph:** {st['nodes']} nodes · {st['edges']} edges · {st['files']} files · "
        f"{st['communities']} communities",
        "",
        "## God nodes (most connected)",
        *[f"- `{n['label']}` ({n['degree']} edges) - {n['source_file']}" for n in g["god_nodes"]],
        "",
        "## Circular dependencies (Graphify, file level)",
        *([f"- {' -> '.join(c['cycle'])}" for c in g["circular_dependencies"]] or ["- none"]),
        "",
        "## Dead-code candidates (graph)",
        *([f"- `{n['label']}` - {n['source_file']}:{n['source_location']}"
           for n in g["dead_code"]["unreferenced_callables"][:15]] or ["- none"]),
    ]
    if audit is None:
        return "\n".join(out)
    if "error" in audit:
        return "\n".join(out + ["", f"## Gemma 4 audit\n\n**Error:** {audit['error']}"])
    out += ["", "## Gemma 4 audit", "", audit.get("summary", ""), ""]
    if isinstance(audit.get("health_score"), (int, float)):
        out.append(f"**Health score:** {audit['health_score']}/100\n")
    out.append("### Security hotspots")
    out += [
        f"- **{str(h.get('severity', '?')).upper()}** `{h.get('file')}:{h.get('line')}` - "
        f"{h.get('category', '')}: {h.get('explanation', '')}"
        for h in audit.get("security_hotspots", [])
    ] or ["- none"]
    out += ["", "### Prioritized fixes"]
    out += [f"{f.get('rank')}. {f.get('title')} (`{f.get('file')}`)" for f in audit.get("prioritized_fixes", [])] or ["- none"]
    if audit.get("git_diff_patch"):
        out += ["", "### Patch for fix #1", "", "```diff", audit["git_diff_patch"].rstrip(), "```"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the pipeline and print the report. Returns an exit code."""
    parser = argparse.ArgumentParser(prog="gemmagraph", description=__doc__.split("\n")[0])
    parser.add_argument("target", nargs="?", default=".", help="local path or https://github.com/<owner>/<repo>")
    parser.add_argument("--graph-only", action="store_true", help="skip the Gemma 4 audit (no API key needed)")
    parser.add_argument("--json", action="store_true", help="emit raw JSON instead of Markdown")
    parser.add_argument("--patch-out", metavar="FILE", help="write Gemma's git_diff_patch to FILE")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles default to cp1252
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        target = validate_target(args.target, allow_any_local_path=True)
        graph = analyze_repo_graph(target, use_cache=False)
    except GraphEngineError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    audit: dict[str, Any] | None = None
    if not args.graph_only:
        import gemma_agent  # imported lazily so --graph-only works without google-genai configured

        try:
            audit = gemma_agent.audit_code_graph(graph["graph_summary"], graph["report_md"], graph["code_snippets"])
        except Exception as exc:  # report but keep the graph results
            audit = {"error": f"{type(exc).__name__}: {exc}"}

    if args.patch_out and audit and audit.get("git_diff_patch"):
        Path(args.patch_out).write_text(audit["git_diff_patch"].rstrip("\n") + "\n", encoding="utf-8", newline="\n")
        print(f"patch written to {args.patch_out}", file=sys.stderr)

    if args.json:
        payload = {k: v for k, v in graph.items() if k != "code_snippets"}
        print(json.dumps({**payload, "audit": audit}, indent=2, default=str))
    else:
        print(_render_markdown(graph, audit))
    return 1 if audit and audit.get("security_hotspots") else 0


if __name__ == "__main__":
    raise SystemExit(main())
