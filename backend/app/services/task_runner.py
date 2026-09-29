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
from app.services.model_access import get_access_for_version, model_call_view
from app.services.model_client import invoke_model
from app.services.prompt_render import MissingRequiredVariable, render_prompt
from app.services.report_archive import result_row_for_report, write_task_report
from app.services.builtin_tools import run_builtin_tool
from app.services.task_events import emit_event
from app.services.task_service import fencing_still_valid, heartbeat_lease
from app.services.tool_gateway import invoke_tool, response_result
from app.utils.jsonutil import dumps, loads

log = logging.getLogger(__name__)

DEFAULT_PROMPT = "{{input}}"
SHARD_SIZE = 50


async def run_eval_task(
    task_id: int,
    *,
    fencing_token: int | None = None,
    lease_owner: str | None = None,
) -> None:
    async with async_session() as db:
        try:
            await _run(db, task_id, fencing_token=fencing_token, lease_owner=lease_owner)
            await db.commit()
        except Exception:
            await db.rollback()
            task = await db.get(EvalTask, task_id)
            if task:
                if fencing_token and int(getattr(task, "fencing_token", 0) or 0) != int(fencing_token):
                    log.warning("task %s stale fencing on exception, skip fail write", task_id)
                else:
                    task.status = "failed"
                    task.error_message = "任务执行异常"
                    task.finished_at = datetime.utcnow()
                    task.lease_owner = ""
                    task.lease_until = None
                    await emit_event(db, task_id, "failed", {"reason": "exception"})
                    await db.commit()
            log.exception("eval task %s failed", task_id)
    from app.services.task_queue import dispatch_dependents
    await dispatch_dependents(task_id)


