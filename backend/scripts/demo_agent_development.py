"""Persistent development demonstration through authenticated APIs, never SQL fixtures.

Run from backend with its .venv. Uses the existing .env model connection and live
development server. Does not import isolated_env, create databases, or fake scores.
Every resource/session/task is deliberately retained for manual inspection.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.config import settings
from app.services.agent_capabilities import DEFAULT_MAIN_PROMPT, MAIN_TOOLS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--password', default=None)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--session-index', type=int, default=None)
    args = parser.parse_args()
    if settings.APP_ENV == 'production' or settings.DATABASE_URL != 'sqlite+aiosqlite:///./eval_platform.db':
        raise RuntimeError('This demonstration is restricted to the existing local development database')
    if not all([settings.L3_MODEL_API_URL, settings.L3_MODEL_API_KEY, settings.L3_MODEL_PRIMARY]):
        raise RuntimeError('Missing real model connection in .env')
    client = httpx.Client(base_url=args.base_url, timeout=300)
    evidence_file = Path('../docs/delivery/agent-development-evidence-2026-10-24.json')
    evidence_file.parent.mkdir(exist_ok=True, parents=True)

    def api(method, path, **kw):
        response = client.request(method, '/api' + path, **kw)
        if response.status_code != 200:
            raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:600]}')
        return response.json()

    login = api('POST', '/auth/login', json={'username': 'admin', 'password': args.password or 'admin123'})
    client.headers['Authorization'] = 'Bearer ' + login['access_token']
    data = json.loads(evidence_file.read_text(encoding='utf-8')) if evidence_file.exists() else {'source': 'existing development service; authenticated APIs; real L3 model; generated inputs', 'models': [], 'datasets': [], 'resources': [], 'subagents': [], 'skills': [], 'sessions': []}

    def save():
        evidence_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    if not data['models']:
        for name in ['编排实测-规划模型', '编排实测-通用问答模型', '编排实测-数值推理模型']:
            row = api('POST', '/models', json={'name': name, 'description': '2026-10-24真实编排演示，连接.env配置的真实模型；不使用模拟输出。', 'api_url': settings.L3_MODEL_API_URL, 'api_key': settings.L3_MODEL_API_KEY, 'served_model_name': settings.L3_MODEL_PRIMARY, 'auth_type': 'bearer_token', 'channel_type': settings.L3_MODEL_CHANNEL, 'timeout': 90, 'scene_white_list': ['chat', 'table']})
            data['models'].append({'id': row['id'], 'name': name})
            save()
            health = api('POST', f"/models/{row['id']}/health")
            data['models'][-1]['health'] = {k: health[k] for k in ['health_status', 'ok', 'latency_ms'] if k in health}
            save()

    if not data['datasets']:
        groups = [
            ('客服售后覆盖题集', 'general', [(f'客服规则：订单金额为{n*10}元，支持7天无理由退货。用户询问可以无理由退货的天数。只回答整数。', '7') for n in range(1, 13)]),
            ('金融利息核验题集', 'finance', [(f'本金{n*1000}元，年利率3%，存款1年，按单利计算利息。只回答数字，不加单位。', str(n*30)) for n in range(1, 13)]),
            ('数据覆盖基础问答题集', 'general', [(f'计算{n}+{n+1}，只回答整数。', str(2*n+1)) for n in range(1, 13)]),
            ('报告审校边界题集', 'general', [(f'任务要求输出小写英文。将编号{n}后的英文词 HELLO 转换成小写，仅输出词。', 'hello') for n in range(1, 13)]),
        ]
        for title, industry, pairs in groups:
            row = api('POST', '/datasets', json={'name': '编排实测-' + title, 'task_type': 'chat', 'domain_type': industry, 'tags': ['chat', 'agent-real-demo', industry], 'description': 'source_kind=ai_generated_input；可人工核验参考答案；真实模型调用和裁判打分。'})
            did = row['id']
            imported = api('POST', f'/datasets/{did}/import', files={'file': ('agent-real-demo.json', json.dumps([{'input': q, 'answer': a} for q, a in pairs], ensure_ascii=False).encode(), 'application/json')})
            quality = api('POST', '/quality/run', params={'dataset_id': did, 'version_id': imported['version_id']})
            published = api('POST', f'/datasets/{did}/publish')
            data['datasets'].append({'id': did, 'name': row['name'], 'version_id': imported['version_id'], 'samples': imported['data_count'], 'quality_status': quality.get('status'), 'status': published['status']})
            save()

    if not data['resources']:
        def manifest(rid, name, endpoint, kind='tool'):
            return {'spec_version': '0.6.1', 'resource_id': rid, 'resource_type': kind, 'name': name, 'description': '开发演示真实计算服务：tools/stats_service；非Mock', 'version': '1.0.0', 'owner': {'name': 'development', 'contact': 'local', 'email': 'dev@example.local'}, 'capabilities': {'input_schema': {'type': 'object'}, 'output_schema': {'type': 'object'}, 'call_mode': 'sync', 'idempotent': True, 'timeout': 30, 'side_effects': 'none'}, 'interfaces': {'endpoint': endpoint, 'method': 'POST', 'auth_type': 'none', 'egress_allowlist': ['127.0.0.1', 'localhost']}}
        for rid, name, path in [('agentdemo/parse', '编排实测-单位解析工具', '/v1/parse'), ('agentdemo/stats', '编排实测-数值统计工具', '/v1/stats')]:
            api('POST', '/resources/register', json={'manifest': manifest(rid, name, 'http://127.0.0.1:8765'+path)})
            result = api('POST', '/resources/invoke', json={'resource_id': rid, 'correlation_id': f'agent-demo-{time.time_ns()}', 'body': {'text': '100 cm, 2 m, 500 mm'} if path.endswith('parse') else {'values': [{'value': n, 'unit': 'm'} for n in [10,20,30]], 'target_unit': 'm'}})
            data['resources'].append({'resource_id': rid, 'name': name, 'invoke_status': result.get('body', {}).get('status')})
            save()
        mcp = manifest('agentdemo/mcp_stats', '编排实测-统计MCP服务', 'http://127.0.0.1:8765/mcp', 'mcp')
        mcp['interfaces']['transport'] = 'streamable_http'
        api('POST', '/resources/register', json={'manifest': mcp})
        probe = api('POST', '/resources/mcp/probe', json={'resource_id': mcp['resource_id'], 'method': 'tools/list'})
        data['resources'].append({'resource_id': mcp['resource_id'], 'name': mcp['name'], 'probe': probe})
        save()
        workflow = manifest('agentdemo/unit_stats_skill', '编排实测-单位归一统计Skill', '', 'skill')
        workflow['interfaces'] = {'method': 'workflow', 'auth_type': 'none'}
        workflow['skill'] = {'execution_type': 'workflow', 'chain': [{'step_id': 'parse', 'resource_id': 'agentdemo/parse', 'input': {'text': {'$ref': '$input.text'}}}, {'step_id': 'stats', 'resource_id': 'agentdemo/stats', 'input': {'values': {'$ref': 'parse.output.values'}, 'target_unit': {'$ref': '$input.target_unit'}}}]}
        api('POST', '/resources/register', json={'manifest': workflow})
        result = api('POST', '/resources/invoke', json={'resource_id': workflow['resource_id'], 'correlation_id': f'agent-demo-skill-{time.time_ns()}', 'body': {'text': '100 cm, 2 m, 500 mm', 'target_unit': 'm'}})
        data['resources'].append({'resource_id': workflow['resource_id'], 'name': workflow['name'], 'invoke_status': result.get('body', {}).get('status')})
        save()

    profile = api('GET', '/agents/profile')
    profile.update(system_prompt=DEFAULT_MAIN_PROMPT, available_tools=list(MAIN_TOOLS), max_iterations=10, timeout_seconds=180, model_config={'temperature': 0, 'max_tokens': 2200})
    api('PUT', '/agents/profile', json=profile)
    definitions = [
        ('customer_coverage', '客服场景覆盖顾问', ['客服', '售后'], ['planning'], '核对客服与售后题集的业务规则、意图覆盖、参考答案和裁判适用性。比较平台真实资源，按真实ID给建议。缺少多轮、投诉、边界情况时明确指出；不要泛称覆盖完整。'),
        ('finance_verifier', '金融数值核验顾问', ['金融', '利息'], ['planning'], '核对单利、单位、舍入、数值参考答案和严格裁判风险。读取真实资源，必要时调用已绑定统计MCP验证计算；输出引用和局限。'),
        ('coverage_auditor', '数据覆盖审查员', ['数据覆盖', '覆盖审查'], ['planning'], '审查题集样本量、场景匹配、发布及质检、版本和覆盖不足；引用清单实际数据，不把12条题集视作正式业务准入充分证明。'),
        ('failure_analyst', '失败样本归因顾问', ['失败归因', '异常定位'], ['diagnosis'], '基于实际失败样本与错误区分连接、超时、格式、参考答案、评分和模型能力原因。列举样本ID、根因假设和验证步骤；恢复补测须人工确认。'),
    ]
    catalog = api('GET', '/agents/catalog')
    existing = {x['role'] for x in catalog['subagents']}
    for role, name, keywords, stages, prompt in definitions:
        body = {'role': role, 'name': name, 'description': prompt, 'system_prompt': prompt, 'max_iterations': 4, 'timeout_seconds': 180, 'available_tools': ['get_resource_inventory', 'get_task_evidence', 'search_eval_resources', 'get_task_status', 'invoke_skill', 'call_mcp'], 'skill_codes': ['clarify_goal', 'draft_report'], 'evaluation_spec': {'stages': stages, 'trigger_keywords': keywords}, 'model_config': {'temperature': 0, 'max_tokens': 1800}, 'enabled': True}
        api('PUT' if role in existing else 'POST', '/agents/definitions/'+role if role in existing else '/agents/definitions', json=body)
    data['subagents'] = [{'role': r, 'name': n, 'trigger_keywords': k, 'stages': st} for r,n,k,st,p in definitions]
    save()
    for code, title, prompt in [('coverage_matrix', '覆盖矩阵检查', '按实际数据集和样本证据，列出现有意图、缺失边界及采样局限，给出人工可执行的补充题目，不捏造样本。'), ('numeric_review', '数值口径审查', '检查货币、利率、单位、精度和裁判容错，引用实际配置；没有实测不得声称通过。'), ('report_evidence', '报告证据核对', '逐项将报告论断映射任务统计、样本ID和工具记录，标注推断、不确定性和人工审核项。')]:
        current = {x['code'] for x in api('GET', '/agents/catalog')['skills']}
        api('PUT' if code in current else 'POST', '/agents/skills/'+code if code in current else '/agents/skills', json={'code': code, 'name': title, 'entry_point': prompt, 'execution_type': 'prompt_template'})
    data['skills'] = ['coverage_matrix', 'numeric_review', 'report_evidence']
    save()
    if args.prepare_only:
        print('Resources prepared:', {k: len(data[k]) for k in ['models', 'datasets', 'resources', 'subagents', 'skills']}, flush=True)
        return

    def wait_run(rid, timeout=1500):
        deadline = time.monotonic()+timeout
        last = None
        while time.monotonic() < deadline:
            row = api('GET', f'/agents/runs/{rid}')
            state = (row['status'], row['checkpoint'].get('phase'), row['rounds_used'], row['event_seq'])
            if state != last:
                print('run', rid, state, flush=True)
                last = state
            if row['status'] in {'success','failed','paused_budget','cancelled'} or (row['status']=='waiting' and row['checkpoint'].get('phase')=='await_approval'):
                return row
            time.sleep(3)
        raise RuntimeError(f'run {rid} timed out; retained for inspection')

    scenarios = [
        '客服售后质量评测，同时做数据覆盖审查；使用“编排实测-客服售后覆盖题集”和“编排实测-通用问答模型”，裁判使用 builtin/exact_match，正式执行。请先核对授权资源和专项建议，形成实际计划；执行结束后监控、审校并优化报告。',
        '金融利息数值能力评测，使用“编排实测-金融利息核验题集”和“编排实测-数值推理模型”，裁判 builtin/exact_match，正式执行。请金融顾问通过统计MCP的compute_stats工具核验 values=[{value:30,unit:m},{value:60,unit:m},{value:90,unit:m}]、target_unit=m 的统计值（此处m仅作为计算工具单位占位，不将其解释为货币单位），再给出计划与局限，执行后优化报告。',
        '数据覆盖审查：使用“编排实测-数据覆盖基础问答题集”和“编排实测-通用问答模型”，裁判 builtin/exact_match，正式执行；关注小样本覆盖局限和报告审校。',
        '报告审校与失败归因评测：使用“编排实测-报告审校边界题集”和“编排实测-通用问答模型”，裁判 builtin/exact_match，正式执行，若出现执行异常请做异常定位，不要自动重试；输出可审核优化稿。',
    ]
    indices = [args.session_index] if args.session_index is not None else range(len(scenarios))
    for index in indices:
        previous = next((x for x in data['sessions'] if x['scenario_index']==index), None)
        if previous and previous.get('completed'):
            print('Retained completed scenario', index, previous['id'], flush=True)
            continue
        if not previous:
            available_skills = {item['code'] for item in api('GET', '/agents/catalog')['skills'] if item.get('enabled', True)}
            selected = [code for code in ['clarify_goal','recommend_params','draft_report','coverage_matrix','numeric_review','report_evidence'] if code in available_skills]
            created = api('POST', '/agents/sessions', json={'requirement': scenarios[index], 'planner_model_id': data['models'][0]['id'], 'token_budget': 500000, 'mcp_resource_ids': ['agentdemo/mcp_stats'], 'subagent_roles': ['monitor','diagnose','plan_analyst','param_advisor','report_reviewer','report_optimizer'], 'skill_codes': selected})
            previous = {'id': created['id'], 'scenario_index': index, 'planning_run_id': created['active_run_id']}
            data['sessions'].append(previous)
            save()
        sid = previous['id']
        planned = wait_run(previous['planning_run_id'])
        previous['planning_status'] = planned['status']
        save()
        if planned['status'] == 'paused_budget':
            previous.setdefault('budget_paused_run_ids', []).append(planned['id'])
            api('POST', f'/agents/sessions/{sid}/clarify', json={'token_budget': 500000})
            continued = api('POST', f'/agents/sessions/{sid}/runs', json={'message': scenarios[index] + ' 请复用此前已经完成的专项分析，不重复调用规划子Agent。先用propose_resources核对并写入指定资源，然后给出计划或请求审批。', 'provider': 'live', 'planner_model_id': data['models'][0]['id'], 'max_rounds': 8, 'token_budget': 500000, 'sync': False})
            previous['planning_run_id'] = continued['id']
            save()
            planned = wait_run(continued['id'])
            previous['planning_status'] = planned['status']
            save()
        if planned['status'] in {'failed','paused_budget','cancelled'}:
            print('Planning failed', planned.get('error_message'), flush=True)
            continue
        session = api('GET', f'/agents/sessions/{sid}')
        previous['plan_resources'] = {k: session['plan'].get(k) for k in ['dataset_id','model_id','judge_resource_id','ready','analysis_status']}
        save()
        if not session['plan'].get('ready'):
            print('Actual plan requires clarification', session['plan'].get('clarifications'), flush=True)
            continue
        if not session.get('task_id'):
            approved = api('POST', f'/agents/sessions/{sid}/approve', json={})
            confirmed = api('POST', f'/agents/sessions/{sid}/confirm', json={'approval_id': approved['approval']['id'], 'execute': True, 'client_invocation_id': f'agent-real-demo-{sid}'})
            previous['task_id'] = confirmed['task_id']
            save()
        deadline=time.monotonic()+1500
        while time.monotonic()<deadline:
            session=api('GET', f'/agents/sessions/{sid}')
            rid=session.get('active_run_id') or session.get('last_run_id')
            current=api('GET', f'/agents/runs/{rid}')
            if session.get('task_status') in {'success','failed','partial_failed','cancelled','paused_budget'} and current['status'] in {'success','failed','paused_budget','cancelled'}:
                break
            print('tracking', sid, session.get('task_status'), current['status'], current['event_seq'], flush=True)
            time.sleep(8)
        previous['task_status']=session.get('task_status')
        previous['final_run_id']=rid
        previous['final_run_status']=current['status']
        previous['completion']=current.get('completion')
        delegations=api('GET',f'/agents/sessions/{sid}/delegations')
        previous['delegations']=[{'id':x['id'],'role':x['role'],'status':x['status'],'run_id':x.get('run_id'),'event_count':len(x.get('evidence') or [])} for x in delegations['items']]
        revisions=api('GET',f'/agents/sessions/{sid}/report-revisions')
        previous['report_revision_ids']=[x['id'] for x in revisions['items']]
        previous['completed']=session.get('task_status') in {'success','failed','partial_failed'} and current['status'] in {'success','failed'} and current.get('completion', {}).get('kind') in {'evaluation_completed', 'evaluation_unverified'}
        save()
        print('Scenario retained',previous,flush=True)


if __name__=='__main__':
    main()
