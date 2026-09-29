# C Task 1：填充客户端与 REAL01

Work from E:\eval-platform. No git commit. No writes to backend/eval_platform.db.

Plan: docs/superpowers/plans/2026-09-29-subproject-c-real-fill.md Task 1

Create tools/real_fill/__init__.py, client.py, scenarios.py (real01 only), backend/tests/test_real_fill.py

FillClient(client) wrapping TestClient or httpx:
- login(username, password)
- request(method, path, **kwargs)

real01_accounts(admin_client, viewer_client) -> dict:
- admin login 200
- viewer hits an admin-only or create endpoint expecting 403/401

Use tests.isolated_env and followup_helpers if useful. Do not call paid models.

unittest tests.test_real_fill -v from backend.
Report .superpowers/sdd/task-c1-report.md
