"""Isolated functional/security tests; fixtures are not production acceptance evidence."""
import asyncio
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tests import isolated_env
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///' + (Path(__file__).parent / '_isolated' / 'service_portal_test.db').resolve().as_posix()
isolated_env.assert_isolated_database(os.environ['DATABASE_URL'])

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.database import engine, Base, async_session
from app.models import (Dataset, DatasetVersion, DatasetItem, EvalModel, EvalTask, ModelVersion, ServiceCall, ServiceClient,
                        ServiceGatewayAudit, Tenant, User)
from app.api import service_portal, tasks
from app.services.model_access import insert_access_snapshot
from app.services.service_portal import period_starts
from app.utils.auth import create_access_token

app = FastAPI()
app.include_router(service_portal.router, prefix='/api/service-portal')
app.include_router(service_portal.gateway, prefix='/api/service-gateway/v1')
app.include_router(tasks.service_router, prefix='/api/services')
P = '/api/service-portal'
G = '/api/service-gateway/v1'


class ExternalServicesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        async def init():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        asyncio.run(init())
        cls.client = TestClient(app)
        # Controlled HTTP provider fixture, never a formal model quality acceptance.
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread
        import json
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                data = {'choices': [{'message': {'content': 'fixture'}, 'finish_reason': 'stop'}], 'usage': {'total_tokens': 7}}
                if getattr(self.server, 'omit_usage', False):
                    data.pop('usage')
                payload = json.dumps(data).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *_):
                pass
        cls.provider = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.provider_thread = Thread(target=cls.provider.serve_forever, daemon=True)
        cls.provider_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.provider.shutdown()
        cls.provider.server_close()
        cls.provider_thread.join()
        cls.client.close()

    def setUp(self):
        self.provider.omit_usage = False
        self.suffix = uuid.uuid4().hex[:12]
        async def seed():
            async with async_session() as db:
                tenant = Tenant(code=self.suffix, name='operator fixture')
                db.add(tenant)
                await db.flush()
                user = User(username='admin_' + self.suffix, password_hash='not-used', tenant_id=tenant.id, role='admin')
                db.add(user)
                await db.commit()
                return user.username
        self.admin = {'Authorization': 'Bearer ' + create_access_token({'sub': asyncio.run(seed())})}
        self.customer, self.h = self.customer_account('a')
        self.other, self.other_h = self.customer_account('b')
        self.ws = self.customer['workspace_id']
        res = self.client.post(P + '/clients', headers=self.h, json={'name': 'application', 'workspace_id': self.ws})
        self.assertEqual(res.status_code, 200, res.text)
        self.cid, self.key = res.json()['id'], res.json()['api_key']
        self.set_quota(100, 1000)
        async def assets():
            async with async_session() as db:
                ds = Dataset(name='fixture', tenant_id=self.customer['tenant_id'], creator_id=self.customer['user_id'], visibility='shared', status='published', quality_status='passed')
                model = EvalModel(name='fixture', tenant_id=self.customer['tenant_id'], creator_id=self.customer['user_id'], visibility='shared', api_url=f'http://127.0.0.1:{self.provider.server_port}', status='active')
                db.add_all([ds, model])
                await db.flush()
                dv = DatasetVersion(dataset_id=ds.id, version_code='fixture')
                db.add(dv)
                await db.flush()
                ds.current_version_id = dv.id
                db.add(DatasetItem(dataset_id=ds.id, version_id=dv.id, item_no=1, input_content='fixture', reference_answer='fixture'))
                v = ModelVersion(model_id=model.id, version_code='fixture-v1')
                db.add(v)
                await db.flush()
                model.current_version_id = v.id
                await insert_access_snapshot(db, model)
                await db.commit()
                return ds.id, model.id, v.id
        self.did, self.mid, self.vid = asyncio.run(assets())
        res = self.client.post(P + '/routes', headers=self.h, json={'workspace_id': self.ws, 'name': 'test route'})
        self.rid = res.json()['id']
        self.release = self.add_release('v1')
        self.set_traffic(self.release)
        self.body = {'client_id': self.cid, 'route_id': self.rid, 'title': 'Test evaluation', 'dataset_id': self.did, 'token_budget': 60}

    def customer_account(self, suffix):
        username = 'client_' + suffix + self.suffix
        r = self.client.post(P + '/customers', headers=self.admin, json={'username': username, 'password': 'integration-password-123', 'company': username})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json(), {'Authorization': 'Bearer ' + create_access_token({'sub': username})}

    def set_quota(self, day, month, rpm=30):
        r = self.client.put(f'{P}/clients/{self.cid}/quota', headers=self.admin,
            json={'daily_tokens': day, 'monthly_tokens': month, 'requests_per_minute': rpm, 'price_fen_per_1k': 100})
        self.assertEqual(r.status_code, 200, r.text)

    def add_release(self, label):
        r = self.client.post(f'{P}/routes/{self.rid}/versions', headers=self.h,
            json={'version': label, 'model_id': self.mid, 'model_version_id': self.vid})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()['id']

    def set_traffic(self, stable, candidate=None, pct=0):
        r = self.client.put(f'{P}/routes/{self.rid}/traffic', headers=self.h,
            json={'stable_id': stable, 'candidate_id': candidate, 'gray_percent': pct})
        self.assertEqual(r.status_code, 200, r.text)

    def submit(self, key='once', body=None):
        return self.client.post(G + '/evaluations', headers={'X-API-Key': self.key, 'Idempotency-Key': key}, json=body or self.body)

    def execute_task(self, task_id):
        async def execute():
            from app.database import seed_builtin_resources
            from app.services.task_service import claim_task
            from app.services.task_runner import run_eval_task
            async with async_session() as db:
                await seed_builtin_resources(db)
                task, token = await claim_task(db, task_id, owner='isolated-service-test')
                self.assertIsNotNone(task)
                await db.commit()
            await run_eval_task(task_id, fencing_token=token, lease_owner='isolated-service-test')
        asyncio.run(execute())

    def test_taskservice_execution_usage_and_report_delivery(self):
        response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        call_id, task_id = response.json()['id'], response.json()['task_id']
        self.execute_task(task_id)
        result = self.client.get(f'{G}/evaluations/{call_id}', headers={'X-API-Key': self.key})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['status'], 'success', result.text)
        self.assertEqual(result.json()['tokens'], 7)
        self.assertEqual(result.json()['reserved_tokens'], 7)
        self.assertEqual(result.json()['amount_fen'], 1)
        self.assertEqual(result.json()['billing_status'], 'settled')
        report = self.client.get(f'{G}/evaluations/{call_id}/report', headers={'X-API-Key': self.key})
        self.assertEqual(report.status_code, 200, report.text)
        self.assertEqual(self.submit().json()['id'], call_id)

    def test_missing_provider_usage_remains_unmeasured(self):
        self.provider.omit_usage = True
        created = self.submit()
        self.assertEqual(created.status_code, 200, created.text)
        self.execute_task(created.json()['task_id'])
        result = self.client.get(f"{G}/evaluations/{created.json()['id']}", headers={'X-API-Key': self.key})
        self.assertEqual(result.json()['billing_status'], 'unmeasured', result.text)
        self.assertEqual(result.json()['reserved_tokens'], 60)
        self.assertEqual(self.submit('second').status_code, 429)

    def test_asset_grant_copies_published_snapshot(self):
        result = self.client.post(P + '/assets/grants', headers=self.admin,
            json={'tenant_id': self.other['tenant_id'], 'dataset_id': self.did})
        # Even service operators must have access to the source dataset.
        self.assertEqual(result.status_code, 404)
        self.assertEqual(self.client.post(P + '/assets/grants', headers=self.h,
            json={'tenant_id': self.other['tenant_id'], 'dataset_id': self.did}).status_code, 403)
        async def operator_asset():
            async with async_session() as db:
                admin = await db.scalar(select(User).where(User.username == 'admin_' + self.suffix))
                ds = Dataset(name='operator-published-fixture', tenant_id=admin.tenant_id,
                    creator_id=admin.id, status='published', quality_status='passed')
                db.add(ds)
                await db.flush()
                version = DatasetVersion(dataset_id=ds.id, version_code='source-v1', checksum='fixture-checksum')
                db.add(version)
                await db.flush()
                ds.current_version_id = version.id
                db.add(DatasetItem(dataset_id=ds.id, version_id=version.id, item_no=1, input_content='shared fixture'))
                await db.commit()
                return ds.id
        source = asyncio.run(operator_asset())
        granted = self.client.post(P + '/assets/grants', headers=self.admin,
            json={'tenant_id': self.other['tenant_id'], 'dataset_id': source})
        self.assertEqual(granted.status_code, 200, granted.text)
        visible = self.client.get(P + '/assets', headers=self.other_h).json()['datasets']
        self.assertIn(granted.json()['dataset_id'], [d['id'] for d in visible])

    def test_endpoint_registration_allowlist_and_secret_redaction(self):
        from app.config import settings
        from unittest.mock import patch
        payload = {'version': 'endpoint-v3', 'api_url': 'https://allowed.example/v1', 'api_key': 'upstream-secret', 'served_model_name': 'test-model'}
        with patch.object(settings, 'SERVICE_MODEL_HOSTS', 'allowed.example'):
            for url in ['http://allowed.example', 'https://evil.example', 'https://allowed.example:8080', 'https://allowed.example:bad']:
                r = self.client.post(f'{P}/routes/{self.rid}/endpoints', headers=self.h, json={**payload, 'api_url': url})
                self.assertEqual(r.status_code, 400, r.text)
            r = self.client.post(f'{P}/routes/{self.rid}/endpoints', headers=self.h, json=payload)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertNotIn('upstream-secret', r.text)
        listing = self.client.get(G + '/services', headers={'X-API-Key': self.key})
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertNotIn('upstream-secret', listing.text)
        self.assertEqual(self.client.get(G + '/usage', headers={'X-API-Key': self.key}).status_code, 200)

    def test_concurrent_admission_cannot_overspend(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda k: self.submit(k), ['parallel-a', 'parallel-b']))
        self.assertEqual(sorted(r.status_code for r in results), [200, 429], [r.text for r in results])

    def test_tenant_isolation_and_customer_permissions(self):
        for path in ['clients', 'routes', 'evaluations', 'gateway-audit']:
            r = self.client.get(f'{P}/{path}', params={'workspace_id': self.ws}, headers=self.other_h)
            self.assertEqual(r.status_code, 404, r.text)
        self.assertEqual(self.client.post(f'{P}/clients/{self.cid}/revoke', headers=self.other_h).status_code, 404)
        self.assertEqual(self.client.put(f'{P}/clients/{self.cid}/quota', headers=self.h, json={'daily_tokens': 999, 'monthly_tokens': 999, 'requests_per_minute': 1, 'price_fen_per_1k': 0}).status_code, 403)
        self.assertEqual(self.client.get('/api/services/workspaces', headers=self.h).status_code, 403)
        self.assertEqual(self.client.get(P + '/assets', headers=self.other_h).json()['models'], [])

    def test_idempotency_quota_and_audit(self):
        first = self.submit()
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['status'], 'queued')
        second = self.submit()
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(self.submit('next').status_code, 429)
        self.assertEqual(self.submit(body={**self.body, 'title': 'different'}).status_code, 409)
        client = self.client.get(P + '/clients', headers=self.h, params={'workspace_id': self.ws}).json()['items'][0]
        self.assertEqual(client['usage']['daily_used'], 60)
        self.assertNotIn('key_hash', client)
        self.assertNotIn('api_key', client)
        audit = self.client.get(P + '/gateway-audit', headers=self.h, params={'workspace_id': self.ws}).json()['items']
        self.assertEqual(sorted(a['status_code'] for a in audit), [200, 200, 409, 429])

    def test_gray_and_rollback_bind_release(self):
        candidate = self.add_release('v2')
        self.set_traffic(self.release, candidate, 100)
        r = self.submit()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['release_id'], candidate)
        self.set_traffic(candidate)
        self.assertEqual(self.client.post(f'{P}/routes/{self.rid}/rollback', headers=self.h).status_code, 200)
        route = self.client.get(P + '/routes', headers=self.h, params={'workspace_id': self.ws}).json()['items'][0]
        self.assertEqual(route['stable_id'], self.release)
        self.assertEqual(route['gray_percent'], 0)
        self.assertEqual(self.submit().json()['release_id'], candidate)

    def test_revoke_invalid_key_validation_and_gateway_scope(self):
        r = self.submit()
        call_id = r.json()['id']
        unauthorized = self.client.post(G + '/evaluations', headers={'X-API-Key': 'bad', 'Idempotency-Key': 'x'}, json=self.body)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(self.client.post(G + '/evaluations', headers={'X-API-Key': self.key}, json={}).status_code, 422)
        key2 = self.client.post(P + '/clients', headers=self.h, json={'name': 'second', 'workspace_id': self.ws}).json()['api_key']
        self.assertEqual(self.client.get(f'{G}/evaluations/{call_id}', headers={'X-API-Key': key2}).status_code, 404)
        self.assertEqual(self.client.post(f'{P}/clients/{self.cid}/revoke', headers=self.h).status_code, 200)
        self.assertEqual(self.submit('revoked').status_code, 401)
        self.assertEqual(self.client.get(f'{G}/evaluations/{call_id}', headers={'X-API-Key': self.key}).status_code, 401)

    def test_expert_confirm_and_cancel_release_reservation(self):
        r = self.submit(body={**self.body, 'mode': 'expert', 'judge_resource_id': 'builtin/contains'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['status'], 'draft')
        cid = r.json()['id']
        self.assertEqual(self.client.post(f'{P}/evaluations/{cid}/start', headers=self.other_h).status_code, 404)
        start = self.client.post(f'{P}/evaluations/{cid}/start', headers=self.h)
        self.assertEqual(start.status_code, 200, start.text)
        self.assertEqual(start.json()['status'], 'queued')
        self.assertEqual(self.client.post(f'{P}/evaluations/{cid}/start', headers=self.h).status_code, 409)
        self.assertEqual(self.client.get(f'{P}/evaluations/{cid}/report', headers=self.h).status_code, 409)
        cancel = self.client.post(f'{P}/evaluations/{cid}/cancel', headers=self.h)
        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertEqual(cancel.json()['reserved_tokens'], 0)
        self.assertEqual(self.submit('after-cancel').status_code, 200)

    def test_monthly_quota_rate_limit_and_periods(self):
        self.set_quota(1000, 50)
        self.assertEqual(self.submit().status_code, 429)
        self.set_quota(1000, 1000, rpm=1)
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(self.submit('rate').status_code, 429)
        day, month = period_starts(datetime(2026, 10, 1, 0, 1, tzinfo=timezone(timedelta(hours=8))))
        self.assertEqual(day, datetime(2026, 9, 30, 16))
        self.assertEqual(month, day)

    def test_cross_tenant_report_and_injected_client(self):
        cid = self.submit().json()['id']
        self.assertEqual(self.client.get(f'{P}/evaluations/{cid}/report', headers=self.other_h).status_code, 404)
        outsider = self.client.post(P + '/clients', headers=self.other_h, json={'name': 'other', 'workspace_id': self.other['workspace_id']}).json()
        self.assertEqual(self.submit('injection', {**self.body, 'client_id': outsider['id']}).status_code, 404)
        self.assertEqual(self.client.get(P + '/members', headers=self.h).json()['items'][0]['id'], self.customer['user_id'])


if __name__ == '__main__':
    unittest.main()
