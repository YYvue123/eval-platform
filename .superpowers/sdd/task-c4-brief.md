# C Task 4：REAL03/06/07 模型、Agent、正式评测

Work from E:\eval-platform. No git commit. No eval_platform.db writes. Do not print API keys or L3_MODEL_API_URL values.

Read actual APIs:
- POST /api/models, POST /api/models/{id}/health, POST /api/models/{id}/invoke
- POST /api/agents/sessions, POST /api/agents/sessions/{sid}/confirm, POST /api/agents/sessions/{sid}/runs
- POST /api/tasks (trial_run allowed for small sample)

Add to tools/real_fill/scenarios.py:

```
def _l3_url_present() -> bool:
    import os
    return bool((os.getenv("L3_MODEL_API_URL") or "").strip())

def real03_models(client) -> dict:
    if not _l3_url_present():
        return {"result": "blocked", "scenario": "REAL03", "blocking_reason": "missing L3_MODEL_API_URL"}
    # register/use model with credential_ref not raw key; health once
    # NEVER mark pass if model has empty api_url
    # Do not put api_url or key into the returned dict

def real06_agent(client, *, parse_resource_id: str | None = None) -> dict:
    if not _l3_url_present():
        return {"result": "blocked", "scenario": "REAL06", "blocking_reason": "missing L3_MODEL_API_URL"}
    # create session whose objective mentions using the HTTP parse tool
    # do not claim pass without a real tool loop

def real07_formal_task(client, *, dataset_id, version_id, model_id) -> dict:
    if not _l3_url_present():
        return {"result": "blocked", "scenario": "REAL07", "blocking_reason": "missing L3_MODEL_API_URL"}
    # small sample; no INSERT of scores
```

Tests (isolated TestClient):
- With L3_MODEL_API_URL deleted/empty: all three return result==blocked and blocking_reason contains missing L3_MODEL_API_URL. Do not start stats_service or call paid APIs.
- Optional: creating a model with empty api_url then health/invoke must not be treated as pass (assert blocked or HTTP error). Do not call real L3 from unit tests.

Keep REAL01–05 tests. unittest tests.test_real_fill -v
Report .superpowers/sdd/task-c4-report.md
