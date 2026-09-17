"""提示词工程。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import PromptTemplate, PromptVersion, User
from app.services.audit import get_client_ip, log_audit
from app.services.prompt_render import extract_variables, render_prompt
from app.services.serializers import prompt_out
from app.utils.jsonutil import dumps, loads

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


class PreviewBody(BaseModel):
    prompt_content: str | None = None
    values: dict = {}


def _next_version(current: str) -> str:
    try:
        num = float(current.upper().lstrip("V"))
        return f"V{num + 0.1:.1f}"
    except Exception:
        return "V1.1"


@router.get("")
async def list_prompts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    search: str = Query(""),
    status: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("prompt:list")),
):
    q = select(PromptTemplate)
    if search:
        q = q.where(or_(PromptTemplate.name.contains(search), PromptTemplate.description.contains(search)))
    if status:
        q = q.where(PromptTemplate.status == status)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(PromptTemplate.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [prompt_out(p) for p in rows], "total": total or 0}


@router.post("")
async def create_prompt(
    body: PromptCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:create")),
):
    if not (body.prompt_content or "").strip():
        raise HTTPException(400, "提示词内容不能为空")
    p = PromptTemplate(
        name=body.name,
        prompt_type=body.prompt_type,
        applicable_task=body.applicable_task,
        applicable_model=body.applicable_model,
        applicable_scene=body.applicable_scene,
        description=body.description,
        creator_id=current.id,
    )
    db.add(p)
    await db.flush()
    variables = extract_variables(body.prompt_content)
    ver = PromptVersion(
        prompt_id=p.id,
        version_code="V1.0",
        prompt_content=body.prompt_content,
        variable_config=dumps(variables),
        output_format=body.output_format,
        creator_id=current.id,
    )
    db.add(ver)
    await db.flush()
    p.current_version_id = ver.id
    await log_audit(db, "prompt", "create", user_id=current.id, username=current.username, target_id=p.id, ip=get_client_ip(request))
    return {**prompt_out(p), "prompt_content": ver.prompt_content, "variables": variables}


@router.get("/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("prompt:view")),
):
    p = await db.get(PromptTemplate, prompt_id)
    if not p:
        raise HTTPException(404, "提示词不存在")
    versions = (await db.execute(select(PromptVersion).where(PromptVersion.prompt_id == prompt_id).order_by(PromptVersion.id.desc()))).scalars().all()
    current = await db.get(PromptVersion, p.current_version_id) if p.current_version_id else None
    return {
        **prompt_out(p),
        "prompt_content": current.prompt_content if current else "",
        "variables": loads(current.variable_config, []) if current else [],
        "output_format": current.output_format if current else "text",
        "versions": [
            {
                "id": v.id,
                "version_code": v.version_code,
                "prompt_content": v.prompt_content,
                "variables": loads(v.variable_config, []),
                "change_desc": v.change_desc,
                "status": v.status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
    }


@router.put("/{prompt_id}")
async def update_prompt(
    prompt_id: int,
    body: PromptUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:edit")),
):
    p = await db.get(PromptTemplate, prompt_id)
    if not p:
        raise HTTPException(404, "提示词不存在")
    data = body.model_dump(exclude_unset=True)
    content = data.pop("prompt_content", None)
    output_format = data.pop("output_format", None)
    change_desc = data.pop("change_desc", "")
    for k, v in data.items():
        setattr(p, k, v)
    if content is not None:
        if not content.strip():
            raise HTTPException(400, "提示词内容不能为空")
        code = _next_version(p.current_version)
        ver = PromptVersion(
            prompt_id=p.id,
            version_code=code,
            prompt_content=content,
            variable_config=dumps(extract_variables(content)),
            output_format=output_format or "text",
            change_desc=change_desc or "",
            creator_id=current.id,
        )
        db.add(ver)
        await db.flush()
        p.current_version = code
        p.current_version_id = ver.id
        p.status = "draft"
    await log_audit(db, "prompt", "update", user_id=current.id, username=current.username, target_id=p.id, ip=get_client_ip(request))
    return prompt_out(p)


@router.post("/{prompt_id}/publish")
async def publish_prompt(
    prompt_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:publish")),
):
    p = await db.get(PromptTemplate, prompt_id)
    if not p:
        raise HTTPException(404, "提示词不存在")
    p.status = "published"
    if p.current_version_id:
        ver = await db.get(PromptVersion, p.current_version_id)
        if ver:
            ver.status = "published"
    await log_audit(db, "prompt", "publish", user_id=current.id, username=current.username, target_id=p.id, ip=get_client_ip(request))
    return prompt_out(p)


@router.post("/{prompt_id}/preview")
async def preview_prompt(
    prompt_id: int,
    body: PreviewBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("prompt:view")),
):
    p = await db.get(PromptTemplate, prompt_id)
    if not p:
        raise HTTPException(404, "提示词不存在")
    content = body.prompt_content
    if content is None and p.current_version_id:
        ver = await db.get(PromptVersion, p.current_version_id)
        content = ver.prompt_content if ver else ""
    rendered = render_prompt(content or "", body.values or {})
    return {"rendered": rendered, "variables": extract_variables(content or "")}


@router.delete("/{prompt_id}")
async def delete_prompt(
    prompt_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("prompt:delete")),
):
    p = await db.get(PromptTemplate, prompt_id)
    if not p:
        raise HTTPException(404, "提示词不存在")
    if p.status == "published":
        p.status = "archived"
        return prompt_out(p)
    await db.execute(PromptVersion.__table__.delete().where(PromptVersion.prompt_id == prompt_id))
    await db.delete(p)
    await log_audit(db, "prompt", "delete", user_id=current.id, username=current.username, target_id=prompt_id, ip=get_client_ip(request))
    return {"ok": True}
