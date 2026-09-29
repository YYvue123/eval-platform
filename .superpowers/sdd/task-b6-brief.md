# B Task 6：停止 seed 回灌

Work from E:\eval-platform. No git commit. No eval_platform.db writes.

Modify backend/app/database.py:
- seed_db MUST NOT call seed_eval_packs
- seed_knowledge MUST NOT insert the two sample entries titled 任务失败不自动恢复 and 内置裁判画像; keep template ref_type entries

Keep seed_eval_packs function in eval_packs.py for explicit calls.

Add SeedTests in test_cleanup_mock.py: after init_db+seed_db on isolated URL, count Dataset.name like pack:% == 0.

If other tests break because they expected packs, update those tests to call seed_eval_packs explicitly. Run:
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock tests.test_eval_flow tests.test_isolation_guard -v

Report .superpowers/sdd/task-b6-report.md
