# 子项目 C 验收证据（真实填充 REAL01–12）

日期：2026-09-29。工作目录：`E:\eval-platform`。未提交。未打印 API Key / `L3_MODEL_API_URL` 值。unittest 未指向 `backend/eval_platform.db`。

## 方法

| 通道 | 做法 | 是否写入活动库 |
| --- | --- | --- |
| 隔离证据（本表主结果） | `TestClient` + `tests.isolated_env`；`dump_isolated_evidence` 写出 `backend/tests/_isolated/real_fill_isolated_evidence.json` | 否（隔离 sqlite，库名不是 `eval_platform.db`） |
| CLI | `python -m tools.real_fill --db PATH --confirm-fingerprint HEX [--base-url URL --only …]`；httpx 打 `--base-url` | 仅当指纹匹配且 `--only` 非空 |
| 活动库 live fill | 优先已运行隔离栈 `127.0.0.1:8001` + `tests/_isolated/a_ui.db` | **未执行**（见下） |

本进程 `L3_MODEL_API_URL`：**未设置**（只记录有无，不写 URL）。

## 活动库 / live（REAL01/02/04/05）

| 探测 | 结果 |
| --- | --- |
| `GET http://127.0.0.1:8001/api/live` | 失败（`URLError`，无监听） |
| `GET http://127.0.0.1:8000/api/live` | 200（判定为既有业务栈，**不**作为填充目标） |
| `backend/tests/_isolated/a_ui.db` | 存在；仅做过 **dry-run**（指纹匹配、`--only` 空、无远程写） |
| `backend/eval_platform.db` | 存在；**未** `--confirm-fingerprint` apply/fill |

对 `a_ui.db` 故意错误指纹 + `--only REAL01 --base-url http://127.0.0.1:8001`：退出码 **1**，stderr `fingerprint missing or mismatch`。

因此 live 的 REAL01/02/04/05 **不得标 pass**。原因：`isolated stack 8001 not running; refused :8000 as likely business DB`。

## REAL01–12（隔离 TestClient，诚实结果）

JSON：`backend/tests/_isolated/real_fill_isolated_evidence.json`（最后一次 `test_isolated_evidence_dump_json`）。

| case_id | result | IDs / 关键字段 | blocking_reason |
| --- | --- | --- | --- |
| REAL01 | pass | `admin_login_status=200`；`viewer_denied_status=403`；`viewer_username=real01-viewer-bd7665d8` | — |
| REAL02 | pass | `dataset_id=13`；`version_id=13`；`data_count=4`；`quality_status=passed` | — |
| REAL03 | blocked | — | missing L3_MODEL_API_URL |
| REAL04 | pass | `parse_resource_id=demo/parse_d935b75a`；`stats_resource_id=demo/stats_d935b75a`；failed cid `real04-6e2d0427c409` | — |
| REAL05 | pass | `mcp_resource_id=demo/mcp_7d8b8dd7`；`success_ok=true`；`empty_args_ok=false` | — |
| REAL06 | blocked | — | missing L3_MODEL_API_URL |
| REAL07 | blocked | — | missing L3_MODEL_API_URL |
| REAL08 | blocked | — | missing L3_MODEL_API_URL |
| REAL09 | pass | `signed=false`；`score_status=200`（未代签） | — |
| REAL10 | blocked | `publish_status=200` | publish_not_rejected:200（空榜仍 2xx，不把发布标合格） |
| REAL11 | blocked | — | 七天窗口未满，seven-day window is not elapsed |
| REAL12 | pass | `backup_status=200`；`backup_sha256=fecbd5009af056ca8a6fcd184d548e532401f66d46f3938aef4877aa9fa76379`；`hash_match=true`；`notification_id=5`；路径在隔离 `BACKUP_DIR` | — |

### live 行（活动库，非隔离 pass）

| case_id | result | blocking_reason |
| --- | --- | --- |
| REAL01 | blocked | isolated stack 8001 not running; refused :8000 as likely business DB |
| REAL02 | blocked | isolated stack 8001 not running; refused :8000 as likely business DB |
| REAL04 | blocked | isolated stack 8001 not running; refused :8000 as likely business DB |
| REAL05 | blocked | isolated stack 8001 not running; refused :8000 as likely business DB |

## 单测

```text
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill tests.test_isolation_guard -v
Ran 28 tests in 16.182s OK
```

未把业务库、密钥、`.env` URL 写入本文件。
