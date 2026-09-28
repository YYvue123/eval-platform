"""数据质量测试：规则、检测、问题工单、报告。"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.config import settings
from app.database import get_db
from app.models import Dataset, DatasetItem, DatasetVersion, QualityIssue, QualityReport, QualityRule, User
from app.services.dataset_revision import apply_item_changes
from app.services.quality_checker import check_items
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


class RuleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    severity: str | None = None
    enabled: bool | None = None
    config: dict | None = None


class IssueHandle(BaseModel):
    action: str
    note: str = ""
    input_content: str | None = None
    reference_answer: str | None = None
    recheck: bool = True


def _rules_payload(rule_rows) -> list[dict]:
    return [
        {
            "code": r.code,
            "name": r.name,
            "category": r.category,
            "severity": r.severity,
            "description": r.description,
            "config": loads(r.config_json, {}),
            "enabled": bool(r.enabled),
        }
        for r in rule_rows
    ]


async def _execute_quality_check(
    db: AsyncSession,
    d: Dataset,
    *,
    version_id: int | None,
    user_id: int | None,
) -> dict:
    vid = version_id or d.current_version_id
    if not vid:
        raise HTTPException(400, "请先导入数据")
    d.quality_status = "checking"
    items = (await db.execute(
        select(DatasetItem).where(DatasetItem.version_id == vid, DatasetItem.status != "deleted").order_by(DatasetItem.item_no)
    )).scalars().all()
    payload = [
        {
            "id": x.id,
            "item_no": x.item_no,
            "input_content": x.input_content,
            "reference_answer": x.reference_answer,
        }
        for x in items
    ]
    rule_rows = (await db.execute(select(QualityRule))).scalars().all()
    rules = _rules_payload(rule_rows) or None
    try:
        result = check_items(payload, rules)
    except Exception as exc:
        d.quality_status = "check_failed"
        raise HTTPException(500, f"检测失败：{exc}") from exc
    flags = result.pop("flags")
    issue_records = result.pop("issue_records", [])
    for item, flag in zip(items, flags):
        item.quality_flag = flag
    ver = await db.get(DatasetVersion, vid)
    if ver:
        ver.quality_score = result["score"]
        ver.quality_status = result["status"]
    d.quality_status = result["status"]
    report = QualityReport(
        dataset_id=d.id,
        version_id=vid,
        status=result["status"],
        score=result["score"],
        report_json=dumps(result),
        issue_count=len(issue_records),
        creator_id=user_id,
    )
    db.add(report)
    await db.flush()
    dest = Path(settings.UPLOAD_DIR) / "quality"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"report-{report.id}.json"
    path.write_text(dumps({**result, "issue_records": issue_records}), encoding="utf-8")
    report.report_path = str(path)
    for rec in issue_records:
        db.add(QualityIssue(
            report_id=report.id,
            dataset_id=d.id,
            version_id=vid,
            item_id=rec.get("item_id"),
            item_no=rec.get("item_no") or 0,
            rule_code=rec.get("rule_code") or "",
            issue_type=rec.get("issue_type") or "",
            severity=rec.get("severity") or "warning",
            description=rec.get("description") or "",
        ))
    await db.flush()
    return {
        "id": report.id,
        "score": result["score"],
        "status": result["status"],
        "issue_count": len(issue_records),
        "report": result,
        "version_id": vid,
    }

def _rule_out(r: QualityRule) -> dict:
    return {
        "id": r.id,
        "code": r.code,
        "name": r.name,
        "category": r.category,
        "description": r.description,
        "severity": r.severity,
        "enabled": bool(r.enabled),
        "config": loads(r.config_json, {}),
        "created_at": iso(r.created_at),
    }


def _issue_out(i: QualityIssue) -> dict:
    return {
        "id": i.id,
        "report_id": i.report_id,
        "dataset_id": i.dataset_id,
        "version_id": i.version_id,
        "item_id": i.item_id,
        "item_no": i.item_no,
        "rule_code": i.rule_code,
        "issue_type": i.issue_type,
        "severity": i.severity,
        "description": i.description,
        "status": i.status,
        "handler": i.handler,
        "handle_note": i.handle_note,
        "created_at": iso(i.created_at),
        "updated_at": iso(i.updated_at),
    }


@router.get("")
async def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=200),
    dataset_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("quality:list")),
):
    q = select(QualityReport)
    if dataset_id:
        q = q.where(QualityReport.dataset_id == dataset_id)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(QualityReport.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "dataset_id": r.dataset_id,
                "version_id": r.version_id,
                "status": r.status,
                "score": r.score,
                "issue_count": r.issue_count,
                "report_path": r.report_path,
                "report": loads(r.report_json, {}),
                "created_at": iso(r.created_at),
            }
            for r in rows
        ],
        "total": total or 0,
    }


@router.get("/rules")
async def list_rules(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("quality:list")),
):
    rows = (await db.execute(select(QualityRule).order_by(QualityRule.id))).scalars().all()
    return [_rule_out(r) for r in rows]


@router.put("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("quality:edit")),
):
    r = await db.get(QualityRule, rule_id)
    if not r:
        raise HTTPException(404, "规则不存在")
    data = body.model_dump(exclude_unset=True)
    if "config" in data:
        r.config_json = dumps(data.pop("config") or {})
    for k, v in data.items():
        setattr(r, k, v)
    return _rule_out(r)


@router.get("/issues")
async def list_issues(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    dataset_id: int | None = None,
    report_id: int | None = None,
    status: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("quality:view")),
):
    q = select(QualityIssue)
    if dataset_id:
        q = q.where(QualityIssue.dataset_id == dataset_id)
    if report_id:
        q = q.where(QualityIssue.report_id == report_id)
    if status:
        q = q.where(QualityIssue.status == status)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = (await db.execute(q.order_by(QualityIssue.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [_issue_out(x) for x in rows], "total": total or 0}


@router.post("/issues/{issue_id}/handle")
async def handle_issue(
    issue_id: int,
    body: IssueHandle,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("quality:edit")),
):
    issue = await db.get(QualityIssue, issue_id)
    if not issue:
        raise HTTPException(404, "问题不存在")
    action = body.action
    if action not in {"fix", "delete", "ignore", "review"}:
        raise HTTPException(400, "action 必须是 fix / delete / ignore / review")
    item = await db.get(DatasetItem, issue.item_id) if issue.item_id else None
    if action == "fix":
        if not item:
            raise HTTPException(400, "找不到对应条目")
        d = await db.get(Dataset, issue.dataset_id)
        if not d:
            raise HTTPException(404, "数据集不存在")
        # 若条目不在当前版本（曾修订），按 item_no 定位当前副本
        if d.current_version_id and item.version_id != d.current_version_id:
            cur = await db.scalar(
                select(DatasetItem).where(
                    DatasetItem.version_id == d.current_version_id,
                    DatasetItem.item_no == item.item_no,
                )
            )
            if not cur:
                raise HTTPException(400, "当前版本找不到对应条目")
            item = cur
        changes = {"quality_flag": "normal"}
        if body.input_content is not None:
            changes["input_content"] = body.input_content
        if body.reference_answer is not None:
            changes["reference_answer"] = body.reference_answer
        new_item = await apply_item_changes(
            db,
            dataset=d,
            source_item_id=item.id,
            changes=changes,
            creator_id=current.id,
            change_desc=f"质检修复 issue#{issue.id}",
        )
        issue.item_id = new_item.id
        issue.status = "fixed"
    elif action == "delete":
        if item:
            d = await db.get(Dataset, issue.dataset_id)
            if not d:
                raise HTTPException(404, "数据集不存在")
            if d.current_version_id and item.version_id != d.current_version_id:
                cur = await db.scalar(
                    select(DatasetItem).where(
                        DatasetItem.version_id == d.current_version_id,
                        DatasetItem.item_no == item.item_no,
                    )
                )
                if cur:
                    item = cur
            new_item = await apply_item_changes(
                db,
                dataset=d,
                source_item_id=item.id,
                changes={"status": "deleted", "quality_flag": "deleted"},
                creator_id=current.id,
                change_desc=f"质检删除 issue#{issue.id}",
            )
            issue.item_id = new_item.id
        issue.status = "deleted"
    elif action == "ignore":
        issue.status = "ignored"
    else:
        issue.status = "review"
    issue.handler = current.username
    issue.handle_note = body.note
    out = {"issue": _issue_out(issue)}
    if body.recheck and action in {"fix", "delete"}:
        d = await db.get(Dataset, issue.dataset_id)
        if d:
            out["recheck"] = await _execute_quality_check(db, d, version_id=d.current_version_id, user_id=current.id)
            out["version_id"] = d.current_version_id
    return out


@router.get("/{report_id}/download")
async def download_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("quality:view")),
):
    r = await db.get(QualityReport, report_id)
    if not r:
        raise HTTPException(404, "报告不存在")
    if r.report_path and Path(r.report_path).exists():
        return FileResponse(r.report_path, filename=f"quality-{report_id}.json", media_type="application/json")
    raise HTTPException(404, "报告文件不存在")


@router.post("/run")
async def run_quality(
    dataset_id: int = Query(...),
    version_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_permission("quality:run")),
):
    d = await db.get(Dataset, dataset_id)
    if not d or d.status == "deleted":
        raise HTTPException(404, "数据集不存在")
    return await _execute_quality_check(db, d, version_id=version_id, user_id=current.id)