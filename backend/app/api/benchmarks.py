"""基准套件 API：注册表、readiness、金标包、模拟器、MUT 策略。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.database import get_db
from app.models import BenchmarkSuite, User
from app.services import benchmark_packs as packs
from app.services import benchmark_registry as reg
from app.services import media_adapter
from app.services import scenario_simulators as sims
from app.utils.jsonutil import dumps, iso, loads

router = APIRouter()


def _row_to_suite_dict(row: BenchmarkSuite) -> dict:
    cfg = loads(row.config_json, {})
    return {
        "code": row.code,
        "name": row.name,
        "category": row.category,
        "template_code": row.template_code,
        "input_modality": row.input_modality,
        "oracle_type": row.oracle_type,
        "license": row.license,
        "calibration_report": row.calibration_report,
        "metrics": loads(row.metrics_json, []),
        "has_real_inputs": bool(cfg.get("has_real_inputs")),
        "has_oracle": bool(cfg.get("has_oracle")),
        "code_host_exec": bool(cfg.get("code_host_exec")),
        "mut_isolated": bool(cfg.get("mut_isolated", True)),
        "string_only_media": bool(cfg.get("string_only_media")),
        "readiness_target": cfg.get("readiness_target") or "draft",
    }


def _suite_out(row: BenchmarkSuite) -> dict:
    suite = _row_to_suite_dict(row)
    readiness = reg.compute_readiness(suite)
    view = reg.suite_public_view(suite, readiness)
    view.update({
        "id": row.id,
        "persisted_readiness": row.readiness,
        "status": row.status,
        "updated_at": iso(row.updated_at),
        "has_pack": suite["code"] in packs.PACK_INDEX,
    })
    return view


async def sync_benchmark_suites(db: AsyncSession) -> int:
    """从注册表同步套件；始终刷新门禁字段。"""
    n = 0
    for spec in reg.default_suites():
        row = await db.scalar(select(BenchmarkSuite).where(BenchmarkSuite.code == spec["code"]))
        cfg = {
            "has_real_inputs": spec.get("has_real_inputs"),
            "has_oracle": spec.get("has_oracle"),
            "code_host_exec": spec.get("code_host_exec"),
            "mut_isolated": spec.get("mut_isolated", True),
            "string_only_media": spec.get("string_only_media"),
            "readiness_target": spec.get("readiness_target") or "draft",
        }
        readiness = reg.compute_readiness(spec)
        if not row:
            db.add(BenchmarkSuite(
                code=spec["code"],
                name=spec["name"],
                category=spec.get("category") or "text",
                template_code=spec.get("template_code") or "",
                input_modality=spec.get("input_modality") or "text",
                oracle_type=spec.get("oracle_type") or "reference",
                license=spec.get("license") or "",
                calibration_report=spec.get("calibration_report") or "",
                metrics_json=dumps(spec.get("metrics") or []),
                config_json=dumps(cfg),
                readiness=readiness["status"],
                blockers_json=dumps(readiness["blockers"]),
            ))
            n += 1
        else:
            row.name = spec["name"]
            row.category = spec.get("category") or row.category
            row.template_code = spec.get("template_code") or row.template_code
            row.input_modality = spec.get("input_modality") or row.input_modality
            row.oracle_type = spec.get("oracle_type") or row.oracle_type
            row.license = spec.get("license") or row.license
            row.calibration_report = spec.get("calibration_report") or row.calibration_report
            row.metrics_json = dumps(spec.get("metrics") or [])
            row.config_json = dumps(cfg)
            row.readiness = readiness["status"]
            row.blockers_json = dumps(readiness["blockers"])
            n += 1
    await db.flush()
    return n


@router.get("")
async def list_benchmarks(
    category: str = Query(""),
    readiness: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:list")),
):
    await sync_benchmark_suites(db)
    q = select(BenchmarkSuite).where(BenchmarkSuite.status == "active")
    if category:
        q = q.where(BenchmarkSuite.category == category)
    if readiness:
        q = q.where(BenchmarkSuite.readiness == readiness)
    rows = (await db.execute(q.order_by(BenchmarkSuite.category, BenchmarkSuite.code))).scalars().all()
    return {"items": [_suite_out(r) for r in rows], "total": len(rows)}


@router.get("/metrics")
async def list_metrics(_: User = Depends(require_permission("task:list"))):
    return {"items": [reg.metric_out(c) for c in reg.METRIC_REGISTRY], "total": len(reg.METRIC_REGISTRY)}


@router.get("/packs")
async def list_packs(_: User = Depends(require_permission("task:list"))):
    return {"items": packs.list_available_packs(), "total": len(packs.PACK_INDEX)}


@router.get("/packs/{code}")
async def get_pack(code: str, _: User = Depends(require_permission("task:view"))):
    try:
        return packs.pack_summary(code)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/simulators")
async def list_simulators(_: User = Depends(require_permission("task:list"))):
    return {"items": sims.list_simulators(), "total": len(sims.SIMULATOR_CODES)}


class SimulateIn(BaseModel):
    simulator: str
    suite_code: str
    sample_id: str | None = None
    candidate: str | None = None
    actions: list[dict] | None = None


@router.post("/simulate")
async def simulate(
    body: SimulateIn,
    _: User = Depends(require_permission("task:view")),
):
    try:
        return sims.run_simulator(
            body.simulator,
            body.suite_code,
            body.sample_id,
            candidate=body.candidate,
            actions=body.actions,
        )
    except sims.HostExecutionForbidden as exc:
        raise HTTPException(400, str(exc)) from exc
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc

@router.get("/{code}")
async def get_benchmark(
    code: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:view")),
):
    await sync_benchmark_suites(db)
    row = await db.scalar(select(BenchmarkSuite).where(BenchmarkSuite.code == code))
    if not row:
        raise HTTPException(404, "基准套件不存在")
    out = _suite_out(row)
    if code in packs.PACK_INDEX:
        try:
            out["pack"] = packs.pack_summary(code)
        except (FileNotFoundError, ValueError):
            out["pack"] = None
    return out


class MutToolCheck(BaseModel):
    tool_name: str


@router.post("/mut/check-tool")
async def mut_check_tool(
    body: MutToolCheck,
    _: User = Depends(require_permission("task:view")),
):
    try:
        reg.assert_mut_tool_allowed(body.tool_name)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"ok": True, "tool_name": body.tool_name}


class SampleValidate(BaseModel):
    modality: str = "text"
    sample: dict = Field(default_factory=dict)


@router.post("/validate-sample")
async def validate_sample(
    body: SampleValidate,
    _: User = Depends(require_permission("task:view")),
):
    errors = reg.validate_sample_against_schema(body.modality, body.sample or {})
    if body.modality == "media":
        errors = list(dict.fromkeys(errors + media_adapter.validate_media_sample(body.sample or {})))
    return {"ok": not errors, "errors": errors}


class MarkReadyIn(BaseModel):
    force: bool = False


@router.post("/{code}/mark-ready")
async def mark_ready(
    code: str,
    body: MarkReadyIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("task:edit")),
):
    await sync_benchmark_suites(db)
    row = await db.scalar(select(BenchmarkSuite).where(BenchmarkSuite.code == code))
    if not row:
        raise HTTPException(404, "基准套件不存在")
    suite = _row_to_suite_dict(row)
    readiness = reg.compute_readiness(suite)
    if readiness["blockers"] and not body.force:
        raise HTTPException(400, "门禁未通过：" + "；".join(readiness["blockers"]))
    if readiness["blockers"] and body.force:
        raise HTTPException(400, "禁止强制绕过 blockers 宣布 ready")
    row.readiness = "ready"
    row.blockers_json = dumps([])
    cfg = loads(row.config_json, {})
    cfg["readiness_target"] = "ready"
    row.config_json = dumps(cfg)
    await db.flush()
    return _suite_out(row)
