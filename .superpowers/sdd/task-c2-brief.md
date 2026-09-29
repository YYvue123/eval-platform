# C Task 2：REAL02 数据集

Work from E:\eval-platform. No commit. No eval_platform.db.

Add real02_dataset(client) in tools/real_fill/scenarios.py: create dataset with 4 AI-generated items, description must say 「AI 生成确定性题集」. Import via existing datasets API. Return dataset_id, version_id.

Look at backend/app/api/datasets.py for actual endpoints (create, import, quality). Don't invent fields.

Tests in test_real_fill.py on isolated TestClient. unittest tests.test_real_fill -v
Report .superpowers/sdd/task-c2-report.md
