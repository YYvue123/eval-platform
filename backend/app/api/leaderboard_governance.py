"""Publication and review gates; no scoring facts are changed here."""
import hashlib
import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_actor
from app.database import get_db
from app.models import EvalTask, LeaderboardPolicy, LeaderboardPublication, LeaderboardReview
from app.services.actor_context import ActorContext
from app.services.audit import log_audit, get_client_ip
from app.services.leaderboard_insights import insights
from app.services.object_policy import get_visible_or_404, apply_object_scope
from app.utils.jsonutil import dumps, loads, iso
from app.models.leaderboard_governance import LeaderboardDemo
from app.services.leaderboard_demo_data import DIMENSIONS, demo_payload
from app.services.leaderboard_insights import apply_scores

router = APIRouter()


@router.post('/demo/seed')
async def seed_demo(request: Request, db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:edit'))):
    added=[]
    for category in DIMENSIONS:
        row=await db.scalar(select(LeaderboardDemo).where(LeaderboardDemo.tenant_id==actor.tenant_id,LeaderboardDemo.category==category))
        if not row:
            db.add(LeaderboardDemo(tenant_id=actor.tenant_id,category=category,payload_json=dumps(demo_payload(category)),creator_id=actor.user_id))
            added.append(category)
    await log_audit(db,'leaderboard','edit',user_id=actor.user_id,username=actor.username,tenant_id=str(actor.tenant_id),ip=get_client_ip(request),detail=dumps({'synthetic_demo_added':added,'formal_results_written':False}))
    await db.commit()
    return {'added':added,'simulation':True}


@router.get('/demo')
async def get_demo(category: str = 'vision', board: str = 'overall', metric: str = '', db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:view'))):
    if board not in {'overall','ability','special','value'}:
        raise HTTPException(400,'榜单类型无效')
    row=await db.scalar(select(LeaderboardDemo).where(LeaderboardDemo.tenant_id==actor.tenant_id,LeaderboardDemo.category==category))
    if not row:
        raise HTTPException(404,'该分类尚未配置模拟展示数据')
    payload=loads(row.payload_json,{})
    demo_rows=(await db.scalars(select(LeaderboardDemo).where(LeaderboardDemo.tenant_id==actor.tenant_id))).all()
    payload['categories']={r.category:len(loads(r.payload_json,{}).get('items',[])) for r in demo_rows}
    payload['overview']={'models':sum(payload['categories'].values()),'runs':0}
    metric=metric if metric in payload['dimensions'] else payload['dimensions'][0]
    weights=apply_scores(payload['items'],payload['dimensions'],{},board,metric,True)
    return {**payload,'board':board,'metric':metric,'weights':weights}


def utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value and value.tzinfo else value


class BoardSelection(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    cohort_id: str = Field(min_length=1, max_length=200)
    board: str = Field(default='overall', pattern='^(overall|ability|special|value)$')
    metric: str = ''
    industry: str = ''
    scene: str = ''
    category: str = ''
    since: datetime | None = None
    as_of: datetime | None = None
    model_ids: list[int] | None = None
    version_id: int | None = None

    def selection(self):
        values = self.model_dump(include=set(BoardSelection.model_fields))
        values['since'], values['as_of'] = utc(self.since), utc(self.as_of)
        if values['since'] and values['as_of'] and values['since'] > values['as_of']:
            raise HTTPException(400, '开始时间不能晚于结束时间')
        return values


class PolicyBody(BaseModel):
    cohort_id: str = Field(min_length=1, max_length=200)
    weights: dict[str, float]


@router.put('/policy')
async def set_policy(body: PolicyBody, request: Request, db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:edit'))):
    payload = await insights(db, actor, cohort_id=body.cohort_id)
    if not payload['items'] or not payload['scale']:
        raise HTTPException(400, '没有完整的已知尺度结果，不能配置综合权重')
    if set(body.weights) != set(payload['dimensions']) or not all(math.isfinite(v) and 0 <= v <= 100 for v in body.weights.values()) or sum(body.weights.values()) <= 0:
        raise HTTPException(400, '权重必须覆盖当前全部维度，非负且总和大于零')
    row = await db.scalar(select(LeaderboardPolicy).where(LeaderboardPolicy.tenant_id == actor.tenant_id, LeaderboardPolicy.cohort_id == body.cohort_id))
    previous = loads(row.weights_json, {}) if row else {}
    if not row:
        row = LeaderboardPolicy(tenant_id=actor.tenant_id, cohort_id=body.cohort_id, updated_by=actor.user_id)
        db.add(row)
    row.weights_json, row.updated_by = dumps(body.weights), actor.user_id
    await log_audit(db,'leaderboard','edit',user_id=actor.user_id,username=actor.username,tenant_id=str(actor.tenant_id),ip=get_client_ip(request),detail=dumps({'cohort_id':body.cohort_id,'before':previous,'after':body.weights}))
    await db.commit()
    return {'weights':body.weights}


class PublishBody(BoardSelection):
    title: str = Field(min_length=2, max_length=120)
    public: bool = False


def publication_info(row):
    return {'id':row.id,'title':row.title,'cohort_id':row.cohort_id,'board':row.board,'status':row.status,
            'created_at':iso(row.created_at),'withdrawn_at':iso(row.withdrawn_at),'withdrawal_reason':row.withdrawal_reason,
            'public_path':f'/leaderboard/public/{row.public_token}' if row.public_token and row.status=='published' else None,
            'checksum':hashlib.sha256(row.payload_json.encode()).hexdigest()}


@router.get('/publications')
async def list_publications(cohort_id: str = '', board: str = '', db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:view'))):
    query = select(LeaderboardPublication).where(LeaderboardPublication.tenant_id == actor.tenant_id)
    if cohort_id:
        query = query.where(LeaderboardPublication.cohort_id == cohort_id)
    if board:
        query = query.where(LeaderboardPublication.board == board)
    return {'items':[publication_info(r) for r in (await db.scalars(query.order_by(LeaderboardPublication.id.desc()))).all()]}


@router.post('/publications')
async def publish(body: PublishBody, request: Request, db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:publish'))):
    payload = await insights(db, actor, **body.selection())
    if not payload['items'] or not any(r['rank'] is not None for r in payload['items']):
        raise HTTPException(400, '没有可排名的完整实测结果，不能发布')
    if payload['pending_review_total']:
        raise HTTPException(409, '该比较组有待复核数据，请先完成复核')
    row = LeaderboardPublication(tenant_id=actor.tenant_id,cohort_id=body.cohort_id,board=body.board,title=body.title.strip(),
        payload_json=dumps(payload),creator_id=actor.user_id,public_token=uuid.uuid4().hex if body.public else None)
    db.add(row)
    await db.flush()
    await log_audit(db,'leaderboard','publish',user_id=actor.user_id,username=actor.username,tenant_id=str(actor.tenant_id),target_id=row.id,ip=get_client_ip(request),detail=dumps({'title':row.title,'cohort_id':row.cohort_id,'public':body.public,'checksum':hashlib.sha256(row.payload_json.encode()).hexdigest()}))
    await db.commit()
    return publication_info(row)


@router.get('/publications/{publication_id}')
async def get_publication(publication_id: int, db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:view'))):
    row = await db.get(LeaderboardPublication, publication_id)
    if not row or row.tenant_id != actor.tenant_id:
        raise HTTPException(404,'发布记录不存在')
    if row.status != 'published' and not actor.has_permission('leaderboard:publish'):
        raise HTTPException(410,'该期榜单已撤回')
    return {**publication_info(row),'payload':loads(row.payload_json,{})}


class ReasonBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    reason: str = Field(min_length=4, max_length=500)


@router.post('/publications/{publication_id}/withdraw')
async def withdraw(publication_id: int, body: ReasonBody, request: Request, db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:withdraw'))):
    row = await db.get(LeaderboardPublication,publication_id)
    if not row or row.tenant_id != actor.tenant_id:
        raise HTTPException(404,'发布记录不存在')
    if row.status != 'published':
        raise HTTPException(409,'该期榜单已经撤回')
    row.status, row.withdrawal_reason, row.withdrawn_at = 'withdrawn', body.reason.strip(), datetime.utcnow()
    await log_audit(db,'leaderboard','withdraw',user_id=actor.user_id,username=actor.username,tenant_id=str(actor.tenant_id),target_id=row.id,ip=get_client_ip(request),detail=body.reason)
    await db.commit()
    return publication_info(row)


@router.get('/public/{token}')
async def public_publication(token: str, response: Response, db: AsyncSession = Depends(get_db)):
    response.headers['Cache-Control'] = 'no-store'
    row = await db.scalar(select(LeaderboardPublication).where(LeaderboardPublication.public_token == token))
    if not row:
        raise HTTPException(404,'公开榜单不存在')
    if row.status != 'published':
        raise HTTPException(410,'该榜单已撤回，停止公开展示')
    saved = loads(row.payload_json,{})
    fields = {'key','model_name','version','parameter_scale','company','source_type','modal','demo_alias','score','raw_score','ranking_score','rank','dimensions','sample_count','pass_rate','latency_ms','p95_latency_ms','cost','cost_per_sample','value_score','updated_at'}
    # Only aggregate fields selected by an authorized publisher; no prompts, task IDs or credentials.
    return {'title':row.title,'created_at':iso(row.created_at),'board':row.board,'metric':saved.get('metric'),
            'items':[{k:v for k,v in item.items() if k in fields} for item in saved.get('items',[])],
            'dimensions':saved.get('dimensions',[]),'scale':saved.get('scale'),'weights':saved.get('weights',{}),
            'history':[{'key':p['key'],'score':p['score'],'at':p['at']} for p in saved.get('history',[])],
            'rules':saved.get('rules'),'status':'published'}


class ReportBody(ReasonBody):
    task_id: int


@router.get('/reviews')
async def list_reviews(db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:review'))):
    visible = apply_object_scope(select(EvalTask.id),EvalTask,actor)
    rows = (await db.scalars(select(LeaderboardReview).where(LeaderboardReview.tenant_id==actor.tenant_id,LeaderboardReview.task_id.in_(visible)).order_by(LeaderboardReview.id.desc()))).all()
    return {'items':[{'id':r.id,'task_id':r.task_id,'status':r.status,'reason':r.reason,'decision_note':r.decision_note,'created_at':iso(r.created_at),'resolved_at':iso(r.resolved_at)} for r in rows]}


@router.post('/reviews')
async def report(body: ReportBody, request: Request, db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:review'))):
    await get_visible_or_404(db,EvalTask,body.task_id,actor)
    row = await db.scalar(select(LeaderboardReview).where(LeaderboardReview.tenant_id==actor.tenant_id,LeaderboardReview.task_id==body.task_id))
    if row and row.status=='pending':
        raise HTTPException(409,'该任务已在复核中')
    if not row:
        row=LeaderboardReview(tenant_id=actor.tenant_id,task_id=body.task_id,reporter_id=actor.user_id,reason=body.reason.strip())
        db.add(row)
    else:
        row.status,row.reason,row.reporter_id,row.reviewer_id,row.decision_note,row.resolved_at='pending',body.reason.strip(),actor.user_id,None,'',None
    await db.flush()
    # A flagged source is removed from live rankings and any affected published views are withdrawn.
    affected=[]
    for publication in (await db.scalars(select(LeaderboardPublication).where(LeaderboardPublication.tenant_id==actor.tenant_id,LeaderboardPublication.status=='published'))).all():
        payload=loads(publication.payload_json,{})
        if any(r.get('task_id')==body.task_id for r in payload.get('items',[])) or any(r.get('task_id')==body.task_id for r in payload.get('history',[])):
            publication.status,publication.withdrawn_at,publication.withdrawal_reason='withdrawn',datetime.utcnow(),f'来源任务 #{body.task_id} 待复核：{body.reason.strip()}'
            affected.append(publication.id)
    await log_audit(db,'leaderboard','review',user_id=actor.user_id,username=actor.username,tenant_id=str(actor.tenant_id),target_id=row.id,ip=get_client_ip(request),detail=dumps({'task_id':body.task_id,'reason':body.reason,'withdrawn_publications':affected}))
    await db.commit()
    return {'id':row.id,'status':row.status,'withdrawn_publications':affected}


class DecisionBody(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    decision: str = Field(pattern='^(cleared|excluded)$')
    note: str = Field(min_length=4,max_length=500)


@router.post('/reviews/{review_id}/resolve')
async def resolve(review_id: int, body: DecisionBody, request: Request, db: AsyncSession = Depends(get_db), actor: ActorContext = Depends(require_actor('leaderboard:review'))):
    row=await db.get(LeaderboardReview,review_id)
    if not row or row.tenant_id!=actor.tenant_id:
        raise HTTPException(404,'复核记录不存在')
    await get_visible_or_404(db,EvalTask,row.task_id,actor)
    if row.status!='pending':
        raise HTTPException(409,'该记录已完成复核')
    row.status,row.decision_note,row.reviewer_id,row.resolved_at=body.decision,body.note.strip(),actor.user_id,datetime.utcnow()
    await log_audit(db,'leaderboard','review',user_id=actor.user_id,username=actor.username,tenant_id=str(actor.tenant_id),target_id=row.id,ip=get_client_ip(request),detail=dumps({'decision':body.decision,'note':body.note,'task_id':row.task_id}))
    await db.commit()
    return {'id':row.id,'status':row.status}
