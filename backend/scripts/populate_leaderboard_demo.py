"""Provision real, explicitly labelled customer-demo runs through gated platform APIs.

Defaults to a dedicated development DB; --target staging appends via the existing API.
Never seeds task status or score facts directly; staging is backed up and checked for preservation.
Run from backend: .venv/Scripts/python scripts/populate_leaderboard_demo.py
"""
from __future__ import annotations

import json
import asyncio
import argparse
import logging
import os
import sys
import sqlite3
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--target', choices=['demo', 'staging'], default='demo')
parser.add_argument('--api-url', default='http://127.0.0.1:8000')
args = parser.parse_args() if __name__ == '__main__' else parser.parse_args([])
if args.target == 'demo':
    os.environ["APP_ENV"] = "dev"
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + (ROOT / "leaderboard_demo.db").as_posix()
    os.environ["UPLOAD_DIR"] = str(ROOT / "uploads/leaderboard-demo")
    os.environ["LOG_DIR"] = str(ROOT / "logs/leaderboard-demo")
    os.environ["AGENT_WORKER_ENABLED"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"

from fastapi.testclient import TestClient
from app.config import settings
from app.main import app
from app.database import async_session
from app.services.task_service import recover_expired_leases

PREFIX = "客户演示20261024"
SAMPLES = [
    ("知识问答", "法国首都是哪个城市？只输出中文城市名。", "巴黎"),
    ("知识问答", "化学元素金的元素符号是什么？只输出符号。", "Au"),
    ("数学推理", "计算 17 乘以 23，只输出十进制整数。", "391"),
    ("数学推理", "袋中3个红球2个蓝球，随机取一球为红色的概率是多少？只输出最简分数。", "3/5"),
    ("指令遵循", "只输出大写英文单词 READY，不要标点和解释。", "READY"),
    ("指令遵循", "将英文单词 leaderboard 的字母顺序反转，只输出结果。", "draobredael"),
    ("代码理解", "Python 表达式 sum(range(1, 6)) 的值是多少？只输出数字。", "15"),
    ("代码理解", "Python 表达式 len(set([1, 2, 2, 3])) 的值是多少？只输出数字。", "3"),
]
EXPRESSION_SAMPLES = [
    ("知识表达", "用一句话解释水沸腾的条件。", "水的饱和蒸气压达到外界压强时会沸腾。"),
    ("知识表达", "用一句话解释月亮为什么发光。", "月亮反射太阳光，因此看起来会发光。"),
    ("推理说明", "解释为什么连续三个整数的和一定能被3整除，用一句话回答。", "设三个数是n、n加1、n加2，它们的和为3n加3，所以能被3整除。"),
    ("推理说明", "说明为什么两个奇数的和是偶数，用一句话回答。", "两个奇数分别可写为2a加1和2b加1，相加等于2乘以a加b加1，因此是偶数。"),
    ("文本摘要", "概括这段话：城市新增三条公交线，覆盖五个社区，预计下月开通。", "城市下月将开通覆盖五个社区的三条新公交线。"),
    ("文本摘要", "概括这段话：图书馆周末延长开放两小时，并新增线上预约座位服务。", "图书馆周末延长开放时间并支持线上预约座位。"),
    ("代码说明", "用一句话解释 Python 的集合为什么能用于列表去重。", "集合只保存互不重复的元素，因此可用于去除列表中的重复值。"),
    ("代码说明", "用一句话解释 Python 中浅拷贝和深拷贝的区别。", "浅拷贝保留嵌套对象的引用，深拷贝递归复制嵌套对象。"),
]


def main():
    if not all([settings.L3_MODEL_API_URL, settings.L3_MODEL_API_KEY, settings.L3_MODEL_PRIMARY]):
        raise SystemExit("Missing configured L3 model; no mock fallback.")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    before, backup_path, target_path = {}, None, ROOT / "leaderboard_demo.db"
    if args.target == 'staging':
        from sqlalchemy.engine import make_url
        if settings.APP_ENV != 'staging' or not settings.DATABASE_URL.startswith('sqlite'):
            raise SystemExit('Staging provisioning requires the configured staging SQLite database.')
        target_path = Path(make_url(settings.DATABASE_URL).database).resolve()
        if not target_path.exists() or target_path == ROOT / 'leaderboard_demo.db':
            raise SystemExit('Existing staging database required; refusing ambiguous target.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        backup_path = ROOT / 'backups' / f'before-leaderboard-staging-{stamp}.db'
        backup_path.parent.mkdir(exist_ok=True)
        with sqlite3.connect(target_path.as_uri() + '?mode=ro', uri=True) as source, sqlite3.connect(backup_path) as dest:
            source.backup(dest)
        with sqlite3.connect(backup_path) as saved:
            for name, in saved.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                quoted = '"' + name.replace('"', '""') + '"'
                columns = [r[1] for r in sorted(saved.execute(f'PRAGMA table_info({quoted})'), key=lambda r:r[5]) if r[5]]
                if columns:
                    selector = ','.join('"' + c.replace('"', '""') + '"' for c in columns)
                    before[name] = {'keys': set(saved.execute(f'SELECT {selector} FROM {quoted}')), 'selector': selector}
            original_core = {t: {r[0]: hashlib.sha256(repr(r).encode()).hexdigest() for r in saved.execute(f'SELECT * FROM {t}')} for t in ['datasets','dataset_versions','dataset_items','eval_tasks','eval_results']}
        print(json.dumps({'phase':'backup_ready','backup':str(backup_path),'before':{t:len(before[t]['keys']) for t in ['eval_models','datasets','eval_tasks','eval_results']}}),flush=True)
    import httpx
    context = httpx.Client(base_url=args.api_url, timeout=120) if args.target == 'staging' else TestClient(app)
    with context as client:
        def call(method, path, **kwargs):
            response = client.request(method, "/api" + path, **kwargs)
            if response.status_code != 200:
                # Never log request bodies containing model credentials.
                raise RuntimeError(f"{method} {path}: HTTP {response.status_code}")
            return response.json()

        login = call("POST", "/auth/login", json={"username": "admin", "password": os.environ.get('DEMO_ADMIN_PASSWORD') or 'admin123'})
        client.headers["Authorization"] = "Bearer " + login["access_token"]
        async def recover():
            async with async_session() as db:
                await recover_expired_leases(db)
                await db.commit()
        if args.target == 'demo':
            asyncio.run(recover())
        models = call("GET", "/models", params={"page_size": 200})["items"]
        if args.target == 'staging':
            # Prove the HTTP service is attached to the backed-up DB before any resource writes.
            with sqlite3.connect(backup_path) as saved:
                expected = {r[0]:r[1] for r in saved.execute("SELECT id,name FROM eval_models WHERE status!='deleted' AND tenant_id=(SELECT tenant_id FROM users WHERE username='admin')")}
            if {m['id']:m['name'] for m in models} != expected:
                raise RuntimeError('API model inventory does not match the staging backup; no resources written.')
        mids, created_models = [], set()
        for label, temp in [("稳健", 0), ("均衡", .4), ("探索", .9)]:
            name = f"[演示配置] {label}"
            existing = next((m for m in models if m["name"] == name), None)
            if existing:
                mids.append(existing["id"])
                continue
            template = json.dumps({"model": settings.L3_MODEL_PRIMARY,
                "messages": [{"role": "user", "content": "{{prompt}}"}], "temperature": temp, "max_tokens": 512})
            model = call("POST", "/models", json={"name": name, "api_url": settings.L3_MODEL_API_URL,
                "api_key": settings.L3_MODEL_API_KEY, "served_model_name": settings.L3_MODEL_PRIMARY,
                "channel_type": settings.L3_MODEL_CHANNEL, "status": "online", "timeout": 90, "retry_count": 0,
                "request_template": template, "company_name": "同源模型 · 真实调用演示", "source_type": "",
                "description": f"客户演示接入别名；底层模型 {settings.L3_MODEL_PRIMARY}，temperature={temp}。不代表独立厂商模型。"})
            mids.append(model["id"])
            created_models.add(model['id'])

        datasets = call("GET", "/datasets", params={"page_size": 200})["items"]
        # Demonstration pricing inputs, not a claim about the provider's tariff.
        # Third alias deliberately has no price, exercising the missing-cost presentation.
        for mid in [mid for mid in mids[:2] if mid in created_models]:
            call("PUT", f"/leaderboard/costs/{mid}", json={"token_price_per_1k": .002, "latency_price_per_sec": 0, "gpu_hour_price": 0})
        def dataset(name, samples):
            existing = next((d for d in datasets if d["name"] == name), None)
            if existing:
                return existing["id"]
            d = call("POST", "/datasets", json={"name": name, "description": "人工编写的小样本演示题；不等同于公共基准。维度来自题目标签。"})
            payload = [{"input": prompt, "reference": answer, "data_label": dim} for dim, prompt, answer in samples]
            call("POST", f"/datasets/{d['id']}/import", files={"file": ("demo.json", json.dumps(payload, ensure_ascii=False).encode(), "application/json")})
            call("POST", "/quality/run", params={"dataset_id": d["id"]})
            call("POST", f"/datasets/{d['id']}/publish")
            return d["id"]

        full = dataset(PREFIX + " · 四维能力", SAMPLES)
        subset = dataset(PREFIX + " · 双维覆盖", SAMPLES[:4])
        expression = dataset(PREFIX + " · 文本相似度示例（非能力认证）", EXPRESSION_SAMPLES)
        tasks = call("GET", "/tasks", params={"page_size": 200})["items"]
        plans = [(mid, full, "builtin/exact_match", round_no) for round_no in (1, 2) for mid in mids]
        plans += [(mids[0], full, "builtin/fuzzy", 1), (mids[1], subset, "builtin/exact_match", 1)]
        plans += [(mid, expression, "builtin/fuzzy", round_no) for round_no in (1, 2) for mid in mids]
        evidence = []
        for index, (mid, dsid, judge, run) in enumerate(plans):
            name = f"{PREFIX}-{mid}-{dsid}-{judge.split('/')[-1]}-R{run}"
            t = next((t for t in tasks if t["name"] == name), None)
            if not t:
                t = call("POST", "/tasks", json={"name": name, "model_id": mid, "dataset_id": dsid,
                    "judge_resource_id": judge, "scene": "qa", "industry": "general", "token_quota": 12000})
            if t["status"] == "draft":
                call("POST", f"/tasks/{t['id']}/submit")
                call("POST", f"/tasks/{t['id']}/audit", json={"approved": True, "comment": "用户授权的开发演示真实评测"})
            if t["status"] not in {'success', 'running'}:
                call("POST", f"/tasks/{t['id']}/run")
            actual = call("GET", f"/tasks/{t['id']}")
            deadline = time.monotonic() + 600
            while actual['status'] in {'queued','running','pending_review'} and time.monotonic() < deadline:
                time.sleep(1)
                actual = call('GET', f"/tasks/{t['id']}")
            evidence.append({k: actual.get(k) for k in ["id", "name", "status", "avg_score", "tokens_used", "simulation"]})
            print(json.dumps({"completed": index + 1, "planned": len(plans), "task_id": t["id"], "status": actual["status"]}), flush=True)
        measured = call("GET", "/leaderboard/insights")
        output = ROOT.parent / f"docs/delivery/leaderboard-{args.target}-evidence.json"
        preservation = {}
        if args.target == 'staging':
            with sqlite3.connect(target_path.as_uri() + '?mode=ro', uri=True) as current:
                for table, entry in before.items():
                    quoted = '"' + table.replace('"','""') + '"'
                    after = set(current.execute(f"SELECT {entry['selector']} FROM {quoted}"))
                    if not entry['keys'].issubset(after):
                        raise RuntimeError(f'Original records missing in {table}; inspect backup, do not auto-restore.')
                    preservation[table] = {'before':len(entry['keys']),'after':len(after),'original_ids_preserved':True}
                for table, hashes in original_core.items():
                    after = {r[0]:hashlib.sha256(repr(r).encode()).hexdigest() for r in current.execute(f'SELECT * FROM {table}')}
                    if any(after.get(key) != digest for key,digest in hashes.items()):
                        raise RuntimeError(f'Original business rows changed in {table}.')
                    preservation[table]['original_content_unchanged'] = True
        output.write_text(json.dumps({"database": str(target_path), "backup":str(backup_path) if backup_path else None,
            "preservation":preservation, "real_provider_calls": True,
            "alias_notice": "All aliases use the same configured underlying model.", "tasks": evidence,
            "overview": measured["overview"], "cohorts": measured["cohorts"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"evidence": str(output), "overview": measured["overview"]}), flush=True)
        if not all(t["status"] == "success" and not t["simulation"] for t in evidence):
            raise SystemExit("Some real evaluations did not complete; inspect tasks, do not claim pass.")


if __name__ == "__main__":
    main()
