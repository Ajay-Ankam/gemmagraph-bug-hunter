# Graph Report - gemmagraph-bug-hunter  (2026-10-31)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 192 nodes · 337 edges · 11 communities (8 shown, 3 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 11 edges (avg confidence: 0.91)
- Token cost: 0 input · 0 output

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

## God Nodes (most connected - your core abstractions)
1. `scan()` - 15 edges
2. `analyze_repo_graph()` - 15 edges
3. `GraphEngineError` - 11 edges
4. `validate_target()` - 11 edges
5. `InvalidTargetError` - 9 edges
6. `health()` - 9 edges
7. `summarize_graph()` - 9 edges
8. `main()` - 9 edges
9. `ScanTarget` - 8 edges
10. `multimodal_audit()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `test_unexpected_errors_return_clean_json()` --indirect_call--> `main()`  [INFERRED]
  tests/test_api.py → backend/cli.py
- `test_validate_target_accepts_only_allowlist()` --uses--> `InvalidTargetError`  [INFERRED]
  tests/test_api.py → backend/graph_engine.py
- `test_validate_target_accepts_only_allowlist()` --calls--> `validate_target()`  [INFERRED]
  tests/test_api.py → backend/graph_engine.py
- `test_summarize_graph_finds_cycle_god_node_and_dead_code()` --calls--> `summarize_graph()`  [INFERRED]
  tests/test_api.py → backend/graph_engine.py
- `main()` --uses--> `GraphEngineError`  [INFERRED]
  backend/cli.py → backend/graph_engine.py

## Import Cycles
- 2-file cycle: `demo_buggy_app/auth.py -> demo_buggy_app/db.py -> demo_buggy_app/auth.py`

## Communities (11 total, 3 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (13): analyze_repo_graph(), _clone_repo(), _find_cycle_path(), _fingerprint(), _git_head(), GraphEngineError, _graphify_cmd(), read_critical_files() (+5 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (9): _get_cached(), get_scan(), _graphify_status(), health(), index(), _load_cache(), multimodal_audit(), _store() (+1 more)

### Community 2 - "Community 2"
Cohesion: 0.09
Nodes (3): demo_scan(), test_malicious_scan_targets_are_rejected(), test_unexpected_errors_return_clean_json()

### Community 3 - "Community 3"
Cohesion: 0.16
Nodes (6): audit_architecture_diagram(), audit_code_graph(), _compact_summary(), _extract_json(), _generate(), get_client()

### Community 4 - "Community 4"
Cohesion: 0.21
Nodes (5): _error(), http_exception_handler(), invalid_target_handler(), unhandled_exception_handler(), validation_exception_handler()

### Community 5 - "Community 5"
Cohesion: 0.23
Nodes (8): _scan_id(), admin_backup(), hash_password(), login(), backup_database(), create_user(), find_user(), get_connection()

### Community 6 - "Community 6"
Cohesion: 0.18
Nodes (6): InvalidTargetError, ScanTarget, validate_target(), scan(), ScanRequest, test_validate_target_accepts_only_allowlist()

### Community 9 - "Community 9"
Cohesion: 0.83
Nodes (3): fail(), log(), deploy_cloudways.sh script

## Knowledge Gaps
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `analyze_repo_graph()` connect `Community 0` to `Community 1`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `scan()` (e.g. with `GraphEngineError` and `InvalidTargetError`) actually correct?**
  _`scan()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.08097165991902834 - nodes in this community are weakly interconnected._
- **Why does `scan()` connect `Community 6` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 5`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `GraphEngineError` (e.g. with `main()` and `scan()`) actually correct?**
  _`GraphEngineError` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07823613086770982 - nodes in this community are weakly interconnected._
- **Why does `validate_target()` connect `Community 6` to `Community 0`, `Community 1`, `Community 7`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._