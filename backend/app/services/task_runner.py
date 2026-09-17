"""评测任务执行：读取数据分片、调用模型、调用打分工具、回写结果。"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import (
    Dataset,
    DatasetItem,
    DatasetLog,
    DatasetVersion,
    EvalModel,
    EvalResult,
    EvalTask,
    ModelCallLog,
    PromptTemplate,
    PromptVersion,
    ResourceCallLog,
)
from app.services.builtin_tools import run_builtin_tool
from app.services.model_client import invoke_model
from app.services.prompt_render import render_prompt
from app.utils.jsonutil import dumps

log = logging.getLogger(__name__)

DEFAULT_PROMPT = "{{input}}"


async def run_eval_task(task_id: int) -> None:
    async with async_session() as db:
        try:
            await _run(db, task_id)
            await db.commit()
        except Exception:
            await db.rollback()
            task = await db.get(EvalTask, task_id)
            if task:
                task.status = "failed"
                task.error_message = "任务执行异常"
                task.finished_at = datetime.utcnow()
                await db.commit()
            log.exception("eval task %s failed", task_id)


async def _run(db: AsyncSession, task_id: int) -> None:
    task = await db.get(EvalTask, task_id)
    if not task:
        return
    task.status = "running"
    task.started_at = datetime.utcnow()
    task.batch_id = str(uuid.uuid4())
    await db.flush()

    version_id = task.dataset_version_id
    if not version_id:
        ds = await db.get(Dataset, task.dataset_id)
        version_id = ds.current_version_id if ds else None
        task.dataset_version_id = version_id
    if not version_id:
        task.status = "failed"
        task.error_message = "数据集没有可用版本"
        task.finished_at = datetime.utcnow()
        return

    items = (
        await db.execute(
            select(DatasetItem)
            .where(DatasetItem.version_id == version_id, DatasetItem.status == "active")
            .order_by(DatasetItem.item_no)
        )
    ).scalars().all()
    version = await db.get(DatasetVersion, version_id)
    snapshot_src = f"{version_id}:{(version.checksum if version else '')}:{len(items)}"
    task.snapshot_id = hashlib.sha256(snapshot_src.encode()).hexdigest()[:16]
    task.total = len(items)

    model = await db.get(EvalModel, task.model_id)
    if not model:
        task.status = "failed"
        task.error_message = "被测模型不存在"
        task.finished_at = datetime.utcnow()
        return

    template = DEFAULT_PROMPT
    if task.prompt_version_id:
        pv = await db.get(PromptVersion, task.prompt_version_id)
        if pv:
            template = pv.prompt_content or DEFAULT_PROMPT
    elif task.prompt_id:
        pt = await db.get(PromptTemplate, task.prompt_id)
        if pt and pt.current_version_id:
            pv = await db.get(PromptVersion, pt.current_version_id)
            if pv:
                template = pv.prompt_content or DEFAULT_PROMPT

    judge_id = task.judge_resource_id or "builtin/exact_match"
    scores = []
    passed_n = 0
    fail_n = 0
    for idx, item in enumerate(items, start=1):
        values = {
            "input": item.input_content,
            "question": item.input_content,
            "reference": item.reference_answer,
            "answer": item.reference_answer,
            "requirement": item.task_requirement,
        }
        prompt = render_prompt(template, values)
        err = ""
        output = ""
        latency = 0
        tokens = 0
        try:
            invoked = await invoke_model(model, prompt)
            output = invoked["output"]
            latency = invoked["latency_ms"]
            tokens = invoked["tokens"]
            db.add(ModelCallLog(
                model_id=model.id,
                task_id=task.id,
                call_status="success",
                latency_ms=latency,
                token_usage=tokens,
            ))
        except Exception as exc:
            err = str(exc)
            fail_n += 1
            db.add(ModelCallLog(
                model_id=model.id,
                task_id=task.id,
                call_status="failed",
                error_message=err[:2000],
            ))
            db.add(EvalResult(
                task_id=task.id,
                item_id=item.id,
                item_no=item.item_no,
                input_content=item.input_content,
                reference_answer=item.reference_answer,
                error_message=err[:2000],
            ))
            task.progress = int(idx / max(len(items), 1) * 100)
            continue

        try:
            judged = run_builtin_tool(judge_id, {
                "prediction": output,
                "reference": item.reference_answer,
                "pattern": item.expected_output or item.reference_answer,
            })
            db.add(ResourceCallLog(resource_id=judge_id, task_id=task.id, status="success", latency_ms=0))
        except Exception as exc:
            judged = {"score": 0, "passed": False, "metrics": {}}
            err = str(exc)
            db.add(ResourceCallLog(resource_id=judge_id, task_id=task.id, status="failed", error_message=err[:2000]))

        score = float(judged.get("score") or 0)
        passed = bool(judged.get("passed"))
        scores.append(score)
        if passed:
            passed_n += 1
        db.add(EvalResult(
            task_id=task.id,
            item_id=item.id,
            item_no=item.item_no,
            input_content=item.input_content,
            model_output=output,
            reference_answer=item.reference_answer,
            score=score,
            passed=passed,
            metrics_json=dumps(judged.get("metrics") or {}),
            error_message=err,
            latency_ms=latency,
        ))
        task.progress = int(idx / max(len(items), 1) * 100)
        task.success_count = passed_n
        task.fail_count = fail_n
        if idx % 20 == 0:
            await db.flush()

    n = len(items)
    task.success_count = passed_n
    task.fail_count = fail_n
    task.avg_score = round(sum(scores) / len(scores), 4) if scores else 0
    task.pass_rate = round(passed_n / n, 4) if n else 0
    task.progress = 100
    task.status = "success"
    task.finished_at = datetime.utcnow()
    task.report_summary = (
        f"样本 {n} 条，通过 {passed_n}，失败 {fail_n}，"
        f"通过率 {task.pass_rate:.2%}，平均分 {task.avg_score:.4f}。"
    )
    db.add(DatasetLog(
        dataset_id=task.dataset_id,
        version_id=version_id,
        task_id=task.id,
        operation_type="call",
        operation_desc=f"评测任务 {task.name} 调用数据集",
        operator="system",
        operation_result="success",
    ))
