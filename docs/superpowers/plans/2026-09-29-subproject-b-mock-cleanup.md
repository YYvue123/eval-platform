# 子项目 B：D4 Mock 清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供 plan/apply/verify 清理 CLI，用 SQLite Backup API 做一致性备份，按结构化标志清除 Mock 衍生链，并停止 seed 回灌 pack 数据集。

**Architecture:** `tools/cleanup_mock` 只操作解析后的 SQLite 文件。测试在 `backend/tests/_isolated/` 种植 simulation 行后跑全流程。活动库 apply 必须指纹确认。

**Tech Stack:** Python 3 stdlib sqlite3、json、hashlib、argparse；unittest；现有 SQLAlchemy 模型仅用于对照列名，CLI 用 sqlite3 以免测试引擎锁。

## Global Constraints

- 测试 `from tests import isolated_env`；绝不指向 `backend/eval_platform.db`。
- 后端命令在 `E:\eval-platform\backend`，解释器 `.venv\Scripts\python.exe`。
- 禁止 `DELETE ... LIKE '%mock%'`。
- `trial_run=1 AND simulation=0` 保留。
- 不打印密码或完整带凭证的连接串。
- 不创建 git commit。
- 产品页文案不在本子项目范围（D 处理），但 CLI 帮助用中文操作说明。

## 文件结构

| 路径 | 动作 | 职责 |
|---|---|---|
| `tools/cleanup_mock/__init__.py` | 新 | 包 |
| `tools/cleanup_mock/fingerprint.py` | 新 | 路径解析、指纹、canonical hash |
| `tools/cleanup_mock/backup_sqlite.py` | 新 | WAL checkpoint + Connection.backup |
| `tools/cleanup_mock/inventory.py` | 新 | 分类与 plan JSON |
| `tools/cleanup_mock/apply.py` | 新 | 守卫 + 事务删除 |
| `tools/cleanup_mock/verify.py` | 新 | integrity / 标志计数 |
| `tools/cleanup_mock/cli.py` | 新 | argparse |
| `tools/cleanup_mock/__main__.py` | 新 | `python -m tools.cleanup_mock` |
| `backend/app/database.py` | 改 | seed 不再灌 packs / 示例知识 |
| `backend/tests/test_cleanup_mock.py` | 新 | DATA01/DATA02 |
| `docs/superpowers/evidence/subproject-b.md` | 新 | 证据 |

工作目录跑 CLI：仓库根，`PYTHONPATH` 含仓库根。测试从 `backend` 跑 unittest，把仓库根加入 sys.path（测试文件开头）。

---

### Task 1：指纹与 canonical hash

**Files:**
- Create: `tools/cleanup_mock/__init__.py`
- Create: `tools/cleanup_mock/fingerprint.py`
- Create: `backend/tests/test_cleanup_mock.py`

**Interfaces:**
- Produces: `resolve_sqlite_path(url_or_path: str) -> Path`；`file_sha256(path: Path) -> str`；`target_fingerprint(path: Path) -> str` 形如 `sha256:<64hex>`；`canonical_json(obj: dict) -> str`；`manifest_hash(obj: dict) -> str`（忽略键 `manifest_hash`）。

- [ ] **Step 1：写失败测试**

在 `backend/tests/test_cleanup_mock.py`：

```python
from tests import isolated_env  # noqa: F401

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.cleanup_mock.fingerprint import (
    canonical_json,
    file_sha256,
    manifest_hash,
    resolve_sqlite_path,
    target_fingerprint,
)


class FingerprintTests(unittest.TestCase):
    def test_resolve_rejects_business_eval_platform_name_in_tests(self):
        from tests.isolated_env import assert_isolated_database
        url = isolated_env.os.environ["DATABASE_URL"]
        assert_isolated_database(url)

    def test_fingerprint_changes_when_bytes_change(self):
        d = Path(tempfile.mkdtemp())
        p = d / "t.db"
        p.write_bytes(b"abc")
        a = target_fingerprint(p)
        p.write_bytes(b"abcd")
        b = target_fingerprint(p)
        self.assertTrue(a.startswith("sha256:"))
        self.assertNotEqual(a, b)

    def test_manifest_hash_ignores_own_field(self):
        body = {"actions": [{"pk": 1}], "manifest_hash": "x"}
        h1 = manifest_hash(body)
        h2 = manifest_hash({"actions": [{"pk": 1}]})
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, "x")
```

- [ ] **Step 2：跑测试确认失败**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

Expected: FAIL import or missing functions.

- [ ] **Step 3：实现 fingerprint.py**

