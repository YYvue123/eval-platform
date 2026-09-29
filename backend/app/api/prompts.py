"""提示词工程。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission, require_actor
from app.database import get_db
from app.models import (
    Dataset,
    DatasetItem,
    EvalModel,
    EvalTask,
    PromptCallLog,
    PromptExperiment,
    PromptTemplate,
    PromptTestRun,
    PromptVersion,
    User,
)
from app.services.actor_context import ActorContext, effective_tenant_id
from app.services.object_policy import apply_object_scope, get_visible_or_404, object_is_visible
from app.services.audit import get_client_ip, log_audit
from app.services.builtin_tools import run_builtin_tool
from app.services.model_client import invoke_model
from app.services.prompt_craft import build_variable_config, generate_draft, optimize_prompt
from app.services.prompt_render import extract_variables, render_prompt
from app.services.serializers import prompt_out
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


class PromptCreate(BaseModel):
    name: str
    prompt_type: str = "eval"
    applicable_task: str = "qa"
    applicable_model: str = ""
    applicable_scene: str = ""
    description: str = ""
    prompt_content: str = "{{input}}"
    output_format: str = "text"
    tags: list[str] = Field(default_factory=list)
    constraints: str = ""


class PromptUpdate(BaseModel):
    name: str | None = None
    prompt_type: str | None = None
    applicable_task: str | None = None
    applicable_model: str | None = None
    applicable_scene: str | None = None
    description: str | None = None
    prompt_content: str | None = None
    output_format: str | None = None
    change_desc: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    constraints: str | None = None
    variable_config: list | None = None


class PreviewBody(BaseModel):
    prompt_content: str | None = None
    values: dict = {}


class GenerateBody(BaseModel):
    task_type: str = "qa"
    metrics: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)


class AuditBody(BaseModel):
    action: str
    comment: str = ""


class TestBody(BaseModel):
    dataset_id: int
    model_id: int
    version_id: int | None = None
    compare_version_id: int | None = None
    limit: int = 5


def _next_version(current: str) -> str:
    try:
        num = float(current.upper().lstrip("V"))
        return f"V{num + 0.1:.1f}"
    except Exception:
        return "V1.1"


def _version_out(v: PromptVersion) -> dict:
    return {
        "id": v.id,
        "version_code": v.version_code,
        "prompt_content": v.prompt_content,
        "variables": loads(v.variable_config, []),
        "output_format": v.output_format,
        "change_desc": v.change_desc,
        "status": v.status,
        "created_at": iso(v.created_at),
    }


async def _require_prompt(db, prompt_id: int) -> PromptTemplate:
    p = await db.get(PromptTemplate, prompt_id)
    if not p or p.status == "deleted":
        raise HTTPException(404, "提示词不存在")
    return p


@router.get("")
async def list_prompts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    search: str = Query(""),
    status: str = Query(""),
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("prompt:list")),
):
    q = select(PromptTemplate).where(PromptTemplate.status != "deleted")
    q = apply_object_scope(q, PromptTemplate, actor)
    if search:
        q = q.where(or_(PromptTemplate.name.contains(search), PromptTemplate.description.contains(search)))
    if status:
        q = q.where(PromptTemplate.status == status)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(PromptTemplate.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [prompt_out(p) for p in rows], "total": total or 0}


@router.post("/generate")
async def generate_prompt_draft(
    body: GenerateBody,
    _: User = Depends(require_permission("prompt:create")),
):
    return generate_draft(body.task_type, body.metrics, body.fields)


@router.post("")
async def create_prompt(
    body: PromptCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("prompt:create")),
):
    if not (body.prompt_content or "").strip():
        raise HTTPException(400, "提示词内容不能为空")
    exists = await db.scalar(select(PromptTemplate.id).where(
        PromptTemplate.name == body.name,
        PromptTemplate.status != "deleted",
        PromptTemplate.tenant_id == actor.tenant_id,
    ))
    if exists:
        raise HTTPException(400, "提示词名称已存在")
    p = PromptTemplate(
        name=body.name,
        prompt_type=body.prompt_type,
        applicable_task=body.applicable_task,
        applicable_model=body.applicable_model,
        applicable_scene=body.applicable_scene,
        description=body.description,
        tags=dumps(body.tags),
        constraints=body.constraints,
        creator_id=actor.user_id,
        tenant_id=effective_tenant_id(actor, None),
        visibility="private",
    )
    db.add(p)
    await db.flush()
    variables = build_variable_config(body.prompt_content)
    ver = PromptVersion(
        prompt_id=p.id,
        version_code="V1.0",
        prompt_content=body.prompt_content,
        variable_config=dumps(variables),
        output_format=body.output_format,
        creator_id=actor.user_id,
    )
    db.add(ver)
    await db.flush()
    p.current_version_id = ver.id
    await log_audit(db, "prompt", "create", user_id=actor.user_id, username=actor.username, target_id=p.id, ip=get_client_ip(request))
    return {**prompt_out(p), "prompt_content": ver.prompt_content, "variables": variables}


@router.get("/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("prompt:view")),
):
    p = await get_visible_or_404(db, PromptTemplate, prompt_id, actor, not_found="提示词不存在或无权访问")
    if p.status == "deleted":
        raise HTTPException(404, "提示词不存在或无权访问")
    versions = (await db.execute(select(PromptVersion).where(PromptVersion.prompt_id == prompt_id).order_by(PromptVersion.id.desc()))).scalars().all()
    current = await db.get(PromptVersion, p.current_version_id) if p.current_version_id else None
    used = (await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.prompt_id == prompt_id))) or 0
    return {
        **prompt_out(p),
        "in_use": used,
        "prompt_content": current.prompt_content if current else "",
        "variables": loads(current.variable_config, []) if current else [],
        "output_format": current.output_format if current else "text",
        "versions": [_version_out(v) for v in versions],
    }


@router.put("/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    body: PromptUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:edit")),
):
    p = await _require_prompt(db, prompt_id)
    data = body.model_dump(exclude_unset=True)
    content = data.pop("prompt_content", None)
    output_format = data.pop("output_format", None)
    change_desc = data.pop("change_desc", "")
    variable_config = data.pop("variable_config", None)
    if "tags" in data:
        p.tags = dumps(data.pop("tags") or [])
    if data.get("status") in {"published", "deleted"}:
        raise HTTPException(400, "不允许直接修改为该状态")
    for k, v in data.items():
        setattr(p, k, v)
    if content is not None:
        if not content.strip():
            raise HTTPException(400, "提示词内容不能为空")
        code = _next_version(p.current_version)
        exists = await db.scalar(select(PromptVersion.id).where(PromptVersion.prompt_id == p.id, PromptVersion.version_code == code))
        if exists:
            raise HTTPException(400, "版本号冲突，请稍后重试")
        vars_cfg = variable_config if variable_config is not None else build_variable_config(content)
        ver = PromptVersion(
            prompt_id=p.id,
            version_code=code,
            prompt_content=content,
            variable_config=dumps(vars_cfg),
            output_format=output_format or "text",
            change_desc=change_desc or "",
            creator_id=current.id,
        )
        db.add(ver)
        await db.flush()
        p.current_version = code
        p.current_version_id = ver.id
        if p.status in {"published", "pending"}:
            p.status = "draft"
    elif variable_config is not None and p.current_version_id:
        ver = await db.get(PromptVersion, p.current_version_id)
        if ver:
            if ver.status == "published" or p.status == "published":
                # 已发布版本禁止原地改：复制新版本
                code = _next_version(p.current_version)
                nv = PromptVersion(
                    prompt_id=p.id,
                    version_code=code,
                    prompt_content=ver.prompt_content,
                    variable_config=dumps(variable_config),
                    output_format=ver.output_format,
                    change_desc=change_desc or "变量配置变更",
                    creator_id=current.id,
                    status="draft",
                )
                db.add(nv)
                await db.flush()
                p.current_version = code
                p.current_version_id = nv.id
                if p.status in {"published", "pending"}:
                    p.status = "draft"
            else:
                ver.variable_config = dumps(variable_config)
    await log_audit(db, "prompt", "update", user_id=current.id, username=current.username, target_id=p.id, ip=get_client_ip(request))
    return prompt_out(p)


@router.post("/{prompt_id}/copy")
async def copy_prompt(
    prompt_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("prompt:create")),
):
    p = await get_visible_or_404(db, PromptTemplate, prompt_id, actor, not_found="提示词不存在或无权访问")
    if p.status == "deleted":
        raise HTTPException(404, "提示词不存在或无权访问")
    ver = await db.get(PromptVersion, p.current_version_id) if p.current_version_id else None
    name = f"{p.name}-副本"
    n = 1
    while await db.scalar(select(PromptTemplate.id).where(
        PromptTemplate.name == name,
        PromptTemplate.status != "deleted",
        PromptTemplate.tenant_id == actor.tenant_id,
    )):
        n += 1
        name = f"{p.name}-副本{n}"
    np = PromptTemplate(
        name=name,
        prompt_type=p.prompt_type,
        applicable_task=p.applicable_task,
        applicable_model=p.applicable_model,
        applicable_scene=p.applicable_scene,
        description=p.description,
        tags=p.tags,
        constraints=p.constraints,
        creator_id=actor.user_id,
        tenant_id=effective_tenant_id(actor, None),
        visibility="private",
        current_version="V1.0",
    )
    db.add(np)
    await db.flush()
    nv = PromptVersion(
        prompt_id=np.id,
        version_code="V1.0",
        prompt_content=ver.prompt_content if ver else "{{input}}",
        variable_config=ver.variable_config if ver else "[]",
        output_format=ver.output_format if ver else "text",
        change_desc="复制",
        creator_id=actor.user_id,
    )
    db.add(nv)
    await db.flush()
    np.current_version_id = nv.id
    await log_audit(db, "prompt", "copy", user_id=actor.user_id, username=actor.username, target_id=np.id, ip=get_client_ip(request))
    return prompt_out(np)


@router.post("/{prompt_id}/submit")
async def submit_prompt(
    prompt_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:edit")),
):
    p = await _require_prompt(db, prompt_id)
    if p.status not in {"draft", "rejected"}:
        raise HTTPException(400, "仅草稿或已退回可提交审核")
    if not p.current_version_id:
        raise HTTPException(400, "请先填写提示词内容")
    p.status = "pending"
    p.review_comment = ""
    await log_audit(db, "prompt", "submit", user_id=current.id, username=current.username, target_id=p.id, ip=get_client_ip(request))
    return prompt_out(p)


@router.post("/{prompt_id}/audit")
async def audit_prompt(
    prompt_id: int,
    body: AuditBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:audit")),
):
    p = await _require_prompt(db, prompt_id)
    if p.status != "pending":
        raise HTTPException(400, "仅待审核提示词可审核")
    if body.action not in {"approve", "reject"}:
        raise HTTPException(400, "action 必须是 approve 或 reject")
    if body.action == "approve":
        p.status = "published"
        p.review_comment = body.comment
        if p.current_version_id:
            ver = await db.get(PromptVersion, p.current_version_id)
            if ver:
                ver.status = "published"
        op = "publish"
    else:
        p.status = "rejected"
        p.review_comment = body.comment or "审核退回"
        op = "reject"
    await log_audit(db, "prompt", op, user_id=current.id, username=current.username, target_id=p.id, ip=get_client_ip(request))
    return prompt_out(p)


@router.post("/{prompt_id}/publish")
async def publish_prompt(
    prompt_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:publish")),
):
    p = await _require_prompt(db, prompt_id)
    p.status = "published"
    p.review_comment = ""
    if p.current_version_id:
        ver = await db.get(PromptVersion, p.current_version_id)
        if ver:
            ver.status = "published"
    await log_audit(db, "prompt", "publish", user_id=current.id, username=current.username, target_id=p.id, ip=get_client_ip(request))
    return prompt_out(p)


@router.post("/{prompt_id}/optimize")
async def optimize_prompt_api(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:edit")),
):
    p = await _require_prompt(db, prompt_id)
    ver = await db.get(PromptVersion, p.current_version_id) if p.current_version_id else None
    result = optimize_prompt(ver.prompt_content if ver else "")
    created = None
    if result["changed"]:
        code = _next_version(p.current_version)
        nv = PromptVersion(
            prompt_id=p.id,
            version_code=code,
            prompt_content=result["optimized"],
            variable_config=dumps(build_variable_config(result["optimized"], loads(ver.variable_config, []) if ver else [])),
            output_format=ver.output_format if ver else "text",
            change_desc="规则优化：" + "；".join(result["suggestions"]),
            creator_id=current.id,
        )
        db.add(nv)
        await db.flush()
        p.current_version = code
        p.current_version_id = nv.id
        p.status = "draft"
        created = _version_out(nv)
    return {**result, "new_version": created}


@router.post("/{prompt_id}/versions/{version_id}/restore")
async def restore_version(
    prompt_id: int,
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:edit")),
):
    p = await _require_prompt(db, prompt_id)
    ver = await db.get(PromptVersion, version_id)
    if not ver or ver.prompt_id != prompt_id:
        raise HTTPException(404, "版本不存在")
    p.current_version_id = ver.id
    p.current_version = ver.version_code
    if p.status == "published":
        p.status = "draft"
    return prompt_out(p)


@router.get("/{prompt_id}/compare")
async def compare_versions(
    prompt_id: int,
    left: int = Query(...),
    right: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("prompt:view")),
):
    await _require_prompt(db, prompt_id)
    a = await db.get(PromptVersion, left)
    b = await db.get(PromptVersion, right)
    if not a or not b or a.prompt_id != prompt_id or b.prompt_id != prompt_id:
        raise HTTPException(404, "版本不存在")
    return {"left": _version_out(a), "right": _version_out(b)}


@router.post("/{prompt_id}/preview")
async def preview_prompt(
    prompt_id: int,
    body: PreviewBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("prompt:view")),
):
    p = await _require_prompt(db, prompt_id)
    content = body.prompt_content
    if content is None and p.current_version_id:
        ver = await db.get(PromptVersion, p.current_version_id)
        content = ver.prompt_content if ver else ""
    rendered = render_prompt(content or "", body.values or {})
    missing = [k for k in extract_variables(content or "") if k not in (body.values or {})]
    return {"rendered": rendered, "variables": extract_variables(content or ""), "unbound": missing}


@router.post("/{prompt_id}/tests")
async def run_prompt_test(
    prompt_id: int,
    body: TestBody,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:edit")),
):
    p = await _require_prompt(db, prompt_id)
    ds = await db.get(Dataset, body.dataset_id)
    model = await db.get(EvalModel, body.model_id)
    if not ds or ds.status == "deleted":
        raise HTTPException(400, "数据集不存在")
    if not model or model.status == "deleted":
        raise HTTPException(400, "被测模型不存在")
    vid = body.version_id or p.current_version_id
    ver = await db.get(PromptVersion, vid) if vid else None
    if not ver:
        raise HTTPException(400, "没有可测试的版本")
    items = (await db.execute(
        select(DatasetItem).where(DatasetItem.version_id == ds.current_version_id, DatasetItem.status != "deleted").order_by(DatasetItem.item_no).limit(max(1, min(body.limit, 20)))
    )).scalars().all()
    if not items:
        raise HTTPException(400, "数据集没有可用条目")
    p.status = "testing"

    async def _score(version: PromptVersion):
        scores = []
        rows = []
        for item in items:
            rendered = render_prompt(version.prompt_content, {
                "input": item.input_content,
                "question": item.input_content,
                "reference": item.reference_answer,
            })
            try:
                invoked = await invoke_model(model, rendered)
                judged = run_builtin_tool("builtin/contains", {"prediction": invoked["output"], "reference": item.reference_answer})
                score = float(judged.get("score") or 0)
            except Exception as exc:
                invoked = {"output": "", "latency_ms": 0}
                score = 0
                judged = {"error": str(exc)}
            scores.append(score)
            rows.append({"item_no": item.item_no, "score": score, "output": invoked.get("output", "")[:500]})
            db.add(PromptCallLog(prompt_id=p.id, version_id=version.id, operator=current.username, operation="test"))
        avg = round(sum(scores) / len(scores), 4) if scores else 0
        return avg, rows

    avg, rows = await _score(ver)
    cmp_avg, cmp_rows = 0, []
    cver = None
    if body.compare_version_id:
        cver = await db.get(PromptVersion, body.compare_version_id)
        if cver and cver.prompt_id == p.id:
            cmp_avg, cmp_rows = await _score(cver)
    run = PromptTestRun(
        prompt_id=p.id,
        version_id=ver.id,
        compare_version_id=cver.id if cver else None,
        dataset_id=ds.id,
        model_id=model.id,
        status="done",
        sample_count=len(items),
        avg_score=avg,
        compare_avg_score=cmp_avg,
        result_json=dumps({"rows": rows, "compare_rows": cmp_rows}),
        creator_id=current.id,
    )
    db.add(run)
    p.status = "draft"
    await db.flush()
    return {
        "id": run.id,
        "avg_score": avg,
        "compare_avg_score": cmp_avg,
        "sample_count": len(items),
        "rows": rows,
        "compare_rows": cmp_rows,
    }


@router.get("/{prompt_id}/tests")
async def list_prompt_tests(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("prompt:view")),
):
    await _require_prompt(db, prompt_id)
    rows = (await db.execute(select(PromptTestRun).where(PromptTestRun.prompt_id == prompt_id).order_by(PromptTestRun.id.desc()).limit(20))).scalars().all()
    return [
        {
            "id": r.id,
            "version_id": r.version_id,
            "compare_version_id": r.compare_version_id,
            "dataset_id": r.dataset_id,
            "model_id": r.model_id,
            "sample_count": r.sample_count,
            "avg_score": r.avg_score,
            "compare_avg_score": r.compare_avg_score,
            "result": loads(r.result_json, {}),
            "created_at": iso(r.created_at),
        }
        for r in rows
    ]


@router.get("/{prompt_id}/stats")
async def prompt_stats(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("prompt:view")),
):
    await _require_prompt(db, prompt_id)
    tasks = (await db.execute(select(EvalTask).where(EvalTask.prompt_id == prompt_id))).scalars().all()
    scores = [t.avg_score for t in tasks if t.status == "success"]
    calls = (await db.scalar(select(func.count()).select_from(PromptCallLog).where(PromptCallLog.prompt_id == prompt_id))) or 0
    tests = (await db.execute(select(PromptTestRun).where(PromptTestRun.prompt_id == prompt_id).order_by(PromptTestRun.id.desc()))).scalars().all()
    avg = round(sum(scores) / len(scores), 4) if scores else 0
    stability = 0.0
    if len(scores) >= 2:
        mean = avg
        var = sum((s - mean) ** 2 for s in scores) / len(scores)
        stability = round(max(0.0, 1 - var), 4)
    return {
        "task_count": len(tasks),
        "success_task_count": len(scores),
        "avg_score": avg,
        "stability": stability,
        "call_count": calls,
        "test_count": len(tests),
        "last_test_score": tests[0].avg_score if tests else None,
    }


@router.get("/{prompt_id}/logs")
async def prompt_logs(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("prompt:view")),
):
    await _require_prompt(db, prompt_id)
    rows = (await db.execute(select(PromptCallLog).where(PromptCallLog.prompt_id == prompt_id).order_by(PromptCallLog.id.desc()).limit(50))).scalars().all()
    return [
        {
            "id": lg.id,
            "version_id": lg.version_id,
            "task_id": lg.task_id,
            "operator": lg.operator,
            "operation": lg.operation,
            "result": lg.result,
            "created_at": iso(lg.created_at),
        }
        for lg in rows
    ]




class ExperimentIn(BaseModel):
    dataset_id: int
    holdout_ratio: float = 0.3
    token_budget: int = 500


class ExperimentPublishIn(BaseModel):
    force: bool = False


@router.post("/{prompt_id}/experiments")
async def create_prompt_experiment(
    prompt_id: int,
    body: ExperimentIn,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("prompt:edit")),
):
    from app.services import prompt_experiment as pexp
    prompt = await get_visible_or_404(db, PromptTemplate, prompt_id, actor, not_found="提示词不存在或无权访问")
    exp = await pexp.create_and_run_experiment(
        db,
        prompt=prompt,
        dataset_id=body.dataset_id,
        holdout_ratio=body.holdout_ratio,
        token_budget=body.token_budget,
        creator_id=actor.user_id,
        tenant_id=actor.tenant_id,
    )
    return pexp.experiment_out(exp)


@router.get("/{prompt_id}/experiments")
async def list_prompt_experiments(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("prompt:view")),
):
    from app.services import prompt_experiment as pexp
    await get_visible_or_404(db, PromptTemplate, prompt_id, actor, not_found="提示词不存在或无权访问")
    rows = (await db.execute(select(PromptExperiment).where(PromptExperiment.prompt_id == prompt_id).order_by(PromptExperiment.id.desc()).limit(20))).scalars().all()
    return {"items": [pexp.experiment_out(e) for e in rows], "total": len(rows)}


@router.post("/{prompt_id}/experiments/{eid}/publish")
async def publish_prompt_experiment(
    prompt_id: int,
    eid: int,
    body: ExperimentPublishIn,
    db: AsyncSession = Depends(get_db),
    actor: ActorContext = Depends(require_actor("prompt:publish")),
):
    from app.services import prompt_experiment as pexp
    prompt = await get_visible_or_404(db, PromptTemplate, prompt_id, actor, not_found="提示词不存在或无权访问")
    exp = await db.get(PromptExperiment, eid)
    if not exp or exp.prompt_id != prompt_id:
        raise HTTPException(404, "实验不存在")
    return await pexp.try_publish_from_experiment(db, exp, prompt, force=body.force)


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:delete")),
):
    p = await _require_prompt(db, prompt_id)
    used = (await db.scalar(select(func.count()).select_from(EvalTask).where(EvalTask.prompt_id == prompt_id))) or 0
    p.status = "deleted"
    await log_audit(db, "prompt", "delete", user_id=current.id, username=current.username, target_id=prompt_id, ip=get_client_ip(request))
    return {"ok": True, "logical": True, "task_count": used}
