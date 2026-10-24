"""Isolated infrastructure fixtures; these are not formal evaluation acceptance."""
from tests import isolated_env  # noqa: F401

import unittest
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import select

from app.config import settings
from app.models import AgentDelegation, AgentEvent, AgentRun, AgentSession, Dataset, EvalModel
from app.services import agent_runtime as runtime
from app.services.agent_lifecycle import bind_scenario_roles, ensure_followup, run_stage, track_task
from app.services.agent_context import resource_inventory
from app.services.agent_capabilities import create_definition
from app.services.agent_report import create_revision, publish_revision
from app.api.agents import session_runs
from app.utils.jsonutil import dumps, loads
from tests.test_agent_langgraph import LangGraphRuntimeTest, answer


class AgentLifecycleTest(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = LangGraphRuntimeTest.asyncSetUp
    asyncTearDown = LangGraphRuntimeTest.asyncTearDown
    create = LangGraphRuntimeTest.create
    make_task = LangGraphRuntimeTest.make_task

    async def test_inventory_excludes_other_tenant_and_planner(self):
        self.db.add_all([
            Dataset(name='visible', tenant_id=self.tenant.id, creator_id=self.user.id),
            Dataset(name='hidden', tenant_id=self.tenant.id+10000),
            EvalModel(name='target', api_url='https://example.invalid', tenant_id=self.tenant.id, creator_id=self.user.id),
            EvalModel(name='hidden target', api_url='https://example.invalid', tenant_id=self.tenant.id+10000),
        ])
        await self.db.flush()
        inventory = await resource_inventory(self.db, self.actor)
        self.assertEqual([row['name'] for row in inventory['datasets']], ['visible'])
        self.assertEqual([row['name'] for row in inventory['models']], ['target'])
        self.assertNotIn('api_key', dumps(inventory))

    async def test_custom_keyword_binding_preserves_explicit_optimizer(self):
        await create_definition(self.db, self.actor, {'role': 'coverage_test', 'name': 'coverage', 'evaluation_spec': {'stages': ['planning'], 'trigger_keywords': ['客服']}})
        bound = await bind_scenario_roles(self.db, self.actor, '客服售后评测', {'subagent_roles': ['monitor','diagnose']})
        self.assertIn('coverage_test', bound['subagent_roles'])
        self.assertIn('plan_analyst', bound['subagent_roles'])
        self.assertNotIn('report_optimizer', bound['subagent_roles'])

    async def test_planning_children_leave_real_protocol_trace_and_dedupe(self):
        plan={'capabilities': {'subagent_roles': ['plan_analyst'], 'skill_codes': ['clarify_goal'], 'mcp_resource_ids': []}}
        self.session.plan_json=dumps(plan)
        run=await self.create()
        with patch('app.services.model_client.invoke_chat_tools', return_value=answer('fixture analysis')) as invoke:
            await run_stage(self.db, run, 'planning', 'snapshot1', 'inspect resources')
            await run_stage(self.db, run, 'planning', 'snapshot1', 'inspect resources')
        self.assertEqual(invoke.call_count, 1)
        rows=(await self.db.execute(select(AgentDelegation).where(AgentDelegation.run_id==run.id))).scalars().all()
        self.assertEqual(len(rows),1)
        trace=loads(rows[0].evidence_json, [])
        self.assertEqual([x['type'] for x in trace], ['started','model.request','model.response','completed'])
        self.assertIn('平台授权资源', trace[1]['messages'][0]['content'])

    async def test_automatic_planning_preserves_unknown_child_usage(self):
        self.session.plan_json = dumps({'capabilities':{'subagent_roles':['plan_analyst','param_advisor'],'skill_codes':[],'mcp_resource_ids':[]}})
        run = await self.create(purpose='planning')
        _, token = await runtime.claim_run(self.db,run.id)
        with patch('app.services.model_client.invoke_chat_tools', side_effect=[answer(tokens=None),answer(tokens=7),answer(tokens=3)]):
            await runtime.execute_until_idle(self.db,run.id,fencing_token=token)
        self.assertTrue(runtime.run_out(run)['tokens_usage_unknown'])
        self.assertEqual(run.tokens_used,10)

    async def test_followup_marks_existing_approval_run(self):
        await self.make_task(status='queued')
        run=await self.create()
        active=await ensure_followup(self.db,self.session)
        self.assertEqual(active.id,run.id)
        self.assertEqual(loads(self.session.plan_json,{})['tracking_run_id'],run.id)

    async def test_queued_approval_node_can_enter_interrupt_before_authorization(self):
        from app.services.agent_graph import can_resume
        run = await self.create()
        run.checkpoint_json = dumps({"phase": "await_approval"})
        run.status = 'queued'
        self.assertTrue(await can_resume(self.db, run))
        run.status = 'waiting'
        self.assertFalse(await can_resume(self.db, run))

    async def test_failed_planning_clears_pending_marker_for_budget_recovery(self):
        run = await self.create(purpose='planning')
        self.session.plan_json = dumps({'analysis_status':'pending','planning_run_id':run.id})
        run.status = 'paused_budget'
        await runtime._clear_active(self.db, run)
        self.assertIsNone(self.session.active_run_id)
        self.assertEqual(loads(self.session.plan_json,{})['analysis_status'],'failed')

    async def test_followup_starts_after_planning_finished(self):
        await self.make_task(status='queued')
        run=await ensure_followup(self.db,self.session)
        cp=loads(run.checkpoint_json,{})
        self.assertEqual(cp['purpose'],'followup')
        self.assertEqual(cp['phase'],'verify')
        self.assertEqual(self.session.active_run_id,run.id)

    async def test_changed_approved_plan_uses_new_tracking_run(self):
        await self.make_task(status='queued')
        old = await self.create()
        old.status = 'waiting'
        old.checkpoint_json = dumps({'phase':'await_approval','approval_plan_hash':'old-plan'})
        run = await ensure_followup(self.db, self.session)
        self.assertNotEqual(old.id, run.id)
        self.assertEqual(old.status,'cancelled')
        self.assertEqual(loads(run.checkpoint_json,{})['purpose'],'followup')

    async def test_progress_resumes_never_finish_before_task_terminal(self):
        task = await self.make_task(status='queued')
        run = await ensure_followup(self.db,self.session)
        _, token = await runtime.claim_run(self.db,run.id)
        with patch('app.services.model_client.invoke_chat_tools', return_value=answer('fixture monitoring')):
            await runtime.execute_until_idle(self.db,run.id,fencing_token=token)
            self.assertEqual(run.status,'waiting')
            for progress in [25,50,75]:
                task.status='running'
                task.progress=progress
                await self.db.flush()
                await runtime.resume_run(self.db,run)
                self.assertEqual(run.status,'waiting')
                self.assertEqual(loads(run.checkpoint_json,{})['completion']['kind'],'task_pending')
            task.status='failed'
            await self.db.flush()
            await runtime.resume_run(self.db,run)
        self.assertEqual(run.status,'failed')
        self.assertEqual(loads(run.checkpoint_json,{})['completion']['task_status'],'failed')

    async def test_task_snapshot_changes_record_monitor_and_review_once(self):
        task=await self.make_task(status='queued')
        plan=loads(self.session.plan_json,{})
        plan['capabilities']['subagent_roles']=['monitor','diagnose','report_reviewer']
        self.session.plan_json=dumps(plan)
        run=await self.create()
        with patch('app.services.model_client.invoke_chat_tools', return_value=answer('fixture observation')):
            await track_task(self.db,run)
            await track_task(self.db,run)
            task.status='failed'
            await track_task(self.db,run)
            await track_task(self.db,run)
        events=(await self.db.execute(select(AgentEvent).where(AgentEvent.run_id==run.id,AgentEvent.type=='task.observed'))).scalars().all()
        rows=(await self.db.execute(select(AgentDelegation).where(AgentDelegation.run_id==run.id))).scalars().all()
        self.assertEqual(len(events),2)
        self.assertEqual(sorted(x.role for x in rows),['diagnose','monitor','monitor','report_reviewer'])

    async def test_run_history_paginates_without_losing_older_turns(self):
        for number in range(12):
            self.db.add(AgentRun(session_id=self.session.id,tenant_id=self.tenant.id,status='success',checkpoint_thread_id=f'history-{self.session.id}-{number}',checkpoint_json=dumps({'purpose':'dialogue','input':str(number)})))
        await self.db.flush()
        first=await session_runs(self.session.id,page=1,page_size=5,db=self.db,actor=self.actor)
        last=await session_runs(self.session.id,page=3,page_size=5,db=self.db,actor=self.actor)
        self.assertEqual(first['total'],12)
        self.assertEqual([x['turn'] for x in last['items']],[11,12])
        self.assertEqual(last['items'][-1]['input'],'11')

    async def test_report_revision_preserves_original_and_detects_fact_change(self):
        path=Path(settings.UPLOAD_DIR)/f'fixture-report-{self.session.id}.json'
        path.write_text('{"synthetic_fixture":true}',encoding='utf-8')
        task=await self.make_task(status='success',report_path=str(path),total=1)
        run=await self.create()
        delegation=AgentDelegation(session_id=self.session.id,run_id=run.id,role='report_optimizer',status='success')
        self.db.add(delegation)
        await self.db.flush()
        row=await create_revision(self.db,self.session,run,{'delegation_id':delegation.id,'result':{'summary':'fixture narrative'}},self.actor)
        await publish_revision(self.db,row,self.session,self.actor)
        self.assertEqual(row.status,'published')
        self.assertEqual(path.read_text(encoding='utf-8'),'{"synthetic_fixture":true}')
        self.assertEqual(task.total,1)
        row.status='draft'
        task.total=2
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):
            await publish_revision(self.db,row,self.session,self.actor)
        path.unlink()


if __name__=='__main__':
    unittest.main()