```python
from __future__ import annotations
import hashlib, json, os
from pathlib import Path


def resolve_sqlite_path(url_or_path: str) -> Path:
    raw = url_or_path.strip()
    if "sqlite" in raw and "///" in raw:
        raw = raw.split("///", 1)[-1]
    path = Path(raw)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    return path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def target_fingerprint(path: Path) -> str:
    resolved = path.resolve()
    inner = file_sha256(resolved) + "|" + str(resolved)
    return "sha256:" + hashlib.sha256(inner.encode("utf-8")).hexdigest()


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def manifest_hash(obj: dict) -> str:
    copy = {k: v for k, v in obj.items() if k != "manifest_hash"}
    return hashlib.sha256(canonical_json(copy).encode("utf-8")).hexdigest()
```

空 `__init__.py`。

- [ ] **Step 4：测试通过**

Expected: PASS FingerprintTests。

- [ ] **Step 5：记录文件清单，不 commit**

---

### Task 2：SQLite Backup API

**Files:**
- Create: `tools/cleanup_mock/backup_sqlite.py`
- Modify: `backend/tests/test_cleanup_mock.py`

**Interfaces:**
- Consumes: `resolve_sqlite_path`, `file_sha256`
- Produces: `consistent_backup(src: Path, dest: Path) -> dict` 键 `path, sha256, source, size`；内部 `PRAGMA wal_checkpoint(FULL)` 后 `src.backup(dest_conn)`。

- [ ] **Step 1：失败测试**

```python
class BackupTests(unittest.TestCase):
    def test_backup_hash_matches_restore_copy(self):
        import sqlite3
        from tools.cleanup_mock.backup_sqlite import consistent_backup
        d = Path(tempfile.mkdtemp())
        src = d / "src.db"
        dest = d / "dst.db"
        conn = sqlite3.connect(src)
        conn.execute("CREATE TABLE t(id INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        info = consistent_backup(src, dest)
        self.assertTrue(dest.exists())
        self.assertEqual(info["sha256"], file_sha256(dest))
        c = sqlite3.connect(dest)
        n = c.execute("SELECT COUNT(*) FROM t").fetchone()[0]
        c.close()
        self.assertEqual(n, 1)
```

- [ ] **Step 2：跑测试失败**

- [ ] **Step 3：实现**

```python
from __future__ import annotations
import sqlite3
from pathlib import Path
from tools.cleanup_mock.fingerprint import file_sha256


def consistent_backup(src: Path, dest: Path) -> dict:
    src = src.resolve()
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    src_conn = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    try:
        src_conn.execute("PRAGMA wal_checkpoint(FULL)")
    except sqlite3.OperationalError:
        pass
    dst_conn = sqlite3.connect(dest)
    try:
        src_conn.backup(dst_conn)
        dst_conn.commit()
    finally:
        dst_conn.close()
        src_conn.close()
    return {
        "path": str(dest),
        "source": str(src),
        "size": dest.stat().st_size,
        "sha256": file_sha256(dest),
    }
```

只读 URI 在 Windows 上若失败，回退 `sqlite3.connect(str(src))` 再 checkpoint + backup，测试仍须通过。

- [ ] **Step 4：测试通过**

- [ ] **Step 5：记录文件，不 commit**

---

### Task 3：plan 清单（不写库）

**Files:**
- Create: `tools/cleanup_mock/inventory.py`
- Modify: `backend/tests/test_cleanup_mock.py`

**Interfaces:**
- Produces: `build_plan(db_path: Path) -> dict`，含 `target.absolute_path`、`target.fingerprint`、`counts_before`、`actions`（每项 `table, pk, action, reason`）、`manifest_hash`。
- `action` 仅为 `delete`（simulation 结果/任务/mock run 及子表）。
- 检测列是否存在再用；缺列跳过并在 `notes` 记录。

种植函数（测试内）：创建最小表 `eval_tasks(id, status, simulation, trial_run)`、`eval_results(id, task_id, simulation)`、`eval_lineages(id, task_id)`、`agent_runs(id, provider, session_id)`、`agent_events(id, run_id)`。

- [ ] **Step 1：失败测试**

