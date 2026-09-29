# B Task 3：plan 清单（不写库）

Work from E:\eval-platform. Do NOT git commit. Do NOT write eval_platform.db.

Plan Task 3: docs/superpowers/plans/2026-09-29-subproject-b-mock-cleanup.md

Create tools/cleanup_mock/inventory.py
build_plan(db_path) -> dict with target.absolute_path, target.fingerprint, counts_before, actions[{table,pk,action,reason}], notes, manifest_hash.

Delete candidates: eval_results.simulation=1; eval_tasks.simulation=1 plus lineages; agent_runs.provider=mock plus events. Keep trial_run=1 simulation=0 tasks.

Skip missing tables/columns via notes. Plan must not mutate row counts.

Append PlanTests to backend/tests/test_cleanup_mock.py. Keep prior tests.

Run unittest tests.test_cleanup_mock -v
Report .superpowers/sdd/task-b3-report.md
