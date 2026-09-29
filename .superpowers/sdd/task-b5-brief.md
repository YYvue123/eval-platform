# B Task 5：verify

Work from E:\eval-platform. No git commit. No eval_platform.db writes.

Create tools/cleanup_mock/verify.py
verify_clean(db_path) -> dict with ok, integrity, foreign_key, simulation_results, simulation_tasks, mock_runs.

PRAGMA integrity_check and foreign_key_check. Counts 0 for simulation flags and provider=mock if columns exist.

Append VerifyTests: dirty fixture ok False; after apply_plan ok True.

Keep prior tests. unittest tests.test_cleanup_mock -v
Report .superpowers/sdd/task-b5-report.md