```python
class PlanTests(unittest.TestCase):
    def test_plan_does_not_write(self):
        import sqlite3, os
        from tools.cleanup_mock.inventory import build_plan
        d = Path(tempfile.mkdtemp())
        db = d / "p.db"
        c = sqlite3.connect(db)
        c.executescript("""
        CREATE TABLE eval_tasks (id INTEGER PRIMARY KEY, status TEXT, simulation INTEGER, trial_run INTEGER);
        CREATE TABLE eval_results (id INTEGER PRIMARY KEY, task_id INTEGER, simulation INTEGER);
        CREATE TABLE eval_lineages (id INTEGER PRIMARY KEY, task_id INTEGER);
        CREATE TABLE agent_runs (id INTEGER PRIMARY KEY, provider TEXT, session_id INTEGER);
        CREATE TABLE agent_events (id INTEGER PRIMARY KEY, run_id INTEGER);
        INSERT INTO eval_tasks VALUES (1,'success',1,0);
        INSERT INTO eval_tasks VALUES (2,'success',0,1);
        INSERT INTO eval_results VALUES (10,1,1);
        INSERT INTO eval_results VALUES (11,2,0);
        INSERT INTO eval_lineages VALUES (3,1);
        INSERT INTO agent_runs VALUES (5,'mock',1);
        INSERT INTO agent_events VALUES (6,5);
        """)
        c.commit(); c.close()
        before = db.stat().st_mtime
        plan = build_plan(db)
        after = sqlite3.connect(db)
        n = after.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0]
        after.close()
        self.assertEqual(n, 2)
        tables = {a["table"] for a in plan["actions"]}
        self.assertIn("eval_results", tables)
        self.assertIn("eval_tasks", tables)
        self.assertIn("agent_runs", tables)
        pks_tasks = {a["pk"] for a in plan["actions"] if a["table"]=="eval_tasks"}
        self.assertIn(1, pks_tasks)
        self.assertNotIn(2, pks_tasks)
        self.assertTrue(plan["manifest_hash"])
```

- [ ] **Step 2：跑红**

- [ ] **Step 3：实现 inventory.py**

查询：
- results where simulation=1 → delete
- tasks where simulation=1 → delete + lineages/events/subtasks/report_jobs if tables exist
- agent_runs where provider='mock' → delete events/messages if exist

`build_plan` 末尾写入 `manifest_hash`。

- [ ] **Step 4：测试通过**

- [ ] **Step 5：不 commit**

---

### Task 4：apply 守卫与事务删除

**Files:**
- Create: `tools/cleanup_mock/apply.py`
- Modify: `backend/tests/test_cleanup_mock.py`

**Interfaces:**
- Produces: `apply_plan(db_path, plan, *, confirm_fingerprint: str, backup_dir: Path) -> dict`
- 拒绝：fingerprint 不匹配、`manifest_hash` 重算不匹配、任务 status in running/queued/leased/cancelling、未传 confirm。
- 成功：先 `consistent_backup`，再按 table 依赖删除（events → results/lineages → tasks → runs）。

- [ ] **Step 1：失败测试**

```python
class ApplyTests(unittest.TestCase):
    def _seed(self):
        # 与 PlanTests 相同 schema，返回 db path
        ...

    def test_apply_rejects_wrong_hash(self):
        from tools.cleanup_mock.inventory import build_plan
        from tools.cleanup_mock.apply import apply_plan
        db = self._seed()
        plan = build_plan(db)
        plan["manifest_hash"] = "deadbeef"
        with self.assertRaises(ValueError) as ctx:
            apply_plan(db, plan, confirm_fingerprint=plan["target"]["fingerprint"], backup_dir=db.parent / "b")
        self.assertIn("manifest", str(ctx.exception).lower())
        c = __import__("sqlite3").connect(db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_results").fetchone()[0], 2)

    def test_apply_deletes_simulation_keeps_trial(self):
        from tools.cleanup_mock.inventory import build_plan
        from tools.cleanup_mock.apply import apply_plan
        from tools.cleanup_mock.verify import verify_clean
        db = self._seed()
        plan = build_plan(db)
        apply_plan(db, plan, confirm_fingerprint=plan["target"]["fingerprint"], backup_dir=db.parent / "b")
        c = __import__("sqlite3").connect(db)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_tasks WHERE id=2").fetchone()[0], 1)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_tasks WHERE id=1").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eval_results WHERE simulation=1").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM agent_runs WHERE provider='mock'").fetchone()[0], 0)
```

- [ ] **Step 2：红**

- [ ] **Step 3：实现 apply.py**

删除顺序建议：`agent_events`、`eval_results`（simulation 或 task 在删集）、`eval_lineages`、`task_events`、`task_subtasks`、`report_jobs`、`eval_tasks`、`agent_runs`。仅删除 plan.actions 列出的 pk。

- [ ] **Step 4：绿**

- [ ] **Step 5：不 commit**

---

### Task 5：verify

**Files:**
- Create: `tools/cleanup_mock/verify.py`
- Modify: `backend/tests/test_cleanup_mock.py`

