# C Task 5：REAL08–12

Work from E:\eval-platform. No git commit. No eval_platform.db. Do not print secrets. Do not forge expert signatures or backdate shadow windows.

Read existing APIs in backend/app/api before inventing paths.

Add in tools/real_fill/scenarios.py:

real08_prompts(client, *, dataset_id) -> dict
- If L3_MODEL_API_URL empty: blocked missing L3_MODEL_API_URL (no login).
- Else create two prompt versions on same dataset if POST /api/prompts exists. Do not claim a winner.

real09_safety(client) -> dict
- If a safety trial/run endpoint exists, call it once.
- Never POST expert approve/sign. If only expert-sign exists, blocked with reason expert_sign_not_automated.

real10_leaderboard(client) -> dict
- Attempt publish/release without a qualifying formal result; expect 4xx. That 4xx is pass for this scenario (honest rejection).
- If no publish endpoint, blocked endpoint_missing.

real11_shadow(client) -> dict
- Always blocked with blocking_reason that seven-day window is not elapsed; do not forge timestamps. result=blocked.

real12_ops(client) -> dict
- POST /api/ops/backup then restore-drill against isolated BACKUP_DIR. Record paths/hashes from JSON (no secrets).
- Notifications: if POST exists for a real event, record id; else omit.

Tests isolated:
- real08 without L3 -> blocked
- real09 does not call any path containing sign/approve/expert if you can assert via a recording client OR simply document and test that real09_safety return never has signed=True
- real10: 4xx publish is result pass
- real11: result blocked and reason mentions 七天 or seven
- real12: backup 200 on TestClient (ops backup copies isolated sqlite)

Keep prior tests. unittest tests.test_real_fill -v
Report .superpowers/sdd/task-c5-report.md
