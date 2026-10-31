# Graph Report - gemmagraph-bug-hunter  (2026-10-31)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 311 nodes · 609 edges · 13 communities (9 shown, 4 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 15 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c13d86a4`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5
- Community 6
- Community 7
- Community 8
- Community 9
- Community 10
- Community 11

## God Nodes (most connected - your core abstractions)
1. `$` - 24 edges
2. `esc()` - 16 edges
3. `analyze_repo_graph()` - 15 edges
4. `ApiClient` - 12 edges
5. `scan()` - 12 edges
6. `validate_target()` - 11 edges
7. `ApiError` - 10 edges
8. `GraphEngineError` - 10 edges
9. `main()` - 10 edges
10. `drawGraph()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `test_validate_target_accepts_only_allowlist()` --calls--> `validate_target()`  [INFERRED]
  tests/test_api.py → backend/graph_engine.py
- `test_unexpected_errors_return_clean_json()` --indirect_call--> `main()`  [INFERRED]
  tests/test_api.py → streamlit_app/app.py
- `test_file_graph_to_dot_marks_cycles_and_quotes_ids()` --calls--> `file_graph_to_dot()`  [EXTRACTED]
  tests/test_streamlit_app.py → streamlit_app/components/topology.py
- `test_summarize_graph_finds_cycle_god_node_and_dead_code()` --calls--> `summarize_graph()`  [INFERRED]
  tests/test_api.py → backend/graph_engine.py
- `main()` --uses--> `GraphEngineError`  [INFERRED]
  backend/cli.py → backend/graph_engine.py

## Import Cycles
- 2-file cycle: `demo_buggy_app/auth.py -> demo_buggy_app/db.py -> demo_buggy_app/auth.py`

## Communities (13 total, 4 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (17): _error(), _get_cached(), get_scan(), _graphify_status(), health(), http_exception_handler(), index(), invalid_target_handler() (+9 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (14): ApiClient, ApiError, main(), run_scan(), scan_header(), sidebar(), render_audit(), render_hotspot() (+6 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (16): analyze_repo_graph(), _clone_repo(), _find_cycle_path(), _fingerprint(), _git_head(), GraphEngineError, _graphify_cmd(), InvalidTargetError (+8 more)

### Community 3 - "Community 3"
Cohesion: 0.16
Nodes (35): auditDiagram(), getHealth(), request(), scanRepo(), $, badge(), empty(), esc() (+27 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (5): demo_scan(), test_dashboard_assets_are_served_and_cacheable(), test_malicious_scan_targets_are_rejected(), test_summarize_graph_finds_cycle_god_node_and_dead_code(), test_unexpected_errors_return_clean_json()

### Community 5 - "Community 5"
Cohesion: 0.09
Nodes (4): main(), _render_markdown(), fake_backend(), test_file_graph_to_dot_marks_cycles_and_quotes_ids()

### Community 6 - "Community 6"
Cohesion: 0.16
Nodes (6): audit_architecture_diagram(), audit_code_graph(), _compact_summary(), _extract_json(), _generate(), get_client()

### Community 7 - "Community 7"
Cohesion: 0.27
Nodes (7): admin_backup(), hash_password(), login(), backup_database(), create_user(), find_user(), get_connection()

### Community 10 - "Community 10"
Cohesion: 0.83
Nodes (3): fail(), log(), deploy_cloudways.sh script

## Knowledge Gaps
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `analyze_repo_graph()` connect `Community 2` to `Community 0`, `Community 5`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `ApiClient` (e.g. with `run_scan()` and `render_vision()`) actually correct?**
  _`ApiClient` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.05222734254992319 - nodes in this community are weakly interconnected._
- **Why does `CachedStaticFiles` connect `Community 8` to `Community 0`?**
  _High betweenness centrality (0.026) - this node is a cross-community bridge._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07686932215234102 - nodes in this community are weakly interconnected._
- **Should `Community 2` be split into smaller, more focused modules?**
  _Cohesion score 0.07149758454106281 - nodes in this community are weakly interconnected._
- **Should `Community 4` be split into smaller, more focused modules?**
  _Cohesion score 0.07692307692307693 - nodes in this community are weakly interconnected._