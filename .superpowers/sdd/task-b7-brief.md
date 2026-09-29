# B Task 7：CLI

Work from E:\eval-platform. No git commit. No eval_platform.db writes.

Create tools/cleanup_mock/cli.py and __main__.py so:
python -m tools.cleanup_mock plan --db PATH --out plan.json
python -m tools.cleanup_mock apply --db PATH --manifest plan.json --confirm-fingerprint HEX --backup-dir DIR
python -m tools.cleanup_mock verify --db PATH
python -m tools.cleanup_mock backup --db PATH --out FILE

Must be run with cwd repo root (or PYTHONPATH=repo root). Do not print DATABASE_URL. Print resolved absolute path only.

apply without --confirm-fingerprint exits non-zero.

Append CliTests using subprocess + tempfile fixture from ApplyTests schema. Keep prior tests.

unittest tests.test_cleanup_mock -v from backend.
Report .superpowers/sdd/task-b7-report.md
