"""Governance regressions. All fixtures are synthetic and confined to isolated_env."""
from tests import isolated_env  # noqa: F401
import asyncio
import unittest
import uuid
from datetime import datetime
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from app.models.leaderboard_governance import LeaderboardPolicy, LeaderboardPublication, LeaderboardReview
from app.database import async_session
from app.main import app
from app.models import Dataset, DatasetVersion, DatasetItem, EvalModel, ModelMeta, EvalTask, EvalResult, User, AuditLog
from app.services.leaderboard import cohort_id_of
from app.services.leaderboard_insights import apply_scores
from app.utils.auth import create_access_token, get_password_hash


class ScorePolicyTests(unittest.TestCase):
    def test_weights_change_order_without_changing_raw_dimensions(self):
        rows=[{'key':'a','score':.5,'cost':.02,'sample_count':2,'dimensions':{'知识':{'score':1},'推理':{'score':0}}},
              {'key':'b','score':.5,'cost':None,'sample_count':2,'dimensions':{'知识':{'score':0},'推理':{'score':1}}}]
        apply_scores(rows,['知识','推理'],{'知识':1,'推理':3},'overall','',True)
        self.assertEqual(rows[0]['key'],'b')
        self.assertEqual(rows[0]['score'],.75)
        self.assertEqual(rows[1]['dimensions']['知识']['score'],1)
        apply_scores(rows,['知识','推理'],{},'ability','知识',True)
        self.assertEqual(rows[0]['key'],'a')
        apply_scores(rows,['知识','推理'],{},'value','',True)
        self.assertEqual(rows[0]['key'],'a')
        self.assertIsNone(rows[1]['rank'])
        apply_scores(rows,['知识','推理'],{},'overall','',False)
        self.assertTrue(all(r['rank'] is None for r in rows))


class GovernanceApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context=TestClient(app)
        cls.client=cls.context.__enter__()
        response=cls.client.post('/api/auth/login',json={'username':'admin','password':'admin123'})
        cls.headers={'Authorization':'Bearer '+response.json()['access_token']}

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None,None,None)

    def setUp(self):
        async def fixtures():
            async with async_session() as db:
                admin=await db.scalar(select(User).where(User.username=='admin'))
                suffix=uuid.uuid4().hex[:8]
                ds=Dataset(name='isolated-governance-'+suffix,status='published',tenant_id=admin.tenant_id,creator_id=admin.id)
                db.add(ds);await db.flush()
                version=DatasetVersion(dataset_id=ds.id,version_code='fixture')
                db.add(version);await db.flush()
                samples=[]
                for i,label in enumerate(['知识','推理','代码']):
                    item=DatasetItem(dataset_id=ds.id,version_id=version.id,item_no=i+1,data_label=label)
                    db.add(item);samples.append(item)
                await db.flush()
                tasks=[]
                for name,scores in [('A',[.9,.2,.4]),('B',[.4,.9,.5])]:
                    model=EvalModel(name=f'fixture-{name}-{suffix}',tenant_id=admin.tenant_id,creator_id=admin.id)
                    db.add(model);await db.flush()
                    task=EvalTask(name='isolated scoring fixture',model_id=model.id,dataset_id=ds.id,dataset_version_id=version.id,
                        tenant_id=admin.tenant_id,creator_id=admin.id,status='success',total=3,finished_at=datetime.utcnow(),
                        scene='chat',industry='general',judge_resource_id='builtin/fuzzy',tool_version='1',avg_score=sum(scores)/3,tokens_used=100)
                    db.add(task);await db.flush()
                    for item,score in zip(samples,scores):db.add(EvalResult(task_id=task.id,item_id=item.id,item_no=item.item_no,score=score,passed=score>=.6,execution_status='ok',score_status='scored',simulation=False,latency_ms=200))
                    tasks.append(task)
                other=User(username='other-'+suffix,password_hash=get_password_hash('fixture-only'),role='admin',tenant_id=999991)
                viewer=User(username='viewer-'+suffix,password_hash=get_password_hash('fixture-only'),role='viewer',tenant_id=admin.tenant_id)
                db.add_all([other,viewer]);await db.commit()
                return cohort_id_of(tasks[0]),[t.id for t in tasks],other.username,viewer.username,ds.id,[t.model_id for t in tasks]
        self.cid,self.tasks,other,viewer,self.dataset_id,self.model_ids=asyncio.run(fixtures())
        self.fixture_users=[other,viewer]
        self.other={'Authorization':'Bearer '+create_access_token({'sub':other})}
        self.viewer={'Authorization':'Bearer '+create_access_token({'sub':viewer})}

    def tearDown(self):
        async def cleanup():
            async with async_session() as db:
                for model, condition in [
                    (LeaderboardPublication,LeaderboardPublication.cohort_id==self.cid),
                    (LeaderboardPolicy,LeaderboardPolicy.cohort_id==self.cid),
                    (LeaderboardReview,LeaderboardReview.task_id.in_(self.tasks)),
                    (EvalResult,EvalResult.task_id.in_(self.tasks)),
                    (EvalTask,EvalTask.id.in_(self.tasks)),
                    (DatasetItem,DatasetItem.dataset_id==self.dataset_id),
                    (DatasetVersion,DatasetVersion.dataset_id==self.dataset_id),
                    (Dataset,Dataset.id==self.dataset_id),
                    (ModelMeta,ModelMeta.model_id.in_(self.model_ids)),
                    (EvalModel,EvalModel.id.in_(self.model_ids)),
                    (User,User.username.in_(self.fixture_users)),
                ]:
                    await db.execute(delete(model).where(condition))
                await db.commit()
        asyncio.run(cleanup())

    def test_publication_immutable_review_withdraws_and_restore_does_not_republish(self):
        c=self.client;h=self.headers
        policy={'cohort_id':self.cid,'weights':{'知识':1,'推理':1,'代码':1}}
        self.assertEqual(c.put('/api/leaderboard/policy',headers=h,json=policy).status_code,200)
        release=c.post('/api/leaderboard/publications',headers=h,json={'cohort_id':self.cid,'title':'Isolated public fixture','public':True}).json()
        self.assertIn('id',release,release)
        rid=release['id'];token=release['public_path'].split('/')[-1]
        frozen=c.get(f'/api/leaderboard/publications/{rid}',headers=h).json()
        public=c.get('/api/leaderboard/public/'+token).json()
        self.assertNotIn('task_id',public['items'][0])
        self.assertNotIn('description',public['items'][0])
        self.assertEqual(c.get(f'/api/leaderboard/publications/{rid}',headers=self.other).status_code,404)
        self.assertEqual(c.post('/api/leaderboard/publications',headers=self.viewer,json={'cohort_id':self.cid,'title':'Forbidden'}).status_code,403)
        policy['weights']['推理']=9
        self.assertEqual(c.put('/api/leaderboard/policy',headers=h,json=policy).status_code,200)
        self.assertEqual(c.get(f'/api/leaderboard/publications/{rid}',headers=h).json()['checksum'],frozen['checksum'])
        review=c.post('/api/leaderboard/reviews',headers=h,json={'task_id':self.tasks[0],'reason':'isolated review evidence'}).json()
        self.assertIn(rid,review['withdrawn_publications'])
        self.assertEqual(c.get('/api/leaderboard/public/'+token).status_code,410)
        live=c.get('/api/leaderboard/insights',headers=h,params={'cohort_id':self.cid}).json()
        self.assertEqual(len(live['items']),1)
        self.assertEqual(live['pending_review_total'],1)
        self.assertEqual(c.post('/api/leaderboard/publications',headers=h,json={'cohort_id':self.cid,'title':'Blocked'}).status_code,409)
        self.assertEqual(c.post(f"/api/leaderboard/reviews/{review['id']}/resolve",headers=h,json={'decision':'cleared','note':'verified isolated fixture'}).status_code,200)
        self.assertEqual(len(c.get('/api/leaderboard/insights',headers=h,params={'cohort_id':self.cid}).json()['items']),2)
        self.assertEqual(c.get('/api/leaderboard/public/'+token).status_code,410)
        self.assertEqual(c.get(f'/api/leaderboard/publications/{rid}',headers=h).json()['checksum'],frozen['checksum'])
        async def audit_and_score():
            async with async_session() as db:
                scores=list((await db.scalars(select(EvalResult.score).where(EvalResult.task_id==self.tasks[0]).order_by(EvalResult.item_no))).all())
                actions=list((await db.scalars(select(AuditLog.action).where(AuditLog.resource=='leaderboard',AuditLog.target_id==review['id'],AuditLog.action=='review'))).all())
                return scores,actions
        scores,actions=asyncio.run(audit_and_score())
        self.assertEqual(scores,[.9,.2,.4]);self.assertGreaterEqual(len(actions),2)

    def test_policy_validation_and_cross_tenant_review(self):
        c=self.client;h=self.headers
        for weights in [{'知识':1},{'知识':0,'推理':0,'代码':0},{'知识':-1,'推理':1,'代码':1}]:
            self.assertEqual(c.put('/api/leaderboard/policy',headers=h,json={'cohort_id':self.cid,'weights':weights}).status_code,400)
        self.assertEqual(c.post('/api/leaderboard/reviews',headers=self.other,json={'task_id':self.tasks[0],'reason':'not authorized source'}).status_code,404)
        params={'cohort_id':self.cid,'board':'special'}
        self.assertEqual(c.get('/api/leaderboard/insights',headers=h,params=params).json()['items'],[])
        params={'cohort_id':self.cid,'board':'ability','metric':'代码'}
        result=c.get('/api/leaderboard/insights',headers=h,params=params).json()
        self.assertEqual(result['items'][0]['ranking_score'],.5)
        self.assertEqual(c.get('/api/leaderboard/insights',headers=h,params={'cohort_id':self.cid,'model_ids':'invalid'}).status_code,400)

    def test_single_ability_limits_top_ten_and_model_filters(self):
        async def add_candidates():
            async with async_session() as db:
                source=await db.get(EvalTask,self.tasks[0])
                results=(await db.scalars(select(EvalResult).where(EvalResult.task_id==source.id))).all()
                for i in range(10):
                    model=EvalModel(name=f'isolated-extra-{uuid.uuid4().hex}',tenant_id=source.tenant_id,creator_id=source.creator_id)
                    db.add(model);await db.flush();self.model_ids.append(model.id)
                    task=EvalTask(name='isolated top10 fixture',model_id=model.id,dataset_id=source.dataset_id,dataset_version_id=source.dataset_version_id,
                        tenant_id=source.tenant_id,creator_id=source.creator_id,status='success',total=3,finished_at=datetime.utcnow(),
                        scene=source.scene,industry=source.industry,judge_resource_id=source.judge_resource_id,tool_version=source.tool_version,avg_score=.1+i*.05)
                    db.add(task);await db.flush();self.tasks.append(task.id)
                    for result in results:
                        db.add(EvalResult(task_id=task.id,item_id=result.item_id,item_no=result.item_no,score=.1+i*.05,passed=False,execution_status='ok',score_status='scored',simulation=False,latency_ms=200))
                await db.commit()
        asyncio.run(add_candidates())
        result=self.client.get('/api/leaderboard/insights',headers=self.headers,params={'cohort_id':self.cid,'board':'ability','metric':'代码'}).json()
        self.assertEqual(len(result['items']),10)
        scores=[r['ranking_score'] for r in result['items']]
        self.assertEqual(scores,sorted(scores,reverse=True))
        filtered=self.client.get('/api/leaderboard/insights',headers=self.headers,params={'cohort_id':self.cid,'model_ids':str(self.model_ids[0])}).json()
        self.assertEqual([r['model_id'] for r in filtered['items']],[self.model_ids[0]])

    def test_source_metadata_and_task_resource_labels(self):
        c=self.client;h=self.headers
        for model_id,source in zip(self.model_ids,['open_source','closed']):
            self.assertEqual(c.put(f'/api/models/{model_id}',headers=h,json={'source_type':source}).status_code,200)
        models=c.get('/api/models',headers=h,params={'page_size':200}).json()['items']
        self.assertEqual(next(m for m in models if m['id']==self.model_ids[0])['source_type'],'open_source')
        board=c.get('/api/leaderboard/insights',headers=h,params={'cohort_id':self.cid}).json()
        self.assertEqual({r['source_type'] for r in board['items']},{'open','closed'})
        self.assertEqual(board['cohorts'][0]['judge_name'],'文本相似度')
        task=c.get(f'/api/tasks/{self.tasks[0]}',headers=h).json()
        self.assertEqual(task['judge_name'],'文本相似度')
        self.assertTrue(task['model_name'].startswith('fixture-A'))
        self.assertTrue(task['dataset_name'].startswith('isolated-governance-'))
        row=next(t for t in c.get('/api/tasks',headers=h,params={'page_size':200}).json()['items'] if t['id']==self.tasks[0])
        self.assertEqual(row['model_name'],task['model_name'])

    def test_synthetic_endpoints_are_removed_and_real_results_remain(self):
        c=self.client;h=self.headers
        self.assertEqual(c.post('/api/leaderboard/demo/seed',headers=h).status_code,404)
        self.assertEqual(c.get('/api/leaderboard/demo',headers=h).status_code,404)
        self.assertEqual(len(c.get('/api/leaderboard/insights',headers=h,params={'cohort_id':self.cid}).json()['items']),2)
