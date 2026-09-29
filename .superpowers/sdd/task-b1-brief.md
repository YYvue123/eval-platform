# Task 1：指纹与 canonical hash

Work from E:\eval-platform. Do NOT git commit. Do NOT touch backend/eval_platform.db.

## Context

Subproject B Task 1 of docs/superpowers/plans/2026-09-29-subproject-b-mock-cleanup.md

PYTHONPATH must include repo root for `tools.cleanup_mock`. Tests live in backend/tests and run from backend/.

## Fix vs plan snippet

Do not use `isolated_env.os`. After `from tests import isolated_env`, `import os` and read `os.environ["DATABASE_URL"]`. Call `from tests.isolated_env import assert_isolated_database`.

## Plan text

### Task 1：指纹与 canonical hash

Create:
- tools/cleanup_mock/__init__.py
- tools/cleanup_mock/fingerprint.py
- backend/tests/test_cleanup_mock.py

Functions:
- resolve_sqlite_path(url_or_path: str) -> Path
- file_sha256(path: Path) -> str
- target_fingerprint(path: Path) -> str  # sha256:<hex> of sha256(bytes)+"|"+absolute path
- canonical_json(obj: dict) -> str
- manifest_hash(obj: dict) -> str  # ignore key manifest_hash

TDD. Run from backend:
`.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v`

Report: .superpowers/sdd/task-b1-report.md
