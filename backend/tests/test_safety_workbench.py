"""Isolated protocol regression. Scripted outputs are never development measurements."""
from tests import isolated_env  # noqa: F401

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import json
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import app

from app.database import async_session, init_db
from app.models import EvalResult, EvalTask, SafetyRecord, User
from app.services.actor_context import ActorContext
from app.services.safety_benchmark import benchmark_template
from app.services.safety_protocol import SafetyConfig, DIMENSIONS, rule_score, summarize, next_probe, evidence_hash, validate_sample, aggregate_scores
from app.services.safety_assessments import measurement_scope
from app.services.safety_execution import evaluate_sample
from app.services.leaderboard import cohort_id_of
from app.api.safety_workbench import assessment_payload, review, ReviewBody, calibrate, CalibrationBody, GoldRow, records
from app.utils.jsonutil import dumps


class ProtocolTests(unittest.TestCase):
    def test_numeric_anchors_and_worst_turn_prevent_false_pass(self):
        sample=benchmark_template()['samples'][-1]['safety']
        self.assertFalse(rule_score('100摄氏度',sample)['passed'])
        self.assertTrue(rule_score('0摄氏度',sample)['passed'])
        self.assertTrue(rule_score('0.0摄氏度',sample)['passed'])
        self.assertFalse(rule_score('-10摄氏度',sample)['passed'])
        self.assertEqual(aggregate_scores([1,1,0],'worst'),0)
        self.assertGreater(aggregate_scores([1,1,0],'mean'),.5)
        self.assertEqual(measurement_scope([])['checks'][1]['status'],'未完整测量')
    def test_template_catalog_and_specialized_coverage(self):
        catalog=benchmark_template()['templates']
        self.assertEqual(len(catalog),6)
        for entry in catalog:
            template=benchmark_template(entry['id'])
            self.assertEqual(len(template['samples']),entry['sample_count'])
            self.assertNotIn('开发',template['name'])
            self.assertNotIn('AI编写',template['source'])
            for row in template['samples']:
                dimension=validate_sample(row['safety'])
                if entry['category']!='all':
                    self.assertTrue(dimension.startswith(entry['category']+'.'))
                if entry['id']=='multiturn':
                    self.assertEqual(len(row['safety']['probes']['hard']),2)
        with self.assertRaises(ValueError):
            benchmark_template('unknown')
    def test_all_required_dimensions_and_missing_evidence(self):
        samples = benchmark_template()["samples"]
        self.assertEqual({s["safety"]["dimension"] for s in samples}, set(DIMENSIONS))
        for row in samples:
            self.assertFalse(rule_score("", row["safety"])["passed"])
        with self.assertRaises(ValueError):
            rule_score("0", {"dimension": "hallucination.object", "rubric": "test", "required_any": ["0"]})
        for invalid in [{"required_any": "0"}, {"rubric": " "}, {"probes": {"hard": [""]}}, {"evidence": [{"doc_id": "x", "text": ""}]}]:
            with self.assertRaises(ValueError):
                rule_score("0", {**samples[-1]["safety"], **invalid})

    def test_output_metadata_not_input_metadata(self):
        sample = next(r["safety"] for r in benchmark_template()["samples"] if r["safety"]["dimension"] == "watermark.metadata")
        self.assertFalse(rule_score("检测到AIGC", sample)["passed"])
        self.assertTrue(rule_score(dumps(sample["expected_metadata"]), sample)["passed"])
        wrong_type={**sample['expected_metadata'],'AIGC':1}
        self.assertFalse(rule_score(dumps(wrong_type),sample)['passed'])

    def test_weights_and_null_cells(self):
        for weights in [{"invented": 1}, {"risk.illegal": -1}, {"risk.illegal": float('nan')}, {"risk.illegal": 0}]:
            with self.assertRaises(ValueError):
                SafetyConfig(dimension_weights=weights)
        self.assertIsNone(summarize([], SafetyConfig())["score"])
        self.assertIsNone(summarize([], SafetyConfig())["dimensions"]["hallucination.context"]["score"])

    def test_difficulty_branches_and_bound(self):
        config = SafetyConfig()
        sample = benchmark_template()["samples"][-1]["safety"]
        self.assertEqual(next_probe(sample, 1, 1, config)["difficulty"], "hard")
        self.assertEqual(next_probe(sample, 0, 1, config)["difficulty"], "easy")
        self.assertIsNone(next_probe(sample, 1, 3, config))
        self.assertIsNone(next_probe(sample, 1, 1, SafetyConfig(adaptive=False)))

    def test_judge_configuration_changes_comparison_group(self):
        t = EvalTask(dataset_id=1, model_id=1, scene="chat", metric_weights_json="{}", safety_config_json=dumps(SafetyConfig().model_dump()))
        first = cohort_id_of(t)
        t.safety_config_json = dumps(SafetyConfig(adaptive=False).model_dump())
        self.assertNotEqual(first, cohort_id_of(t))


class WorkbenchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await init_db()

    async def test_agent_safety_permissions_and_missing_protocol_are_blocked(self):
        from app.services.agent_safety import prepare_safety_plan
        with self.assertRaises(ValueError):
            await prepare_safety_plan(None, {'task_type':'security'}, None)
        actor=ActorContext(1,'viewer',1,'viewer','own',{'agent:confirm'},False)
        with self.assertRaises(HTTPException) as caught:
            await prepare_safety_plan(None, {'safety_config':SafetyConfig().model_dump()}, actor)
        self.assertEqual(caught.exception.status_code,403)

    async def test_multiturn_retains_messages_and_judgments(self):
        sample = benchmark_template()["samples"][-1]
        item = SimpleNamespace(extended_content=dumps({"safety":sample["safety"]}), difficulty_level="base")
        task = SimpleNamespace(id=999, model_id=1, safety_config_json=dumps(SafetyConfig().model_dump()), token_quota=100, fencing_token=0)
        db = SimpleNamespace(add=lambda _:None, commit=AsyncMock())
        model = SimpleNamespace(id=1)
        async def judge(db,task,output,sample,config):
            return rule_score(output,sample), 0, False
        mocked = AsyncMock(return_value={"output":"0摄氏度", "tokens":5, "latency_ms":10, "mock":False})
        with patch("app.services.safety_execution.judge_response", side_effect=judge), patch("app.services.safety_execution.invoke_model", mocked):
            result, tokens, latency = await evaluate_sample(db,task,item,model,sample["input"],"0摄氏度",3)
        self.assertEqual(result["metrics"]["turn_count"],2)
        self.assertEqual(tokens,5)
        self.assertEqual(latency,10)
        self.assertEqual(mocked.call_args.kwargs["messages"][1]["role"],"assistant")

    async def test_cultural_contexts_are_independent_and_worst_score_is_retained(self):
        row=next(r for r in benchmark_template()['samples'] if r['safety']['dimension']=='alignment.cross_cultural')
        config=SafetyConfig(adaptive=False,perspective_evaluation=True,turn_aggregation='worst')
        task=SimpleNamespace(id=999,model_id=1,safety_config_json=dumps(config.model_dump()),token_quota=100,fencing_token=0)
        item=SimpleNamespace(extended_content=dumps({'safety':row['safety']}),difficulty_level='base')
        db=SimpleNamespace(add=lambda _:None,commit=AsyncMock())
        async def judge(db,task,output,sample,config):
            return rule_score(output,sample),0,False
        invoked=AsyncMock(side_effect=[{'output':'尊重文化习俗','tokens':3,'latency_ms':4,'mock':False},{'output':'只认可一种文化','tokens':3,'latency_ms':4,'mock':False}])
        with patch('app.services.safety_execution.judge_response',side_effect=judge),patch('app.services.safety_execution.invoke_model',invoked):
            result,tokens,latency=await evaluate_sample(db,task,item,SimpleNamespace(id=1),row['input'],'尊重文化',1)
        self.assertEqual(result['metrics']['perspective_count'],2)
        self.assertEqual(result['score'],0)
        self.assertFalse(result['passed'])
        self.assertEqual(tokens,6)
        self.assertEqual(latency,8)
        self.assertTrue(all('messages' not in call.kwargs for call in invoked.call_args_list))

    async def test_review_persists_without_overwriting_score_and_cross_tenant_denied(self):
        async with async_session() as db:
            actor = ActorContext(910001,"safety-test",910001,"admin","all",{"safety:review","safety:view"},True)
            db.add(User(id=actor.user_id, username="isolated-reviewer", password_hash="fixture", tenant_id=actor.tenant_id))
            await db.flush()
            task = EvalTask(name="isolated-safety",dataset_id=1,model_id=1,task_type="security",status="success",total=2,
                            tenant_id=actor.tenant_id,creator_id=actor.user_id,judge_resource_id='builtin/safety_protocol',safety_config_json=dumps(SafetyConfig().model_dump()))
            db.add(task);await db.flush()
            rows=[]
            for n in [1,2]:
                row=EvalResult(task_id=task.id,item_no=n,score=.5,passed=True,execution_status="ok",score_status="scored",simulation=False,
                               model_output="fixture-only",metrics_json=dumps({"protocol":"safety-protocol-v2","dimension":"alignment.stance_stability","needs_review":True}))
                db.add(row);rows.append(row)
            await db.flush()
            before = await assessment_payload(db,task)
            self.assertFalse(before["leaderboard_eligible"])
            body=ReviewBody(result_id=rows[0].id,evidence_hash=evidence_hash(rows[0]),label="approved",note="isolated fixture review")
            await review(task.id,body,db,actor,None)
            history = await records(task.id, db, actor, None)
            self.assertEqual(history["items"][0]["reviewer_name"], "isolated-reviewer")
            self.assertEqual((await assessment_payload(db,task))["results"][0]["review"]["reviewer_name"], "isolated-reviewer")
            self.assertEqual(rows[0].score,.5)
            self.assertEqual((await assessment_payload(db,task))["pending_reviews"],1)
            from app.services.agent_context import task_evidence
            for label in ('rejected','needs_evidence'):
                await review(task.id,body.model_copy(update={'label':label,'note':'isolated expert decision'}),db,actor,None)
                evidence=await task_evidence(db,SimpleNamespace(task_id=task.id),actor,max_samples=1)
                conclusion=evidence['safety_assessment']
                self.assertFalse(conclusion['leaderboard_eligible'])
                self.assertEqual(len(conclusion['results']),1)
                self.assertEqual(conclusion['results'][0]['review']['label'],label)
                self.assertEqual(rows[0].score,.5)
            previous_hash=conclusion['review_evidence_hash']
            await review(task.id,ReviewBody(result_id=rows[1].id,evidence_hash=evidence_hash(rows[1]),label='approved',note='outside sampled evidence'),db,actor,None)
            refreshed=await task_evidence(db,SimpleNamespace(task_id=task.id),actor,max_samples=1)
            self.assertNotEqual(previous_hash,refreshed['safety_assessment']['review_evidence_hash'])
            with self.assertRaises(HTTPException):
                await review(task.id,body.model_copy(update={"evidence_hash":"stale"}),db,actor,None)
            other=ActorContext(910002,"other",910002,"admin","all",set(),True)
            with self.assertRaises(HTTPException):
                await review(task.id,body,db,other,None)
            gold=[GoldRow(result_id=r.id,evidence_hash=evidence_hash(r),score=0) for r in rows]
            calibration=await calibrate(task.id,CalibrationBody(samples=gold,note="independent fixture labels"),db,actor,None)
            self.assertEqual(calibration["agreement"],0)
            self.assertFalse(calibration["ok"])
            self.assertIsNotNone(await db.get(SafetyRecord,calibration["id"]))
            await db.rollback()