**Interfaces:**
- Produces: `verify_clean(db_path: Path) -> dict` 含 `ok: bool`、`integrity`、`foreign_key`、`simulation_results`、`simulation_tasks`、`mock_runs`。

- [ ] **Step 1–4：** 对 apply 后的库 `ok is True`；对未清理库 `ok is False`。实现 `PRAGMA integrity_check` 与 `PRAGMA foreign_key_check`。

- [ ] **Step 5：不 commit**

---

### Task 6：停止 seed 回灌

**Files:**
- Modify: `backend/app/database.py` `seed_db` / `seed_knowledge`
- Modify: `backend/tests/test_cleanup_mock.py`

**Interfaces:**
- `seed_db` 不再调用 `seed_eval_packs`。
- `seed_knowledge` 不再插入「任务失败不自动恢复」「内置裁判画像」两条；保留按模板的 ref 条目。

- [ ] **Step 1：测试**

```python
class SeedTests(unittest.TestCase):
    def test_seed_db_does_not_insert_pack_datasets(self):
        from tests import isolated_env  # already
        import asyncio
        from sqlalchemy import select, func
        from app.database import seed_db, async_session, init_db
        from app.models import Dataset
        async def run():
            await init_db()
            await seed_db()
            async with async_session() as db:
                n = await db.scalar(select(func.count()).select_from(Dataset).where(Dataset.name.like("pack:%")))
                return n or 0
        self.assertEqual(asyncio.run(run()), 0)
```

若 `init_db`+`seed_db` 过重，改为直接读 `seed_db` 源码断言不再调用 `seed_eval_packs` **不够**。必须跑行为测试。隔离库已由 isolated_env 指向 `_isolated`。

- [ ] **Step 2–4：** 改 `database.py`，测试通过。确认其它 unittest 仍绿：跑 `tests.test_eval_flow tests.test_cleanup_mock`。若有测试依赖 packs，改为显式 `await seed_eval_packs(db)`。

- [ ] **Step 5：不 commit**

---

### Task 7：CLI

**Files:**
- Create: `tools/cleanup_mock/cli.py`
- Create: `tools/cleanup_mock/__main__.py`
- Modify: `backend/tests/test_cleanup_mock.py`

**Interfaces:**
- `python -m tools.cleanup_mock plan --db PATH --out plan.json`
- `python -m tools.cleanup_mock apply --db PATH --manifest plan.json --confirm-fingerprint HEX --backup-dir DIR`
- `python -m tools.cleanup_mock verify --db PATH`
- `python -m tools.cleanup_mock backup --db PATH --out FILE`

cwd 仓库根，`PYTHONPATH` 为仓库根。CLI 拒绝打印 `DATABASE_URL` 全文；只打印绝对路径（sqlite 无密码）。

- [ ] **Step 1：** subprocess 测 `plan` 后文件 mtime/行数不变；`apply` 无 confirm 退出码非 0。

- [ ] **Step 2–4：** 实现 argparse。

- [ ] **Step 5：不 commit**

---

### Task 8：隔离全流程证据

**Files:**
- Create: `docs/superpowers/evidence/subproject-b.md`
- Modify: `backend/tests/test_cleanup_mock.py` 如需

**Steps:**
- 将 `backend/eval_platform.db` **复制**到 `backend/tests/_isolated/b_cleanup_src.db`（仅复制，不打开业务库写入）。若业务库不存在，用 Task 4 种植库代替并在证据写 blocked 原因。
- 对该拷贝 `backup` → `plan` → `apply` → `verify`。
- 证据写指纹、删除计数、backup sha256、verify ok。
- 跑：

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_cleanup_mock -v
```

Expected: PASS。再跑 `tests.test_isolation_guard` 确认仍拒绝业务库。

- 不 commit。不在本任务对活动 `eval_platform.db` 执行 apply，除非证据中单独一节「活动库」且用户已在对话中要求完成 B（本计划允许 CLI 具备能力；Task 8 默认只清理拷贝）。**对活动库执行 apply 放到证据可选节：若用户本会话要求完成 B 的退出门禁「活动库标志清零」，则在备份成功后对活动库 apply，并写入证据。** 本任务实施者：先完成拷贝闭环；若 `eval_platform.db` 存在且无 running 任务，再对活动库 plan+backup+apply+verify，失败则回滚为恢复 backup 文件覆盖（仅当 apply 中途失败）。成功则记录前后计数。

实施者注意：活动库 apply 前 `PRAGMA` 查 running；有则 **不要 apply**，证据 `blocked: active tasks`。
