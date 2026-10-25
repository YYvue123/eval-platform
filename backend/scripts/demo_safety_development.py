"""Real local safety evaluations through authenticated APIs in the existing database.

No isolated_env, SQL writes, fabricated outputs, or automatic expert approvals.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import settings

EVIDENCE = Path(__file__).resolve().parents[2] / "docs/delivery/safety-development-evidence-2026-10-25.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['prepare', 'start', 'collect'], default='collect')
    parser.add_argument('--rule-only', action='store_true')
    parser.add_argument('--task-id', type=int)
    parser.add_argument('--password', default=None)
    args = parser.parse_args()
    if settings.APP_ENV == 'production' or settings.DATABASE_URL != 'sqlite+aiosqlite:///./eval_platform.db':
        raise RuntimeError('Restricted to the existing local development database')
    client = httpx.Client(base_url='http://127.0.0.1:8000/api', timeout=300)

    def api(method, path, **kw):
        response = client.request(method, path, **kw)
        response.raise_for_status()
        return response.json()

    token = api('POST', '/auth/login', json={'username':'admin','password':args.password or 'admin123'})['access_token']
    client.headers['Authorization'] = 'Bearer ' + token
    state = json.loads(EVIDENCE.read_text(encoding='utf-8')) if EVIDENCE.exists() else {
        'source':'existing application database; authenticated API; actual configured model endpoints; no mock',
        'limitations':'AI-authored small development benchmark, not FlagEval data or industry certification. Expert review/calibration remain human actions. Judge may share a base model with the target; report configuration identities explicitly.',
        'models':[], 'tasks':[]}

    def save():
        if EVIDENCE.exists():
            previous = json.loads(EVIDENCE.read_text(encoding='utf-8'))
            known = {t['id'] for t in state['tasks']}
            state['tasks'].extend(t for t in previous.get('tasks', []) if t['id'] not in known)
        EVIDENCE.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')

    if args.task_id and not any(t['id'] == args.task_id for t in state['tasks']):
        current = api('GET', f'/tasks/{args.task_id}')
        if not current['name'].startswith('安全可信真实评测-') or current['task_type'] != 'security':
            raise RuntimeError('Task is not owned by this development demonstration')
        state['tasks'].append({k:current[k] for k in ['id','model_id','name','status']})
        state['tasks'][-1]['mode'] = 'rule' if current['safety_config'].get('rule_weight') == 1 else 'hybrid'
        save()

    if args.stage == 'prepare':
        if not all([settings.L3_MODEL_API_URL, settings.L3_MODEL_API_KEY, settings.L3_MODEL_PRIMARY]):
            raise RuntimeError('Missing real configured model connection')
        if not state['models']:
            names = list(dict.fromkeys(n for n in [settings.L3_MODEL_PRIMARY,settings.L3_MODEL_SECONDARY] if n))
            for name in names:
                model = api('POST','/models',json={'name':f'安全实测-{name}', 'description':f'真实安全开发评测，基础模型：{name}；非模拟配置。',
                    'api_url':settings.L3_MODEL_API_URL,'api_key':settings.L3_MODEL_API_KEY,'served_model_name':name,
                    'auth_type':'bearer_token','channel_type':settings.L3_MODEL_CHANNEL,'timeout':90,'scene_white_list':['chat']})
                state['models'].append({'id':model['id'],'name':model['name'],'base_model':name})
                save()
        if not state.get('dataset'):
            benchmark = api('GET','/safety/benchmark-template')
            ds = api('POST','/datasets',json={'name':'安全可信开发基准V2-2026-10-25','task_type':'chat','tags':['safety','safety-protocol-v2'],'description':benchmark['source']})
            state['dataset']={'id':ds['id'],'name':ds['name']};save()
            imported = api('POST',f"/datasets/{ds['id']}/import",files={'file':('safety-v2.json',json.dumps(benchmark['samples'],ensure_ascii=False).encode(),'application/json')})
            state['dataset'].update(version_id=imported['version_id'],samples=imported['data_count']);save()
            quality=api('POST','/quality/run',params={'dataset_id':ds['id'],'version_id':imported['version_id']})
            state['dataset']['quality_status']=quality.get('status');save()
            published=api('POST',f"/datasets/{ds['id']}/publish")
            state['dataset']['status']=published['status'];save()
        for model in state['models']:
            mode = 'rule' if args.rule_only else 'hybrid'
            if any(t['model_id']==model['id'] and t.get('mode','hybrid') == mode for t in state['tasks']):
                continue
            task=api('POST','/tasks',json={'name':f"安全可信真实评测-{mode}-{model['base_model']}",'task_type':'security','scene':'chat',
                'dataset_id':state['dataset']['id'],'model_id':model['id'],'judge_resource_id':'builtin/safety_protocol',
                'safety_config':{'set_type':'fixed','adaptive':True,'max_turns':2,'judge_model_id':None if args.rule_only else state['models'][0]['id'],'rule_weight':1 if args.rule_only else .5}})
            state['tasks'].append({'id':task['id'],'model_id':model['id'],'name':task['name'],'mode':mode,'status':task['status']});save()
    elif args.stage == 'start':
        for task in state['tasks']:
            if args.task_id and task['id'] != args.task_id:
                continue
            current=api('GET',f"/tasks/{task['id']}")
            if current['status'] in {'draft', 'queued'}:
                current=api('POST',f"/tasks/{task['id']}/run")
            task['status']=current['status'];save()
    else:
        for task in state['tasks']:
            current=api('GET',f"/tasks/{task['id']}")
            task.update({k:current.get(k) for k in ['status','progress','total','success_count','fail_count','avg_score','pass_rate','tokens_used','simulation','report_path']})
            assessment=api('GET',f"/safety/assessments/{task['id']}")
            task['assessment']={k:v for k,v in assessment.items() if k!='results'}
            task['results']=[{'id':r['id'],'score':r['score'],'execution_status':r['execution_status'],'score_status':r['score_status'],
                'dimension':r['metrics'].get('dimension'),'turn_count':r['metrics'].get('turn_count'),'evidence_hash':r['evidence_hash'],'error':r['error']} for r in assessment['results']]
            save()
        board=api('GET','/leaderboard/insights',params={'category':'safety'})
        state['leaderboard']={k:board.get(k) for k in ['cohort_id','dimensions','items','excluded','rules']};save()
    print(json.dumps({'stage':args.stage,'tasks':[{k:t.get(k) for k in ['id','status','progress','total','tokens_used']} for t in state['tasks']], 'evidence':str(EVIDENCE)},ensure_ascii=False))


if __name__=='__main__':
    main()
