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
    BaseResource,
    Dataset,
    DatasetItem,
    DatasetLog,
    DatasetVersion,
    EvalModel,
    EvalResult,
    EvalLineage,
    EvalTask,
    ModelCallLog,
    PromptTemplate,
    PromptVersion,
    PromptCallLog,
    ResourceCallLog,
    TaskSubtask,
)
from app.services.metrics import observe_eval_done
from app.services.model_client import invoke_model
from app.services.prompt_render import render_prompt
from app.services.report_archive import write_task_report
from app.services.task_events import emit_event
from app.utils.jsonutil import dumps

log = logging.getLogger(__name__)

DEFAULT_PROMPT = "{{input}}"
SHARD_SIZE = 50


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
                await emit_event(db, task_id, "failed", {"reason": "exception"})
                await db.commit()
            log.exception("eval task %s failed", task_id)
    from app.services.task_queue import dispatch_dependents
    await dispatch_dependents(task_id)


async def _run(db: AsyncSession, task_id: int) -> None:
    task = await db.get(EvalTask, task_id)
    if not task:
        return
    if task.status == "cancelled":
        return
    task.status = "running"
    task.started_at = datetime.utcnow()
    task.batch_id = str(uuid.uuid4())
    await emit_event(db, task.id, "running", {})
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
        await emit_event(db, task.id, "failed", {"reason": "no_dataset_version"})
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

    existing = (await db.execute(select(TaskSubtask).where(TaskSubtask.task_id == task.id))).scalars().all()
    if not existing:
        for i in range(0, max(len(items), 1), SHARD_SIZE):
            chunk = items[i:i + SHARD_SIZE] if items else []
            db.add(TaskSubtask(
                task_id=task.id,
                shard_no=i // SHARD_SIZE,
                status="pending",
                item_from=chunk[0].item_no if chunk else 0,
                item_to=chunk[-1].item_no if chunk else 0,
            ))
        await db.flush()

    model = await db.get(EvalModel, task.model_id)
    if not model:
        task.status = "failed"
        task.error_message = "被测模型不存在"
        task.finished_at = datetime.utcnow()
        await emit_event(db, task.id, "failed", {"reason": "no_model"})
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
                if not task.prompt_version_id:
                    task.prompt_version_id = pv.id
    if task.prompt_id:
        db.add(PromptCallLog(
            prompt_id=task.prompt_id,
            version_id=task.prompt_version_id,
            task_id=task.id,
            operator="system",
            operation="task",
        ))

    judge_id = task.judge_resource_id or "builtin/exact_match"
    res = await db.scalar(select(BaseResource).where(BaseResource.resource_id == judge_id))
    if res:
        task.tool_version = res.version or ""
    scores = []
    passed_n = 0
    fail_n = 0
    skip_n = 0
    tokens_used = 0
    subtasks = {(s.shard_no): s for s in (await db.execute(select(TaskSubtask).where(TaskSubtask.task_id == task.id))).scalars().all()}
    current_shard = None

    for idx, item in enumerate(items, start=1):
        fresh = await db.get(EvalTask, task.id)
        if fresh and fresh.status == "cancelled":
            task.status = "cancelled"
            task.finished_at = datetime.utcnow()
            await emit_event(db, task.id, "cancelled", {})
            return
        shard_no = (idx - 1) // SHARD_SIZE
        st = subtasks.get(shard_no)
        if st and current_shard != shard_no:
            if current_shard is not None and subtasks.get(current_shard):
                subtasks[current_shard].status = "success"
                subtasks[current_shard].finished_at = datetime.utcnow()
                subtasks[current_shard].progress = 100
            st.status = "running"
            st.started_at = datetime.utcnow()
            current_shard = shard_no

        quota = int(getattr(task, "token_quota", 0) or 0)
        if quota and tokens_used >= quota:
            skip_n += 1
            db.add(EvalResult(
                task_id=task.id,
                item_id=item.id,
                item_no=item.item_no,
                input_content=item.input_content,
                reference_answer=item.reference_answer,
                error_message="BUDGET_EXHAUSTED",
            ))
            task.progress = int(idx / max(len(items), 1) * 100)
            continue

        values = {
            "input": item.input_content,
            "question": item.input_content,
            "reference": item.reference_answer,
            "answer": item.reference_answer,
            "requirement": item.task_requirement,
            "scene": task.scene,
            "industry": task.industry,
        }
        prompt = render_prompt(template, values)
        err = ""
        output = ""
        latency = 0
        tokens = 0
        finish_reason = ""
        try:
            invoked = await invoke_model(model, prompt)
            output = invoked["output"]
            latency = invoked["latency_ms"]
            tokens = invoked["tokens"]
            finish_reason = invoked.get("finish_reason") or "stop"
            tokens_used += int(tokens or 0)
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
            await emit_event(db, task.id, "tool_failed", {"stage": "model", "item_no": item.item_no})
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
            await emit_event(db, task.id, "tool_failed", {"stage": "judge", "item_no": item.item_no})

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
            finish_reason=finish_reason,
        ))
        task.progress = int(idx / max(len(items), 1) * 100)
        task.success_count = passed_n
        task.fail_count = fail_n
        task.skip_count = skip_n
        task.tokens_used = tokens_used
        if idx % 20 == 0:
            await db.flush()

    if current_shard is not None and subtasks.get(current_shard):
        subtasks[current_shard].status = "success"
        subtasks[current_shard].finished_at = datetime.utcnow()
        subtasks[current_shard].progress = 100

    n = len(items)
    task.success_count = passed_n
    task.fail_count = fail_n
    task.skip_count = skip_n
    task.tokens_used = tokens_used
    task.avg_score = round(sum(scores) / len(scores), 4) if scores else 0
    task.pass_rate = round(passed_n / n, 4) if n else 0
    task.progress = 100
    task.status = "success"
    task.finished_at = datetime.utcnow()
    task.report_summary = (
        f"样本 {n} 条，通过 {passed_n}，失败 {fail_n}，跳过 {skip_n}，"
        f"通过率 {task.pass_rate:.2%}，平均分 {task.avg_score:.4f}。"
    )
    task.report_path = write_task_report(task)
    db.add(DatasetLog(
        dataset_id=task.dataset_id,
        version_id=version_id,
        task_id=task.id,
        operation_type="call",
        operation_desc=f"评测任务 {task.name} 调用数据集",
        operator="system",
        operation_result="success",
    ))
    await emit_event(db, task.id, "success", {"pass_rate": task.pass_rate})
    observe_eval_done()
    checksum = version.checksum if version else ""
    existing_lin = await db.scalar(select(EvalLineage).where(EvalLineage.task_id == task.id))
    if not existing_lin:
        db.add(EvalLineage(
            task_id=task.id,
            dataset_id=task.dataset_id,
            dataset_version_id=version_id,
            checksum=checksum or "",
            snapshot_id=task.snapshot_id or "",
            model_id=task.model_id,
            model_version_id=task.model_version_id,
            prompt_id=task.prompt_id,
            prompt_version_id=task.prompt_version_id,
            judge_resource_id=judge_id,
            tool_version=task.tool_version or "",
            channel_type=model.channel_type if model else "",
        ))
