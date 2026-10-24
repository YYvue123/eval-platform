"""Isolated regression tests for protocol boundaries and measured chart data."""
from tests import isolated_env  # noqa: F401

import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.database import async_session, init_db
from app.models import Dataset, DatasetItem, DatasetVersion, EvalModel, EvalResult, EvalTask
from app.services.actor_context import ActorContext
from app.services.leaderboard import cohort_id_of, recalculate_cost
from app.services.leaderboard_insights import insights, summarize_results


class MeasurementTests(unittest.TestCase):
    def test_missing_is_not_zero_and_failed_scores_are_not_measured(self):
        row = SimpleNamespace(item_id=1, simulation=False, execution_status="ok", score_status="scored", score=0, passed=False, latency_ms=125)
        bad = SimpleNamespace(item_id=2, simulation=False, execution_status="ok", score_status="legacy_unverified", score=1, passed=True, latency_ms=10)
        summary = summarize_results([row, bad], None, {"知识": {1}, "推理": {2}})
        self.assertEqual(summary["dimensions"]["知识"]["score"], 0)
        self.assertIsNone(summary["dimensions"]["推理"]["score"])
        self.assertEqual(summary["sample_count"], 1)
        self.assertEqual(summary["latency_ms"], 125)

    def test_no_estimated_latency_or_default_price(self):
        task = SimpleNamespace(tokens_used=1000, total=20)
        self.assertIsNone(recalculate_cost(task, None)["total_cost"])
        price = SimpleNamespace(token_price_per_1k=1, latency_price_per_sec=.2, gpu_hour_price=0)
        self.assertIsNone(recalculate_cost(task, price)["total_cost"])
        self.assertEqual(recalculate_cost(task, price, 2)["total_cost"], 1.4)


class ProtocolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_is_selected_within_protocol_and_tenant(self):
        await init_db()
        async with async_session() as db:
            actor = ActorContext(900001, "fixture", 900001, "admin", "all", {"leaderboard:view"}, True)
            ds = Dataset(name="isolated-insights", status="published", tenant_id=actor.tenant_id, creator_id=actor.user_id)
            model = EvalModel(name="isolated-model", tenant_id=actor.tenant_id, creator_id=actor.user_id)
            db.add_all([ds, model]); await db.flush()
            version = DatasetVersion(dataset_id=ds.id, version_code="test-v1")
            db.add(version); await db.flush()
            item = DatasetItem(dataset_id=ds.id, version_id=version.id, item_no=1, data_label="数学")
            db.add(item); await db.flush()
            now = datetime.utcnow()
            async def add(judge, offset, score, tenant=900001, scored=True):
                task = EvalTask(name="isolated fixture", model_id=model.id, dataset_id=ds.id, dataset_version_id=version.id,
                    judge_resource_id=judge, scene="qa", industry="general", tenant_id=tenant, creator_id=actor.user_id,
                    status="success", finished_at=now+timedelta(seconds=offset), simulation=False, trial_run=False,
                    tokens_used=10, avg_score=score, prompt_id=None, prompt_version_id=None, tool_version="1", metric_weights_json="{}")
                db.add(task); await db.flush()
                db.add(EvalResult(task_id=task.id,item_id=item.id,item_no=1,score=score,passed=score>0,
                    execution_status="ok",score_status="scored" if scored else "legacy_unverified",simulation=False,latency_ms=100))
                await db.flush()
                return task
            old = await add("builtin/exact_match", -10, 0)
            await add("builtin/exact_match", -5, 1)
            await add("builtin/fuzzy", 0, .8)
            await add("builtin/exact_match", 1, .4, tenant=900002)
            await add("builtin/exact_match", 2, .9, scored=False)
            cid = cohort_id_of(old)
            result = await insights(db, actor, cohort_id=cid)
            self.assertEqual(len(result["cohorts"]), 2)
            self.assertEqual(result["items"][0]["score"], 1)
            self.assertEqual(len(result["history"]), 2)
            self.assertEqual(result["excluded_total"], 1)
            self.assertIsNone(result["items"][0]["cost"])
            past = await insights(db, actor, cohort_id=cid, as_of=now-timedelta(seconds=8))
            self.assertEqual(past["items"][0]["score"], 0)
            empty = await insights(db, actor, cohort_id="does-not-exist")
            self.assertEqual(empty["items"], [])
            await db.rollback()
