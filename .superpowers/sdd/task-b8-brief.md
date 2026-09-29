# B Task 8：隔离全流程证据

Work from E:\eval-platform. No git commit.

## Required (must)

1. Copy `backend/eval_platform.db` IF it exists to `backend/tests/_isolated/b_cleanup_src.db` using file copy (not opening it for write via app). If missing, use the Task 4 planted schema instead and write blocked reason for live copy.
2. On the COPY only: backup, plan, apply with confirm-fingerprint, verify. Record counts, hashes in docs/superpowers/evidence/subproject-b.md
3. Run `cd backend; .venv\Scripts\python.exe -m unittest tests.test_cleanup_mock tests.test_isolation_guard -v`

## Live activity DB (try, honest)

4. `plan` against `backend/eval_platform.db` (read-only). Do not print secrets.
5. If plan shows 0 simulation/mock actions, record pass without apply.
6. If actions exist AND no busy task statuses, `backup` then `apply` then `verify` on the live file. If sqlite is locked, busy tasks, or verify fails: do not loop; restore from the backup you just made if apply started and failed; mark live apply blocked with reason.
7. Never LIKE '%mock%'. Never point unittest at business db.

Report .superpowers/sdd/task-b8-report.md
Evidence docs/superpowers/evidence/subproject-b.md
