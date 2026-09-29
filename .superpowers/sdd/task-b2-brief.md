# B Task 2：SQLite Backup API

Work from E:\eval-platform. Do NOT git commit. Do NOT write backend/eval_platform.db.

Read plan Task 2 in docs/superpowers/plans/2026-09-29-subproject-b-mock-cleanup.md

Create tools/cleanup_mock/backup_sqlite.py
Produces consistent_backup(src, dest) -> dict path, sha256, source, size
WAL checkpoint FULL then Connection.backup. Windows: if file: URI mode=ro fails, fallback connect(str(src)).

Append BackupTests to backend/tests/test_cleanup_mock.py. Keep Task 1 tests.

Run: cd backend; .venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
Report: .superpowers/sdd/task-b2-report.md
