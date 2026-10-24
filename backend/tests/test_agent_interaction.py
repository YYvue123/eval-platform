"""Isolated interaction and durable monitoring regression, not live-model acceptance."""
from tests import isolated_env  # noqa: F401

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from starlette.requests import Request
from fastapi import HTTPException

from tests import test_agent_langgraph as fixtures
from app.api import agents
from app.models import AgentMessage, AgentEvent
from app.services import agent_runtime as runtime
from app.services.agent_lifecycle import track_task, snapshot_changed
from app.utils.jsonutil import dumps, loads


def request():
    async def receive():
        await asyncio.sleep(0)
        return {"type": "http.request", "body": b"", "more_body": False}
    return Request({"type":"http", "headers":[], "client":("127.0.0.1",1)}, receive)


class AgentInteractionTest(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = fixtures.LangGraphRuntimeTest.asyncSetUp
    asyncTearDown = fixtures.LangGraphRuntimeTest.asyncTearDown
    create = fixtures.LangGraphRuntimeTest.create
    make_task = fixtures.LangGraphRuntimeTest.make_task

    async def test_initial_requirement_is_stored_and_sent_once(self):
        intent = 'unique initial intent ' * 130
        result = await agents.create_session(agents.SessionIn(requirement=intent,planner_model_id=self.model.id), request(), self.db, self.actor)
        rows=(await self.db.execute(select(AgentMessage).where(AgentMessage.session_id==result['id'], AgentMessage.role=='user'))).scalars().all()
        self.assertEqual(len(rows),1)
        from app.models import AgentRun
        run=await self.db.get(AgentRun,result['active_run_id'])
        inputs=loads(run.checkpoint_json,{})['messages']
        self.assertEqual(sum(item['role']=='user' and item['content']==intent.strip() for item in inputs),1)
        self.assertEqual(sum(item['role']=='user' for item in inputs),1)

    async def test_legacy_planning_copy_hidden_without_deleting_audit_rows(self):
        first=AgentMessage(session_id=self.session.id,role='user',content=self.session.requirement)
        copy=AgentMessage(session_id=self.session.id,role='user',content=self.session.requirement,payload_json=dumps({'purpose':'planning'}))
        self.db.add_all([first,copy]);await self.db.flush()
        response=await agents.get_session(self.session.id,self.db,self.actor)
        self.assertEqual(sum(x['role']=='user' for x in response['messages']),1)
        self.assertEqual(len((await self.db.execute(select(AgentMessage).where(AgentMessage.session_id==self.session.id))).scalars().all()),2)

    async def test_stop_and_continue_preserve_linked_task(self):
        task=await self.make_task(status='running')
        old=await self.create()
        stopped=await agents.stop_session(self.session.id,request(),self.db,self.actor)
        self.assertEqual(old.status,'cancelled')
        self.assertEqual(task.status,'running')
        self.assertEqual(stopped['display_status'],'stopped')
        continued=await agents.continue_session(self.session.id,agents.ContinueIn(),request(),self.db,self.actor)
        self.assertNotEqual(continued['id'],old.id)
        self.assertEqual(continued['purpose'],'followup')
        self.assertEqual(continued['status'],'queued')
        self.assertEqual(self.session.task_id,task.id)

    async def test_budget_continue_requires_larger_cap(self):
        run=await self.create(token_budget=10)
        run.status='paused_budget';run.tokens_used=15
        await runtime._clear_active(self.db,run)
        with self.assertRaises(HTTPException):
            await agents.continue_session(self.session.id,agents.ContinueIn(token_budget=15),request(),self.db,self.actor)
        result=await agents.continue_session(self.session.id,agents.ContinueIn(token_budget=30),request(),self.db,self.actor)
        self.assertEqual(result['token_budget'],30)
        self.assertEqual(run.status,'paused_budget')
        self.assertNotEqual(result['id'],run.id)

    async def test_progress_milestones_and_long_task_heartbeat(self):
        task=await self.make_task(status='running',progress=10)
        run=await self.create()
        with patch('app.services.agent_lifecycle.run_stage',new=AsyncMock(return_value=[])):
            await track_task(self.db,run)
            task.progress=11;await self.db.flush()
            self.assertFalse(await snapshot_changed(self.db,run))
            task.progress=20;await self.db.flush()
            self.assertTrue(await snapshot_changed(self.db,run))
            await track_task(self.db,run)
            previous=await self.db.scalar(select(AgentEvent).where(AgentEvent.run_id==run.id,AgentEvent.type=='task.observed').order_by(AgentEvent.id.desc()).limit(1))
            previous.created_at=datetime.utcnow()-timedelta(minutes=6)
            await self.db.flush()
            self.assertTrue(await snapshot_changed(self.db,run))
            await track_task(self.db,run)
            self.assertFalse(await snapshot_changed(self.db,run))
        heartbeats=(await self.db.execute(select(AgentEvent).where(AgentEvent.run_id==run.id,AgentEvent.type=='task.heartbeat'))).scalars().all()
        self.assertEqual(len(heartbeats),1)

    async def test_sse_replays_after_sequence_and_emits_eof(self):
        run=await self.create()
        await runtime.append_event(self.db,run,'llm.reply',{'reply':'fixture only'})
        run.status='success'
        response=await agents.stream_run_events(run.id,request(),after_seq=1,db=self.db,actor=self.actor)
        chunks=[]
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        body=''.join(chunks)
        self.assertIn('llm.reply',body)
        self.assertIn('run.eof',body)
        self.assertNotIn('run.created',body)
        self.assertEqual(response.headers['x-accel-buffering'],'no')

    async def test_required_human_confirmation_cannot_be_disabled(self):
        from app.services.agent_capabilities import update_main_profile
        profile=await update_main_profile(self.db,self.tenant.id,{'human_in_the_loop':False})
        self.assertTrue(profile['human_in_the_loop'])

    async def test_sse_releases_transaction_before_network_yield(self):
        run = await self.create()
        response = await agents.stream_run_events(run.id, request(), after_seq=0, db=self.db, actor=self.actor)
        iterator = response.body_iterator
        self.assertIn('run.created', await anext(iterator))
        self.assertFalse(self.db.in_transaction())
        await iterator.aclose()

    async def test_chat_confirmation_rejects_ambiguous_or_stale_plan(self):
        from fastapi import BackgroundTasks
        from app.services.goal_spec import canonical_plan_hash
        self.session.plan_json = dumps({'ready': True, 'token_budget': 100})
        current_hash = canonical_plan_hash(loads(self.session.plan_json, {}))
        for message, plan_hash, code in [('好的', current_hash, 400), ('确认执行', '', 400), ('确认执行', 'old-plan', 409)]:
            with self.subTest(message=message, plan_hash=plan_hash):
                with self.assertRaises(HTTPException) as error:
                    await agents.confirm_session(self.session.id, agents.ConfirmIn(confirmation_message=message, expected_plan_hash=plan_hash), BackgroundTasks(), request(), self.db, self.actor)
                self.assertEqual(error.exception.status_code, code)
                self.assertIsNone(self.session.task_id)

    async def test_conversation_updates_budget_and_trial_without_form(self):
        from app.services.agent_orchestrator import apply_resource_proposal
        self.session.plan_json = dumps({'ready': False, 'goal_spec': {}, 'resource_gaps': []})
        await apply_resource_proposal(self.db, self.session, {'trial_run': True, 'token_budget': 321}, actor=self.actor)
        plan = loads(self.session.plan_json, {})
        self.assertTrue(plan['trial_run'])
        self.assertEqual(plan['token_budget'], 321)
        self.assertEqual(plan['goal_spec']['token_budget'], 321)


if __name__=='__main__':
    unittest.main()
