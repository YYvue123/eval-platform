"""安全可信评测 API：四类裁判、校准、自适应、专家复核、候选双验证。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import require_permission
from app.models import User
from app.services import safety_eval as se

router = APIRouter()


@router.get("/categories")
async def list_categories(_: User = Depends(require_permission("task:list"))):
    return {"items": se.list_categories(), "total": 4}


@router.get("/sets/{category}")
async def get_set(
    category: str,
    set_type: str = Query("fixed", pattern="^(fixed|explore)$"),
    _: User = Depends(require_permission("task:view")),
):
    try:
        data = se.load_set(category, set_type)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "category": category,
        "set_type": set_type,
        "rule_version": data.get("rule_version"),
        "formal_comparable": set_type == "fixed",
        "sample_count": len(data.get("samples") or []),
        "samples": data.get("samples") or [],
        "no_legal_conclusion": bool(data.get("no_legal_conclusion")),
    }


class ScoreIn(BaseModel):
    category: str
    sample_id: str
    prediction: str = ""
    set_type: str = "fixed"
    predictions_by_perspective: dict | None = None


@router.post("/score")
async def score_sample(body: ScoreIn, _: User = Depends(require_permission("task:view"))):
    try:
        return se.score_sample(
            body.category,
            body.sample_id,
            body.prediction,
            set_type=body.set_type,
            predictions_by_perspective=body.predictions_by_perspective,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


class AdaptiveIn(BaseModel):
    category: str = "risk"
    sample_id: str | None = None
    history: list[dict] = Field(default_factory=list)


@router.post("/adaptive/next")
async def adaptive_next(body: AdaptiveIn, _: User = Depends(require_permission("task:view"))):
    sample = None
    if body.sample_id:
        try:
            data = se.load_set(body.category, "fixed")
            sample = next((s for s in data["samples"] if s.get("id") == body.sample_id), None)
        except FileNotFoundError:
            sample = None
    return se.adaptive_next_prompt(body.category, body.history, sample)


@router.post("/calibrate")
async def calibrate_all(_: User = Depends(require_permission("task:edit"))):
    return se.calibrate_all()


@router.post("/calibrate/{category}")
async def calibrate_one(
    category: str,
    rule_version: str | None = None,
    _: User = Depends(require_permission("task:edit")),
):
    return se.calibrate_category(category, rule_version=rule_version)


@router.get("/reviews")
async def list_reviews(
    status: str = Query(""),
    _: User = Depends(require_permission("task:list")),
):
    rows = se.list_reviews(status=status)
    return {"items": rows, "total": len(rows)}


class ReviewIn(BaseModel):
    category: str
    sample_id: str
    prediction: str = ""
    note: str = ""


@router.post("/reviews")
async def create_review(body: ReviewIn, _: User = Depends(require_permission("task:edit"))):
    return se.enqueue_review(body.model_dump())


class ResolveIn(BaseModel):
    expert_label: str
    note: str = ""


@router.post("/reviews/{review_id}/resolve")
async def resolve_review(
    review_id: str,
    body: ResolveIn,
    _: User = Depends(require_permission("task:edit")),
):
    try:
        return se.resolve_review(review_id, body.expert_label, body.note)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/candidates")
async def list_candidates(_: User = Depends(require_permission("task:list"))):
    rows = se.list_candidate_bank()
    return {"items": rows, "total": len(rows)}


@router.post("/candidates/{candidate_id}/validate")
async def validate_candidate(
    candidate_id: str,
    _: User = Depends(require_permission("task:edit")),
):
    try:
        return se.validate_candidate(candidate_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
