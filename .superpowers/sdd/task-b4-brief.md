# B Task 4：apply 守卫与事务删除

Work from E:\eval-platform. Do NOT git commit. Do NOT write backend/eval_platform.db.

Plan Task 4. Create tools/cleanup_mock/apply.py
apply_plan(db_path, plan, *, confirm_fingerprint, backup_dir) -> dict

Reject ValueError if fingerprint mismatch, manifest_hash mismatch, missing confirm, or eval_tasks.status in running/queued/leased/cancelling (if table/column exist).

On success: consistent_backup first, then delete ONLY plan.actions pks in safe order (events, results, lineages, child tables, tasks, runs). Transaction.

Do not LIKE mock. Keep trial task.

Append ApplyTests as in the plan. verify_clean can be a stub imported later - if verify.py missing, assert via SQL in the test instead of verify_clean.

Keep all prior tests. unittest tests.test_cleanup_mock -v
Report .superpowers/sdd/task-b4-report.md
