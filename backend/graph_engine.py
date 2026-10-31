"""Graphify-powered dependency graph engine for GemmaGraph Bug Hunter.

Pipeline:
  1. Resolve the target (clone a public git URL into a cache dir, or use a local path).
  2. Run Graphify (AST extraction + clustering) to produce graphify-out/graph.json
     and graphify-out/GRAPH_REPORT.md.
  3. Parse graph.json to find god nodes, file-level import cycles, dense clusters,
     and dead / isolated code.
  4. Read the source of the most critical files around the god nodes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# /tmp/gemmagraph_repos on Linux (Cloudways); the OS temp dir elsewhere.
REPO_CACHE_ROOT = Path(tempfile.gettempdir()) / "gemmagraph_repos"
GRAPHIFY_TIMEOUT_S = 300
MAX_SNIPPET_CHARS = 12_000
MAX_SNIPPET_LINES = 120  # keeps the Gemma prompt small for fast audits
MAX_REPORT_CHARS = 20_000

# Edges that describe structure (file contains function) rather than real usage.
STRUCTURAL_RELATIONS = {"contains", "defines", "method", "rationale_for", "_python_import_marker"}
# Edges that create a dependency from the source file onto the target file.
DEPENDENCY_RELATIONS = {
    "imports", "imports_from", "calls", "indirect_call", "uses", "references",
    "references_constant", "instantiates", "extends", "depends_on", "includes",
    "re_exports", "uses_component", "uses_static_prop", "crate_depends_on",
}
# Names that are legitimately never referenced from inside the repo.
ENTRYPOINT_PATTERNS = re.compile(
    r"^(main|__init__|__main__|__call__|__enter__|__exit__|__repr__|__str__|setup|teardown|"
    r"test_.*|.*_test|handler|lambda_handler|app|create_app|run|cli)$",
    re.IGNORECASE,
)

# In-memory cache keyed by (resolved target, commit/mtime fingerprint).
_ANALYSIS_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()


class GraphEngineError(RuntimeError):
    """Raised when cloning or graph extraction fails."""


# --------------------------------------------------------------------------- #
# Target validation / cloning  (security boundary: all user input passes here)
# --------------------------------------------------------------------------- #

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLONE_TIMEOUT_S = 30
MAX_TARGET_LEN = 200

# The web API may only scan these local folders (aliases -> canonical key).
_LOCAL_ALIASES: dict[str, str] = {
    ".": ".", "./": ".",
    "demo_buggy_app": "demo_buggy_app", "./demo_buggy_app": "demo_buggy_app",
    "demo_buggy_app/": "demo_buggy_app", "./demo_buggy_app/": "demo_buggy_app",
}

# https://github.com/<owner>/<repo>[.git][/] - nothing else (no query, fragment,
# credentials, whitespace or shell metacharacters). Owner rules follow GitHub's.
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"(?P<repo>[A-Za-z0-9._-]{1,100}?)(?:\.git)?/?$"
)

_CLONE_LOCK = threading.Lock()


class InvalidTargetError(GraphEngineError):
    """Raised when a scan target fails validation (maps to HTTP 400)."""


@dataclass(frozen=True)
class ScanTarget:
    """A validated scan target.

    Attributes:
        kind: ``"local"`` or ``"github"``.
        key: Portable cache key (``"."``, ``"demo_buggy_app"`` or the canonical
            GitHub URL), identical on every machine the app is deployed to.
        path: Local directory to scan (``None`` for GitHub targets until cloned).
        url: Canonical clone URL for GitHub targets.
    """

    kind: str
    key: str
    path: Path | None = None
    url: str | None = None


def validate_target(value: str | None, allow_any_local_path: bool = False) -> ScanTarget:
    """Validate untrusted input and turn it into a :class:`ScanTarget`.

    The web API calls this with ``allow_any_local_path=False``: only ``"."``,
    ``"demo_buggy_app"`` and public ``https://github.com/<owner>/<repo>`` URLs are
    accepted, which rules out path traversal and argument/command injection.
    The local CLI (a trusted user on their own machine) may pass ``True``.

    Raises:
        InvalidTargetError: if the value is not an allowed target.
    """
    raw = (value if value is not None else ".").strip() or "."
    if len(raw) > MAX_TARGET_LEN or any(ch.isspace() or ord(ch) < 32 for ch in raw):
        raise InvalidTargetError("Invalid target: whitespace/control characters or too long.")

    if raw in _LOCAL_ALIASES:
        key = _LOCAL_ALIASES[raw]
        return ScanTarget(kind="local", key=key, path=(PROJECT_ROOT / key).resolve())

    match = GITHUB_URL_RE.match(raw)
    if match:
        owner, repo = match["owner"], match["repo"]
        if repo in {".", ".."}:
            raise InvalidTargetError("Invalid GitHub repository name.")
        canonical = f"https://github.com/{owner}/{repo}".lower()
        return ScanTarget(kind="github", key=canonical, url=f"{canonical}.git")

    if allow_any_local_path and not raw.startswith("-"):
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            return ScanTarget(kind="local", key=path.as_posix(), path=path)
        raise InvalidTargetError(f"Local path not found or not a directory: {path}")

    raise InvalidTargetError(
        "Unsupported target. Use '.', 'demo_buggy_app', or https://github.com/<owner>/<repo>."
    )


def _git_head(path: Path) -> str | None:
    """Return the HEAD commit SHA of a git checkout, or ``None``."""
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15, shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def _clone_repo(target: ScanTarget) -> Path:
    """Shallow-clone a validated GitHub target, reusing an existing clone on disk.

    Uses a list argv with ``shell=False`` and ``--`` so the URL can never be read
    as a git option, plus a hard 30 s timeout.
    """
    assert target.kind == "github" and target.url
    match = GITHUB_URL_RE.match(target.key)
    assert match is not None  # key was produced by validate_target
    dest = REPO_CACHE_ROOT / f"{match['owner']}__{match['repo']}"

    with _CLONE_LOCK:
        if (dest / ".git").exists():
            return dest  # disk cache hit: repeated scans skip the network entirely
        REPO_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "echo"}
        try:
            subprocess.run(
                ["git", "clone", "--depth=1", "--single-branch", "--no-tags",
                 "--", target.url, str(dest)],
                check=True, capture_output=True, text=True,
                timeout=CLONE_TIMEOUT_S, shell=False, env=env,
            )
        except subprocess.CalledProcessError as exc:
            shutil.rmtree(dest, ignore_errors=True)
            detail = (exc.stderr or "").strip().splitlines()[-1:] or ["unknown error"]
            raise GraphEngineError(f"git clone failed: {detail[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            shutil.rmtree(dest, ignore_errors=True)
            raise GraphEngineError(f"git clone timed out after {CLONE_TIMEOUT_S}s") from exc
    return dest


def resolve_target(target: ScanTarget) -> Path:
    """Return the local directory for a validated target, cloning if needed."""
    if target.kind == "github":
        return _clone_repo(target)
    assert target.path is not None
    if not target.path.is_dir():
        raise GraphEngineError(f"Scan directory is missing: {target.key}")
    return target.path


# --------------------------------------------------------------------------- #
# Graphify invocation
# --------------------------------------------------------------------------- #

def _graphify_cmd() -> list[str]:
    """Locate the Graphify CLI (console script, else ``python -m graphify``)."""
    exe = shutil.which("graphify")
    return [exe] if exe else [sys.executable, "-m", "graphify"]


def run_graphify(target_dir: Path) -> Path:
    """Run Graphify on target_dir and return the graphify-out directory.

    `graphify <dir> --no-viz` builds graph.json via local AST extraction;
    `graphify cluster-only` then writes GRAPH_REPORT.md (the extract step alone
    does not). `--code-only` keeps the scan local and deterministic (no LLM pass
    over docs), and `--no-label` skips LLM community naming.
    """
    cmd = _graphify_cmd()
    out_dir = target_dir / "graphify-out"
    try:
        subprocess.run(
            [*cmd, str(target_dir), "--no-viz", "--code-only"],
            check=True, capture_output=True, text=True, timeout=GRAPHIFY_TIMEOUT_S,
            cwd=str(target_dir), shell=False,
        )
        subprocess.run(
            [*cmd, "cluster-only", str(target_dir), "--no-viz", "--no-label"],
            check=True, capture_output=True, text=True, timeout=GRAPHIFY_TIMEOUT_S,
            cwd=str(target_dir), shell=False,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()[-1500:]
        raise GraphEngineError(f"graphify failed (exit {exc.returncode}): {detail}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GraphEngineError("graphify timed out") from exc

    if not (out_dir / "graph.json").exists():
        raise GraphEngineError(f"graphify did not produce {out_dir / 'graph.json'}")
    return out_dir


# --------------------------------------------------------------------------- #
# Graph analysis
# --------------------------------------------------------------------------- #

def _strongly_connected_components(adj: dict[str, set[str]]) -> list[list[str]]:
    """Iterative Tarjan's SCC (safe for large graphs; no recursion limit)."""
    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    result: list[list[str]] = []
    counter = 0

    nodes = set(adj) | {t for ts in adj.values() for t in ts}
    for root in nodes:
        if root in index_of:
            continue
        work = [(root, iter(sorted(adj.get(root, ()))))]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index_of:
                    index_of[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(sorted(adj.get(nxt, ())))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index_of[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index_of[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                result.append(comp)
    return result


def _find_cycle_path(component: list[str], adj: dict[str, set[str]]) -> list[str]:
    """Return one concrete cycle (a -> b -> ... -> a) inside an SCC via BFS."""
    members = set(component)
    start = sorted(component)[0]
    parent: dict[str, str | None] = {start: None}
    queue = [start]
    while queue:
        node = queue.pop(0)
        for nxt in sorted(adj.get(node, ())):
            if nxt not in members:
                continue
            if nxt == start:
                path = [node]
                while parent[path[-1]] is not None:
                    path.append(parent[path[-1]])  # type: ignore[arg-type]
                path.reverse()
                return path + [start]
            if nxt not in parent:
                parent[nxt] = node
                queue.append(nxt)
    return sorted(component) + [start]


def summarize_graph(graph: dict[str, Any], top_n_god_nodes: int = 5) -> dict[str, Any]:
    """Turn a Graphify ``graph.json`` into review findings.

    Computes god nodes (highest degree), file-level circular dependencies (Tarjan
    SCCs over EXTRACTED/INFERRED dependency edges), dense Graphify communities,
    dead code (isolated nodes and never-referenced callables), the most critical
    files, and a compact file-level graph for the dashboard.
    """
    nodes: list[dict[str, Any]] = graph.get("nodes", [])
    edges: list[dict[str, Any]] = graph.get("links") or graph.get("edges") or []
    node_by_id = {n["id"]: n for n in nodes if "id" in n}

    degree: dict[str, int] = defaultdict(int)
    in_usage: dict[str, int] = defaultdict(int)  # non-structural incoming edges
    file_adj: dict[str, set[str]] = defaultdict(set)
    file_edge_evidence: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    confidence_counts: dict[str, int] = defaultdict(int)
    relation_counts: dict[str, int] = defaultdict(int)

    for e in edges:
        src, tgt = e.get("source"), e.get("target")
        if src not in node_by_id or tgt not in node_by_id:
            continue
        rel = e.get("relation", "unknown")
        conf = e.get("confidence", "UNKNOWN")
        relation_counts[rel] += 1
        confidence_counts[conf] += 1
        degree[src] += 1
        degree[tgt] += 1
        if rel not in STRUCTURAL_RELATIONS:
            in_usage[tgt] += 1

        # File-level dependency graph from EXTRACTED + INFERRED edges.
        if rel in DEPENDENCY_RELATIONS and conf in ("EXTRACTED", "INFERRED"):
            sf = node_by_id[src].get("source_file")
            tf = node_by_id[tgt].get("source_file")
            if sf and tf and sf != tf:
                file_adj[sf].add(tf)
                if len(file_edge_evidence[(sf, tf)]) < 3:
                    file_edge_evidence[(sf, tf)].append({
                        "from": node_by_id[src].get("label", src),
                        "to": node_by_id[tgt].get("label", tgt),
                        "relation": rel,
                        "confidence": conf,
                        "location": f"{sf}:{e.get('source_location', '')}".rstrip(":"),
                    })

    def node_view(nid: str) -> dict[str, Any]:
        """Compact, JSON-friendly view of one node."""
        n = node_by_id[nid]
        return {
            "id": nid,
            "label": n.get("label", nid),
            "source_file": n.get("source_file"),
            "source_location": n.get("source_location"),
            "community": n.get("community"),
            "degree": degree.get(nid, 0),
        }

    # a) God nodes ------------------------------------------------------------
    ranked = sorted(node_by_id, key=lambda nid: degree.get(nid, 0), reverse=True)
    god_nodes = [node_view(nid) for nid in ranked[:top_n_god_nodes] if degree.get(nid, 0) > 0]

    # b) Circular dependencies (file-level SCCs) ------------------------------
    circular = []
    for comp in _strongly_connected_components(file_adj):
        if len(comp) < 2:
            continue
        cycle = _find_cycle_path(comp, file_adj)
        evidence = []
        for a, b in zip(cycle, cycle[1:]):
            evidence.extend(file_edge_evidence.get((a, b), [])[:1])
        circular.append({"files": sorted(comp), "cycle": cycle, "size": len(comp), "evidence": evidence})
    circular.sort(key=lambda c: c["size"], reverse=True)

    # b) Dense clusters (Graphify communities with high internal density) ---
    community_members: dict[Any, list[str]] = defaultdict(list)
    for nid, n in node_by_id.items():
        if n.get("community") is not None:
            community_members[n["community"]].append(nid)
    internal_edges: dict[Any, int] = defaultdict(int)
    for e in edges:
        s, t = node_by_id.get(e.get("source")), node_by_id.get(e.get("target"))
        if s and t and s.get("community") is not None and s.get("community") == t.get("community"):
            if e.get("relation") not in STRUCTURAL_RELATIONS:
                internal_edges[s["community"]] += 1
    dense_clusters = []
    for cid, members in community_members.items():
        size = len(members)
        if size < 4:
            continue
        density = internal_edges[cid] / (size * (size - 1))
        if density >= 0.15:
            files = sorted({node_by_id[m].get("source_file") for m in members if node_by_id[m].get("source_file")})
            dense_clusters.append({
                "community": cid,
                "name": node_by_id[members[0]].get("community_name", f"Community {cid}"),
                "size": size,
                "internal_edges": internal_edges[cid],
                "density": round(density, 3),
                "files": files[:15],
            })
    dense_clusters.sort(key=lambda c: (c["density"], c["size"]), reverse=True)

    # c) Dead / isolated code -------------------------------------------------
    isolated, unreferenced = [], []
    for nid, n in node_by_id.items():
        if degree.get(nid, 0) == 0:
            isolated.append(node_view(nid))
            continue
        if n.get("_callable") and in_usage.get(nid, 0) == 0:
            bare = re.sub(r"\(.*\)$", "", str(n.get("label", ""))).split(".")[-1]
            if not ENTRYPOINT_PATTERNS.match(bare) and not bare.startswith("__"):
                unreferenced.append(node_view(nid))

    # Critical files: files hosting god nodes, weighted by total degree.
    file_score: dict[str, int] = defaultdict(int)
    for g in god_nodes:
        if g["source_file"]:
            file_score[g["source_file"]] += g["degree"]
    for nid in ranked[:top_n_god_nodes]:
        for e in edges:
            other = e.get("target") if e.get("source") == nid else e.get("source") if e.get("target") == nid else None
            if other in node_by_id and node_by_id[other].get("source_file"):
                file_score[node_by_id[other]["source_file"]] += 1
    critical_files = [f for f, _ in sorted(file_score.items(), key=lambda kv: kv[1], reverse=True)]

    # File-level dependency graph for the dashboard's node-link visual (top files only).
    file_degree: dict[str, int] = defaultdict(int)
    for (a, b) in file_edge_evidence:
        file_degree[a] += 1
        file_degree[b] += 1
    scc_of = {f: i for i, c in enumerate(circular) for f in c["files"]}
    top_files = set(sorted(file_degree, key=file_degree.get, reverse=True)[:40]) | set(scc_of)
    file_graph = {
        "nodes": [
            {"id": f, "degree": file_degree[f], "in_cycle": f in scc_of}
            for f in sorted(top_files)
        ],
        "edges": [
            {"source": a, "target": b, "in_cycle": a in scc_of and scc_of.get(a) == scc_of.get(b)}
            for a in sorted(top_files) for b in sorted(file_adj.get(a, ())) if b in top_files
        ],
    }

    return {
        "stats": {
            "nodes": len(node_by_id),
            "edges": len(edges),
            "files": len({n.get("source_file") for n in nodes if n.get("source_file")}),
            "communities": len(community_members),
            "confidence": dict(confidence_counts),
            "relations": dict(sorted(relation_counts.items(), key=lambda kv: kv[1], reverse=True)),
        },
        "god_nodes": god_nodes,
        "circular_dependencies": circular[:20],
        "dense_clusters": dense_clusters[:10],
        "dead_code": {
            "isolated_nodes": isolated[:50],
            "unreferenced_callables": unreferenced[:50],
            "isolated_count": len(isolated),
            "unreferenced_count": len(unreferenced),
        },
        "critical_files": critical_files[:10],
        "file_graph": file_graph,
    }


def read_critical_files(root: Path, files: list[str], limit: int = 3) -> dict[str, str]:
    """Read the top ``limit`` source files, line-numbered so the model can cite lines.

    Paths are resolved and must stay inside ``root`` (symlinks in hostile repos
    cannot escape the checkout).
    """
    snippets: dict[str, str] = {}
    root_resolved = root.resolve()
    for rel in files:
        if len(snippets) >= limit:
            break
        path = (root / rel).resolve()
        if not path.is_relative_to(root_resolved) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lines = text.splitlines()
        numbered = "\n".join(f"{i:>5}| {line}" for i, line in enumerate(lines[:MAX_SNIPPET_LINES], 1))
        if len(lines) > MAX_SNIPPET_LINES:
            numbered += f"\n... [truncated: {len(lines) - MAX_SNIPPET_LINES} more lines]"
        if len(numbered) > MAX_SNIPPET_CHARS:
            numbered = numbered[:MAX_SNIPPET_CHARS] + "\n... [truncated]"
        snippets[rel.replace("\\", "/")] = numbered
    return snippets


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

SKIP_DIRS = {"graphify-out", ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}


def _fingerprint(target_dir: Path) -> str:
    """Cheap change-detection key for the in-process analysis cache."""
    # Cloned repos are pinned to a commit; HEAD is a precise cache key.
    if target_dir.is_relative_to(REPO_CACHE_ROOT):
        head = _git_head(target_dir)
        if head:
            return head
    # Local working trees can have uncommitted edits: key on newest mtime.
    newest = 0.0
    for p in target_dir.rglob("*"):
        if SKIP_DIRS.intersection(p.relative_to(target_dir).parts):
            continue
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass
    return f"mtime:{newest:.0f}"


def analyze_repo_graph(target: ScanTarget | str, use_cache: bool = True) -> dict[str, Any]:
    """Run the full Graphify pipeline for one target.

    Args:
        target: A :class:`ScanTarget`, or a raw string which is validated with the
            strict web-API rules (``"."``, ``"demo_buggy_app"`` or a GitHub URL).
        use_cache: Reuse an in-process result when the source is unchanged.

    Returns:
        ``{"repo", "graph_summary", "report_md", "code_snippets", "cached"}``.

    Raises:
        InvalidTargetError: the target failed validation.
        GraphEngineError: cloning or Graphify failed.
    """
    if not isinstance(target, ScanTarget):
        target = validate_target(target)
    target_dir = resolve_target(target)
    cache_key = f"{target.key}@{_fingerprint(target_dir)}"

    if use_cache:
        with _CACHE_LOCK:
            hit = _ANALYSIS_CACHE.get(cache_key)
        if hit:
            return {**hit, "cached": True}

    out_dir = run_graphify(target_dir)
    graph = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    report_path = out_dir / "GRAPH_REPORT.md"
    report_md = report_path.read_text(encoding="utf-8", errors="replace") if report_path.exists() else ""
    if len(report_md) > MAX_REPORT_CHARS:
        report_md = report_md[:MAX_REPORT_CHARS] + "\n... [truncated]"

    summary = summarize_graph(graph)
    result: dict[str, Any] = {
        "repo": target.key,
        "graph_summary": summary,
        "report_md": report_md,
        "code_snippets": read_critical_files(target_dir, summary["critical_files"]),
        "cached": False,
    }
    with _CACHE_LOCK:
        _ANALYSIS_CACHE[cache_key] = result
    return result
