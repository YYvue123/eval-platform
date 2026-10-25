from tests import isolated_env  # noqa: F401

import unittest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.database import Base
from app.models import EvalTask, AgentSession
from app.api.dashboard import get_workbench


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_counts_are_not_limited_and_activity_has_empty_days(self):
        engine = create_async_engine('sqlite+aiosqlite:///:memory:')
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                for i in range(12):
                    db.add(EvalTask(name=f'review {i}', dataset_id=1, model_id=1, status='pending_review', created_at=now))
                db.add(EvalTask(name='partial', dataset_id=1, model_id=1, status='partial_failed', created_at=now))
                db.add(EvalTask(name='old', dataset_id=1, model_id=1, status='success', created_at=now-timedelta(days=40)))
                await db.commit()
                result = await get_workbench(db=db, _=None)
                self.assertEqual(result['pending_reviews'], 12)
                self.assertEqual(len(result['activity']), 30)
                self.assertEqual(sum(r['created'] for r in result['activity']), 13)
                self.assertEqual(sum(r['failed'] for r in result['activity']), 1)
                self.assertEqual(result['activity'][-1]['created'], 13)
                self.assertEqual(result['activity'][0]['created'], 0)
                self.assertEqual(result['failed'][0]['name'], 'partial')
                self.assertEqual(sum(r['count'] for r in result['task_types']), 14)
        finally:
            await engine.dispose()
