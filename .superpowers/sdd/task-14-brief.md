# Task 14：全量回归与浏览器验收

Work from E:\eval-platform. Do NOT git commit. Do NOT `--trailer Co-authored-by`. Do NOT touch `backend/eval_platform.db`.

This is verification + evidence. Modify application code **only** if a regression in Tasks 1–13 is proven by a failing test or a failed browser assertion. Then fix, re-run, and record the fix in the evidence doc.

## Global constraints

- Tests: `from tests import isolated_env`; never the business DB.
- Isolated UI env uses `a_ui.db` under `backend/tests/_isolated/`.
- Product copy: no research slogans.
- Kill only processes you start this round.
- No plaintext secrets in evidence (no tokens in digests/screenshots if avoidable).
- Login for isolated UI: `admin` / `admin123` (dev bootstrap).

## Plan text (authoritative)

See `docs/superpowers/plans/2026-09-29-subproject-a-part3-frontend.md` Task 14 (Steps 1–9) and design table in `docs/superpowers/specs/2026-09-29-review-followup-roadmap-design.md` §4.

Evidence file: **create** `docs/superpowers/evidence/subproject-a.md`.

Screenshots: save under `docs/superpowers/evidence/` (png). Reference them from the markdown.

Cases that must appear in the evidence file: A-REV07a, A-REV07b, A-REV08, A-REV09, A-REV11, A-MCP, A-ISO, A-FULL, A-UI. `not_run`/`blocked` must include a reason.

## Step 1–3: automated suites

Python: `E:\eval-platform\backend\.venv\Scripts\python.exe`

Backend cwd: `E:\eval-platform\backend`

Frontend cwd: `E:\eval-platform\frontend`

Unittest discover can take several minutes. Use a high `block_until_ms` (e.g. 600000). Do not mark fail as pass.

Record: test counts, duration, absence of `database is locked`.

Frontend: `npm run test:unit` then `collect-permissions` then `verify:ux-static` then `build`. Permission codes: only existing `resource:*` (view/create/invoke). Count was 55 after Task 13.

## Step 4: isolated UI processes

Before start, check whether 8765 / 8000 / 5173 are already listening. If occupied by **this** isolated stack, reuse; if unknown/business DB, do not reuse — pick free ports or stop only processes you started.

Set these on the **backend** process (PowerShell):

```
$env:DATABASE_URL="sqlite+aiosqlite:///E:/eval-platform/backend/tests/_isolated/a_ui.db"
$env:UPLOAD_DIR="E:/eval-platform/backend/tests/_isolated/a_ui_uploads"
$env:LOG_DIR="E:/eval-platform/backend/tests/_isolated/a_ui_logs"
$env:BACKUP_DIR="E:/eval-platform/backend/tests/_isolated/a_ui_backups"
$env:MCP_STDIO_ALLOWLIST='{"stats-local":["E:\\eval-platform\\backend\\.venv\\Scripts\\python.exe","-m","tools.stats_service.stdio_server"]}'
```

Start:

1. Stats: `E:\eval-platform\tools\stats_service\run.ps1` (127.0.0.1:8765). Confirm `GET http://127.0.0.1:8765/health`.
2. Backend: from `backend`, `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` with the env above. Confirm `/api/live`.
3. Frontend: `npm run dev -- --host 127.0.0.1` (Vite 5173, `/api` proxies to 8000).

stdio child cwd/PYTHONPATH is handled by `stdio_transport.py` (repo root on PYTHONPATH).

## Step 5–7: browser (required for A-UI)

Use cursor-ide-browser MCP (`GetDynamicTools` then `CallDynamicTool`). Workflow: navigate → lock → snapshot/click/type → screenshots at 1440 and ~390 → unlock when fully done.

UI: `http://127.0.0.1:5173` → 资源. Wizard is 「添加资源」.

### HTTP tool (parse)

- Kind: Tool
- ns `demo`, slug unique (e.g. `parse_ui`), name any
- Endpoint `http://127.0.0.1:8765/v1/parse`, POST
- Replace default prediction/reference fields with required string `text`
- Allowlist should include 127.0.0.1 (wizard may default; if register fails on egress, set allowlist)
- After register: 试用 `{"text":"100 cm, 2 m"}` — success; history still there after refresh
- Missing `text`: business failure, **not** a green success badge

Save 1440px and 390px screenshots.

### Stats tool + two-step Skill

Register second tool to `http://127.0.0.1:8765/v1/stats` with schema `values` (array) + `target_unit` (string).

Skill: s1 parse with `$input.text`; s2 stats with `s1.output.values` and `$input.target_unit`. Wizard defaults already match:

```
s1: {"text":{"$ref":"$input.text"}}
s2: {"values":{"$ref":"s1.output.values"},"target_unit":{"$ref":"$input.target_unit"}}
```

Trial:

```json
{"text":"100 cm, 2 m, 500 mm","target_unit":"m"}
```

Assert converted ≈ `[1,2,0.5]`, mean vs `3.5/3` error `< 1e-9`. Call history on both tools: `source=skill_step`, same parent correlation.

### MCP Streamable HTTP

Register MCP endpoint `http://127.0.0.1:8765/mcp`. Open MCP workbench:

1. initialize → protocol version + server name on the five-step bar
2. tools/list → two tools (`parse_measurements`, `compute_stats`)
3. form call success
4. empty values call → `MCP_TOOL_ERROR` and lastCall **failed** (not success toast)

### MCP stdio

Register command alias `stats-local` (select only; no free-form command box). List + call parse. Assert success. Screenshot proving no arbitrary command input.

## Mapping automated cases (may cite tests, not only UI)

| Case | Typical evidence |
|---|---|
| A-REV07a | UI Skill + `GET /api/resources/calls/{rid}` showing skill_step / parent_correlation_id; or `tests.test_review_followup_a` |
| A-REV07b | Backend tests (cross-tenant / nested skill). UI optional. |
| A-REV08 | UI missing-input HTTP; MCP empty-args; plus tests for session expired |
| A-REV09 | History pagination / redaction from tests; UI history after invoke |
| A-REV11 | `frontend/tests/unit` SchemaForm tests; optional UI |
| A-MCP | `tests.test_review_followup_a` SSE / Last-Event-ID / allowlist; UI HTTP+stdio probe/call |
| A-ISO | `tests.test_isolation_guard` output |
| A-FULL | unittest discover counts + no `database is locked` |
| A-UI | Browser IDs, screenshots 1440/390 |

## Step 8–9

Fill real values in evidence (HEAD, `git status --short`, env, IDs, assertions, screenshot paths).

Run `git status --short` and `git diff --check`. Do not add `__pycache__`, business DB, logs, or secrets to git. Do not commit.

Write `.superpowers/sdd/task-14-report.md` with commands, counts, screenshot paths, and any BLOCKED items.

## Browser MCP

Namespace `cursor-ide-browser`. Discover schema first. Order: `browser_navigate` → `browser_lock` lock → interactions → unlock only when all browser work is finished.

If browser MCP cannot complete a step, mark that UI case `blocked` with the exact error; still complete automated evidence.

## Self-review

Status DONE / DONE_WITH_CONCERNS / BLOCKED. List files. Paste suite summaries. No commit.
