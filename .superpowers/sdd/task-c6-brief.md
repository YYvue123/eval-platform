# C Task 6：CLI 与证据

Work from E:\eval-platform. No git commit. Do not print API keys.

Create tools/real_fill/cli.py and __main__.py:

python -m tools.real_fill --base-url URL --db PATH --confirm-fingerprint HEX --only REAL01,REAL04

If --confirm-fingerprint missing or mismatch vs tools.cleanup_mock.fingerprint.target_fingerprint(db): exit 1, write nothing to remote.

Default --only empty means dry-run list of scenarios, no HTTP except optional GET /api/live.

When running scenarios against --base-url, use httpx not TestClient.

## Evidence (required)

Create docs/superpowers/evidence/subproject-c.md covering REAL01–12 with result pass|fail|blocked|not_run, IDs, blocking_reason.

Required isolated evidence: run scenarios via TestClient+isolated_env (can be a small script in the test or unittest that dumps JSON). Do not point unittest at eval_platform.db.

Live activity DB fill (REAL01/02/04/05 only, needs stats_service): only if --confirm-fingerprint matches the intended sqlite file. Prefer an already-running isolated stack (8001/a_ui.db) over eval_platform.db. If live fill is unsafe (wrong db, lock, no server), mark those rows blocked with reason — do not invent pass.

REAL03/06/07/08: blocked if L3_MODEL_API_URL unset in that process; do not print the URL.

Run: unittest tests.test_real_fill tests.test_isolation_guard -v
Report .superpowers/sdd/task-c6-report.md