class WorkbenchApiTests(unittest.TestCase):
    def test_agent_safety_plan_approval_and_task_roundtrip(self):
        from app.services.goal_spec import canonical_plan_hash
        with TestClient(app) as client:
            login=client.post('/api/auth/login',json={'username':'admin','password':'admin123'})
            headers={'Authorization':'Bearer '+login.json()['access_token']}
            name='isolated-agent-safety-'+uuid.uuid4().hex[:8]
            ds=client.post('/api/datasets',headers=headers,json={'name':name,'task_type':'chat'}).json()
            imported=client.post(f"/api/datasets/{ds['id']}/import",headers=headers,
                files={'file':('samples.json',json.dumps(benchmark_template()['samples']).encode(),'application/json')})
            self.assertEqual(imported.status_code,200,imported.text)
            model=client.post('/api/models',headers=headers,json={'name':name,'api_url':''}).json()
            session=client.post('/api/agents/sessions',headers=headers,json={'requirement':'安全可信评测','auto_plan':False}).json()
            sid=session['id']
            config=SafetyConfig(turn_aggregation='worst',perspective_evaluation=True).model_dump()
            update={'dataset_id':ds['id'],'model_id':model['id'],'trial_run':True,'token_budget':1000,'safety_config':config}
            proposed=client.post(f'/api/agents/sessions/{sid}/clarify',headers=headers,json=update)
            self.assertEqual(proposed.status_code,200,proposed.text)
            plan=proposed.json()['plan']
            self.assertTrue(plan['ready'],plan)
            self.assertEqual(plan['judge_resource_id'],'builtin/safety_protocol')
            async def tool_proposal():
                from sqlalchemy import select
                from app.models import AgentSession, User
                from app.services.actor_context import build_actor
                from app.services.agent_context import resource_inventory
                from app.services.agent_orchestrator import apply_resource_proposal
                async with async_session() as db:
                    actor=await build_actor(db,await db.scalar(select(User).where(User.username=='admin')))
                    inventory=await resource_inventory(db,actor)
                    baseline=next(row for row in inventory['datasets'] if row['id']==ds['id'])
                    self.assertEqual(len(baseline['safety_dimensions']),17)
                    result=await apply_resource_proposal(db,await db.get(AgentSession,sid),
                        {'safety_config':{**config,'scenario':'healthcare'}},actor=actor)
                    self.assertIn('安全评测配置',result['updated'])
                    await db.commit()
            client.portal.call(tool_proposal)
            plan=client.get(f'/api/agents/sessions/{sid}',headers=headers).json()['plan']
            self.assertEqual(plan['safety_config']['scenario'],'healthcare')
            modified={**plan,'safety_config':{**plan['safety_config'],'max_turns':1}}
            self.assertNotEqual(canonical_plan_hash(plan),canonical_plan_hash(modified))
            approval=client.post(f'/api/agents/sessions/{sid}/approve',headers=headers,json={'ttl_minutes':30})
            self.assertEqual(approval.status_code,200,approval.text)
            confirmed=client.post(f'/api/agents/sessions/{sid}/confirm',headers=headers,
                json={'execute':False,'approval_id':approval.json()['approval']['id'],'expected_plan_hash':plan['canonical_hash'],'client_invocation_id':name})
            self.assertEqual(confirmed.status_code,200,confirmed.text)
            task=client.get(f"/api/tasks/{confirmed.json()['task_id']}",headers=headers).json()
            self.assertEqual(task['safety_config'],plan['safety_config'])
            self.assertEqual(task['task_type'],'security')
            self.assertFalse(client.get(f"/api/safety/assessments/{task['id']}",headers=headers).json()['leaderboard_eligible'])

    def test_task_api_freezes_safety_config_and_rejects_wrong_dataset_version(self):
        with TestClient(app) as client:
            login=client.post('/api/auth/login',json={'username':'admin','password':'admin123'})
            headers={'Authorization':'Bearer '+login.json()['access_token']}
            valid=client.post('/api/safety/benchmarks/validate',headers=headers,json={'samples':benchmark_template()['samples']})
            self.assertEqual(valid.status_code,200,valid.text)
            self.assertEqual(valid.json()['validation_scope'],'schema_only')
            invalid=client.post('/api/safety/benchmarks/validate',headers=headers,json={'samples':[{'input':'无证据','safety':{'id':'x','dimension':'hallucination.object','rubric':'依据证据','required_any':['甲']}}]})
            self.assertEqual(invalid.status_code,400,invalid.text)
            name='isolated-safety-api-'+uuid.uuid4().hex[:8]
            dataset=client.post('/api/datasets',headers=headers,json={'name':name,'task_type':'chat'}).json()
            imported=client.post(f"/api/datasets/{dataset['id']}/import",headers=headers,
                files={'file':('samples.json',json.dumps(benchmark_template()['samples']).encode(),'application/json')})
            self.assertEqual(imported.status_code,200,imported.text)
            loaded=client.get(f"/api/safety/benchmarks/{dataset['id']}",headers=headers)
            self.assertEqual(loaded.status_code,200,loaded.text)
            self.assertEqual(len(loaded.json()['samples']),17)
            model=client.post('/api/models',headers=headers,json={'name':name,'api_url':''}).json()
            payload={'name':name,'dataset_id':dataset['id'],'model_id':model['id'],'trial_run':True,
                     'safety_config':SafetyConfig(turn_aggregation='worst',perspective_evaluation=True).model_dump()}
            created=client.post('/api/tasks',headers=headers,json=payload)
            self.assertEqual(created.status_code,200,created.text)
            task=created.json()
            self.assertEqual(task['task_type'],'security')
            self.assertEqual(task['judge_resource_id'],'builtin/safety_protocol')
            self.assertEqual(task['safety_config']['dimension_weights'],SafetyConfig().dimension_weights)
            self.assertEqual(task['safety_config']['turn_aggregation'],'worst')
            self.assertTrue(task['safety_config']['perspective_evaluation'])
            revised=benchmark_template()['samples']
            revised[0]['safety']['rubric']='新版独立准则，历史任务不得回填'
            version_two=client.post(f"/api/datasets/{dataset['id']}/import",headers=headers,
                files={'file':('revised.json',json.dumps(revised).encode(),'application/json')})
            self.assertEqual(version_two.status_code,200,version_two.text)
            self.assertNotEqual(version_two.json()['version_id'],imported.json()['version_id'])
            historical=client.get(f"/api/tasks/{task['id']}",headers=headers).json()
            self.assertEqual(historical['dataset_version_id'],imported.json()['version_id'])
            conclusion=client.get(f"/api/safety/assessments/{task['id']}",headers=headers)
            self.assertEqual(conclusion.status_code,200,conclusion.text)
            self.assertFalse(conclusion.json()['leaderboard_eligible'])
            self.assertIsNone(conclusion.json()['score'])
            payload['dataset_version_id']=99999999
            rejected=client.post('/api/tasks',headers=headers,json=payload)
            self.assertEqual(rejected.status_code,400,rejected.text)


if __name__ == '__main__':
    unittest.main()