async def _run(
    db: AsyncSession,
    task_id: int,
    *,
    fencing_token: int | None = None,
    lease_owner: str | None = None,
) -> None:
    task = await db.get(EvalTask, task_id)
    if not task:
        return
    if task.status == "cancelled" or getattr(task, "cancel_requested", False):
        task.status = "cancelled"
        task.finished_at = datetime.utcnow()
        return
    token = int(fencing_token or getattr(task, "fencing_token", 0) or 0)
    if fencing_token is not None and int(getattr(task, "fencing_token", 0) or 0) != int(fencing_token):
        log.warning("task %s fencing mismatch at start, abort", task_id)
        return
    if task.status != "running":
        task.status = "running"
        task.started_at = datetime.utcnow()
    if lease_owner:
        task.lease_owner = lease_owner
    task.batch_id = task.batch_id or str(uuid.uuid4())
    await emit_event(db, task.id, "running", {"fencing_token": token, "attempt": getattr(task, "attempt", 0) or 0})
    await db.commit()
    await db.refresh(task)

    version_id = task.dataset_version_id
    if not version_id:
        ds = await db.get(Dataset, task.dataset_id)
        version_id = ds.current_version_id if ds else None
        task.dataset_version_id = version_id
    if not version_id:
        task.status = "failed"
        task.error_message = "数据集没有可用版本"
        task.finished_at = datetime.utcnow()
        task.lease_owner = ""
        task.lease_until = None
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
        task.lease_owner = ""
        task.lease_until = None
        await emit_event(db, task.id, "failed", {"reason": "no_model"})
        return

    access_cfg = await get_access_for_version(db, model.id, task.model_version_id)
    if access_cfg is None and task.model_version_id:
        log.warning("task %s model_version_id=%s 无冻结配置，回退 live EvalModel", task.id, task.model_version_id)
    call_model = model_call_view(model, access_cfg)

    is_mock_model = not (call_model.api_url or "").strip()
    if is_mock_model and not bool(getattr(task, "trial_run", False)):
        task.status = "failed"
        task.error_message = "正式执行拒绝无 endpoint 模型；请配置 api_url 或使用 trial_run"
        task.finished_at = datetime.utcnow()
        task.simulation = False
        task.lease_owner = ""
        task.lease_until = None
        await emit_event(db, task.id, "failed", {"reason": "no_endpoint"})
        return
    if is_mock_model:
        task.simulation = True

    template = DEFAULT_PROMPT
    var_cfg: list = []
    if task.prompt_version_id:
        pv = await db.get(PromptVersion, task.prompt_version_id)
        if pv:
            template = pv.prompt_content or DEFAULT_PROMPT
            var_cfg = loads(pv.variable_config or "[]", []) or []
    elif task.prompt_id:
        pt = await db.get(PromptTemplate, task.prompt_id)
        if pt and pt.current_version_id:
            pv = await db.get(PromptVersion, pt.current_version_id)
            if pv:
                template = pv.prompt_content or DEFAULT_PROMPT
                var_cfg = loads(pv.variable_config or "[]", []) or []
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
    done_rows = (await db.execute(select(EvalResult).where(EvalResult.task_id == task.id))).scalars().all()
    done_nos = {r.item_no for r in done_rows}
    scores = [float(r.score or 0) for r in done_rows if (r.score_status or "") == "scored"]
    passed_n = sum(1 for r in done_rows if r.passed and (r.score_status or "") == "scored")
    fail_n = sum(1 for r in done_rows if (not r.passed) and (r.score_status or "") == "scored")
    skip_n = sum(1 for r in done_rows if (r.execution_status or "") == "skipped" or (r.score_status or "") == "skipped")
    judge_error_n = sum(1 for r in done_rows if (r.score_status or "") == "error")
    tokens_used = int(task.tokens_used or 0)
    subtasks = {(s.shard_no): s for s in (await db.execute(select(TaskSubtask).where(TaskSubtask.task_id == task.id))).scalars().all()}
    current_shard = None

    for idx, item in enumerate(items, start=1):
        ok_fence, cancel_req = await fencing_still_valid(db, task.id, token)
        if not ok_fence:
            log.warning("task %s lost fencing, stop write", task.id)
            return
        if cancel_req:
            task.status = "cancelled"
            task.finished_at = datetime.utcnow()
            task.lease_owner = ""
            task.lease_until = None
            await emit_event(db, task.id, "cancelled", {"phase": "running"})
            return
        if item.item_no in done_nos:
            task.progress = int(idx / max(len(items), 1) * 100)
            continue
        await heartbeat_lease(db, task.id, token)
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
            task.status = "paused_budget"
            task.error_message = "BUDGET_EXHAUSTED"
            task.finished_at = datetime.utcnow()
            task.lease_owner = ""
            task.lease_until = None
            task.tokens_used = tokens_used
            task.progress = int(idx / max(len(items), 1) * 100)
            await emit_event(db, task.id, "paused_budget", {"tokens_used": tokens_used, "token_quota": quota})
            return

        values = {
            "input": item.input_content,
            "question": item.input_content,
            "reference": item.reference_answer,
            "answer": item.reference_answer,
            "requirement": item.task_requirement,
            "scene": task.scene,
            "industry": task.industry,
        }
        try:
            prompt = render_prompt(template, values, variable_config=var_cfg, strict=not bool(getattr(task, "trial_run", False)))
        except MissingRequiredVariable as exc:
            skip_n += 1
            db.add(EvalResult(
                task_id=task.id,
                item_no=item.item_no,
                input_content=item.input_content,
                model_output="",
                reference_answer=item.reference_answer,
                score=0,
                passed=False,
                metrics_json="{}",
                latency_ms=0,
                token_usage=0,
                error_message=str(exc),
                execution_status="skipped",
                score_status="skipped",
                simulation=bool(getattr(task, "simulation", False)),
            ))
            task.progress = int(idx / max(len(items), 1) * 100)
            task.skip_count = skip_n
            done_nos.add(item.item_no)
            await db.commit()
            await db.refresh(task)
            continue
        err = ""
        output = ""
        latency = 0
        tokens = 0
        finish_reason = ""
        try:
            invoked = await invoke_model(call_model, prompt)
            output = invoked["output"]
            latency = invoked["latency_ms"]
            tokens = invoked["tokens"]
            finish_reason = invoked.get("finish_reason") or "stop"
            tokens_used += int(tokens or 0)
            if invoked.get("mock"):
                task.simulation = True
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
                execution_status="model_failed",
                score_status="skipped",
                simulation=bool(getattr(task, "simulation", False)),
            ))
            task.progress = int(idx / max(len(items), 1) * 100)
            task.fail_count = fail_n
            done_nos.add(item.item_no)
            await emit_event(db, task.id, "tool_failed", {"stage": "model", "item_no": item.item_no})
            await db.commit()
            await db.refresh(task)
            continue

        judge_failed = False
        try:
            from app.services.actor_context import ActorContext
            # 系统执行：以任务租户为范围；无用户时 actor 为 None，幂等键 tenant=""
            actor = None
            if getattr(task, "tenant_id", None):
                actor = ActorContext(
                    user_id=int(task.creator_id or 0),
                    username="system",
                    tenant_id=int(task.tenant_id),
                    role_code="system",
                    data_scope="all",
                    permissions=set(),
                    is_admin=True,
                )
            envelope = await invoke_tool(
                db,
                actor=actor,
                resource_id=judge_id,
                body={"prediction": output, "reference": item.reference_answer, "pattern": item.expected_output or item.reference_answer},
                task_id=task.id,
                caller_id="task_runner",
            )
            judged = response_result(envelope)
            if (envelope.get("body") or {}).get("status") == "error":
                raise RuntimeError((envelope.get("body") or {}).get("error", {}).get("message") or "judge failed")
            # ResourceCallLog 已由网关写入
        except Exception as exc:
            judged = {"score": 0, "passed": False, "metrics": {}}
            err = str(exc)
            judge_failed = True
            judge_error_n += 1
            await emit_event(db, task.id, "tool_failed", {"stage": "judge", "item_no": item.item_no})

        score = float(judged.get("score") or 0)
        passed = bool(judged.get("passed"))
        sim = bool(getattr(task, "simulation", False)) or bool(judged.get("demo_only"))
        if sim:
            task.simulation = True
        if judge_failed:
            score_status = "error"
            execution_status = "ok"
        else:
            score_status = "scored"
            execution_status = "ok"
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
            passed=passed if not judge_failed else False,
            metrics_json=dumps(judged.get("metrics") or {}),
            error_message=err,
            latency_ms=latency,
            finish_reason=finish_reason,
            execution_status=execution_status,
            score_status=score_status,
            simulation=sim,
        ))
        task.progress = int(idx / max(len(items), 1) * 100)
        task.success_count = passed_n
        task.fail_count = fail_n
        task.skip_count = skip_n
        task.tokens_used = tokens_used
        done_nos.add(item.item_no)
        # 逐样本提交，供其它连接实时查询进度
        await db.commit()
        await db.refresh(task)

    if current_shard is not None and subtasks.get(current_shard):
        subtasks[current_shard].status = "success"
        subtasks[current_shard].finished_at = datetime.utcnow()
        subtasks[current_shard].progress = 100

    n = len(items)
    # 终态前再次确认 fencing / 取消
    ok_fence, cancel_req = await fencing_still_valid(db, task.id, token)
    if not ok_fence:
        log.warning("task %s lost fencing before finalize", task.id)
        return
    if cancel_req:
        task.status = "cancelled"
        task.finished_at = datetime.utcnow()
        task.lease_owner = ""
        task.lease_until = None
        await emit_event(db, task.id, "cancelled", {"phase": "finalize"})
        return

    task.success_count = passed_n
    task.fail_count = fail_n + judge_error_n
    task.skip_count = skip_n
    task.tokens_used = tokens_used
    task.avg_score = round(sum(scores) / len(scores), 4) if scores else 0
    task.pass_rate = round(passed_n / n, 4) if n else 0
    task.progress = 100
    task.finished_at = datetime.utcnow()
    task.lease_owner = ""
    task.lease_until = None
    if n == 0:
        task.status = "success"
    elif judge_error_n == n:
        task.status = "failed"
        task.error_message = task.error_message or "全部样本裁判失败"
    elif fail_n or judge_error_n:
        task.status = "partial_failed" if (passed_n or scores) else "failed"
    else:
        task.status = "success"
    task.report_summary = (
        f"样本 {n} 条，通过 {passed_n}，失败 {fail_n}，裁判失败 {judge_error_n}，跳过 {skip_n}，"
        f"通过率 {task.pass_rate:.2%}，平均分 {task.avg_score:.4f}"
        f"{'（simulation）' if getattr(task, 'simulation', False) else ''}。"
    )
    result_rows = (
        await db.execute(select(EvalResult).where(EvalResult.task_id == task.id).order_by(EvalResult.item_no))
    ).scalars().all()
    ds = await db.get(Dataset, task.dataset_id)
    prompt_row = await db.get(PromptTemplate, task.prompt_id) if task.prompt_id else None
    task.report_path = write_task_report(task, {
        "dataset_name": ds.name if ds else "",
        "model_name": model.name if model else "",
        "channel_type": getattr(model, "channel_type", "") or "",
        "prompt_name": prompt_row.name if prompt_row else "",
        "results": [result_row_for_report(r) for r in result_rows],
    })
    db.add(DatasetLog(
        dataset_id=task.dataset_id,
        version_id=version_id,
        task_id=task.id,
        operation_type="call",
        operation_desc=f"评测任务 {task.name} 调用数据集",
        operator="system",
        operation_result=task.status,
    ))
    await emit_event(db, task.id, task.status, {"pass_rate": task.pass_rate, "simulation": bool(getattr(task, "simulation", False))})
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
