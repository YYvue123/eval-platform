"""Incremental staging examples: real calls, versioned snapshots, K12/finance and review workflow."""
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx
from sqlalchemy.engine import make_url

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.config import settings

LANGUAGE=[
 ('学科知识','用一句话解释水沸腾的条件。','水的饱和蒸气压达到外界压强时会沸腾。'),
 ('学科知识','用一句话解释月亮为什么发光。','月亮反射太阳光，因此看起来会发光。'),
 ('逻辑推理','用一句话解释连续三个整数的和为什么能被3整除。','三个连续整数的和可表示为3n加3，因此能被3整除。'),
 ('逻辑推理','用一句话解释两个奇数的和为什么是偶数。','奇数表示为2a加1和2b加1，相加含有因子2，因此是偶数。'),
 ('代码理解','用一句话解释 Python 的集合为什么能用于列表去重。','集合只保存互不重复的元素，因此可用于去除列表中的重复值。'),
 ('代码理解','用一句话解释浅拷贝和深拷贝的区别。','浅拷贝保留嵌套对象的引用，深拷贝递归复制嵌套对象。'),
 ('阅读理解','阅读这段话并概括原因：由于连续大雨导致道路积水，学校决定周五改为线上授课。','学校因大雨积水而改为线上授课。'),
 ('阅读理解','概括这段话：图书馆周末延长开放两小时，并新增线上预约座位服务。','图书馆延长周末开放时间并提供线上预约。'),
 ('指令遵循','用中文一句话说明如何把摄氏温度转换为华氏温度，不要举例。','将摄氏温度乘以1.8后再加32，得到华氏温度。'),
 ('指令遵循','用中文一句话解释平均数的计算方式，不要给出具体例子。','将所有数值求和后除以数值个数，即得到平均数。'),
 ('信息提取','提取活动时间和地点：读书分享会将于周六下午三点在社区图书馆举行。','时间是周六下午三点，地点是社区图书馆。'),
 ('信息提取','提取数量和覆盖范围：城市新增三条公交线，覆盖五个社区，预计下月开通。','新增三条公交线，覆盖五个社区。'),
]
K12=[
 ('语文','填空：床前明月光，疑是地上什么？只输出最后一个字。','霜'),
 ('语文','成语画蛇添足中，添的意思是什么？只输出一个字。','加'),
 ('数学','计算 17 乘以 23，只输出十进制整数。','391'),
 ('数学','解方程 3x 加 6 等于 21，只输出 x 的值。','5'),
 ('英语','把英文单词 apple 翻译成中文，只输出译文。','苹果'),
 ('英语','填写英文单词 child 的复数形式，只输出单词。','children'),
 ('物理','国际单位制中力的单位名称是什么？只输出中文名称。','牛顿'),
 ('物理','一物体以每秒5米匀速运动6秒，路程是多少米？只输出数字。','30'),
 ('化学','水的化学式是什么？只输出化学式，不要使用下标字符。','H2O'),
 ('化学','化学元素金的元素符号是什么？只输出符号。','Au'),
 ('历史','秦统一六国后确立的最高统治者称号是什么？只输出两个汉字。','皇帝'),
 ('历史','造纸术、印刷术、火药、指南针中，用于辨别方向的是哪一种？只输出名称。','指南针'),
]
FINANCE=[
 ('指标计算','某示例本金1000元，单期利率2%，按单利计算一期利息。只输出数字，不要单位。','20'),
 ('指标计算','示例价格从100变为110，涨幅百分数是多少？只输出数字，不要百分号。','10'),
 ('表格分析','示例三个部门费用分别为120、80、50，总费用是多少？只输出数字。','250'),
 ('表格分析','示例三个账户余额为100、200、300，平均余额是多少？只输出数字。','200'),
 ('规则遵循','假设内部规则要求金额大于1000必须复核，金额1500是否必须复核？只输出是或否。','是'),
 ('规则遵循','假设内部规则要求金额大于1000必须复核，金额500是否必须复核？只输出是或否。','否'),
 ('风险识别','按本题规则，连续三次密码错误标记为高风险。记录已经连续错误三次。只输出高风险或低风险。','高风险'),
 ('风险识别','按本题规则，连续三次密码错误标记为高风险。记录第一次正确登录。只输出高风险或低风险。','低风险'),
]


def main():
    if settings.APP_ENV!='staging' or not settings.DATABASE_URL.startswith('sqlite'):
        raise SystemExit('Requires configured staging SQLite; no production or mock fallback.')
    path=Path(make_url(settings.DATABASE_URL).database).resolve()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    backup=ROOT/'backups'/f'before-leaderboard-v2-{stamp}.db'
    backup.parent.mkdir(exist_ok=True)
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(backup) as dst:src.backup(dst)
    core=['datasets','dataset_versions','dataset_items','eval_tasks','eval_results']
    with sqlite3.connect(backup) as saved:
        before={table:{r[0]:hashlib.sha256(repr(r).encode()).hexdigest() for r in saved.execute(f'SELECT * FROM {table}')} for table in core}
        old_models=dict(saved.execute("SELECT id,name FROM eval_models WHERE status!='deleted' AND tenant_id=(SELECT tenant_id FROM users WHERE username='admin')"))
    print(json.dumps({'phase':'backup_ready','backup':str(backup)}),flush=True)
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120) as c:
        def call(method,url,**kwargs):
            r=c.request(method,'/api'+url,**kwargs)
            if r.status_code!=200:raise RuntimeError(f'{method} {url}: HTTP {r.status_code}')
            return r.json()
        auth=call('POST','/auth/login',json={'username':'admin','password':os.environ.get('DEMO_ADMIN_PASSWORD') or 'admin123'})
        c.headers['Authorization']='Bearer '+auth['access_token']
        models=call('GET','/models',params={'page_size':200})['items']
        if {m['id']:m['name'] for m in models}!=old_models:raise RuntimeError('API inventory differs from target staging DB')
        aliases=[next(m for m in models if m['name']==f'[演示配置] {name}') for name in ['稳健','均衡','探索']]
        datasets=call('GET','/datasets',params={'page_size':200})['items']
        def dataset(name,samples,tags,industry):
            existing=next((d for d in datasets if d['name']==name),None)
            if existing:return existing['id']
            d=call('POST','/datasets',json={'name':name,'tags':tags,'domain_type':industry,'description':'客户演示：人工编写的小样本题集，仅用于验证展示与交互，不等同公开基准或能力认证。'})
            payload=[{'input':q,'reference':a,'data_label':dim,'grade':'七年级' if 'K12' in name else '', 'sample_origin':'hand_authored_demo'} for dim,q,a in samples]
            call('POST',f"/datasets/{d['id']}/import",files={'file':('examples.json',json.dumps(payload,ensure_ascii=False).encode(),'application/json')})
            call('POST','/quality/run',params={'dataset_id':d['id']})
            call('POST',f"/datasets/{d['id']}/publish")
            return d['id']
        language=dataset('榜单V2 · 六维语言（文本相似度示例）',LANGUAGE,['language','demo'],'general')
        k12=dataset('榜单V2 · K12 学科基础题（演示）',K12,['k12','demo'],'education')
        finance=dataset('榜单V2 · 金融基础规则（非交易回测）',FINANCE,['finance','demo'],'finance')
        tasks=call('GET','/tasks',params={'page_size':200,'search':'榜单V2-'})['items']
        evidence=[]
        def execute(mid,dsid,round_no,judge='builtin/fuzzy',industry='general',task_type='capability'):
            name=f'榜单V2-{mid}-{dsid}-R{round_no}'
            t=next((t for t in tasks if t['name']==name),None)
            if not t:t=call('POST','/tasks',json={'name':name,'model_id':mid,'dataset_id':dsid,'scene':'chat','industry':industry,'task_type':task_type,'judge_resource_id':judge,'token_quota':20000})
            if t['status']=='draft':
                call('POST',f"/tasks/{t['id']}/submit")
                call('POST',f"/tasks/{t['id']}/audit",json={'approved':True,'comment':'真实模型客户演示，按用户授权增量执行'})
            if t['status'] not in {'success','running'}:call('POST',f"/tasks/{t['id']}/run")
            deadline=time.monotonic()+600
            while True:
                t=call('GET',f"/tasks/{t['id']}")
                if t['status'] not in {'running','queued','pending_review'}:break
                if time.monotonic()>deadline:raise RuntimeError('Evaluation timeout; inspect task, never fabricate pass')
                time.sleep(1)
            if t['status']!='success' or t.get('simulation'):raise RuntimeError(f"Real evaluation task {t['id']} did not succeed")
            evidence.append({k:t.get(k) for k in ['id','name','status','avg_score','tokens_used','simulation']})
            print(json.dumps({'phase':'measured','task_id':t['id'],'completed':len(evidence)}),flush=True)
            return t
        def snapshot(cohort,title,board='overall',metric=''):
            existing=call('GET','/leaderboard/publications',params={'cohort_id':cohort})['items']
            row=next((p for p in existing if p['title']==title),None)
            return row or call('POST','/leaderboard/publications',json={'cohort_id':cohort,'board':board,'metric':metric,'title':title,'public':False})
        for round_no in (1,2):
            for m in aliases:execute(m['id'],language,round_no)
            data=call('GET','/leaderboard/insights',params={'category':'language'})
            group=next(g for g in data['cohorts'] if g['dataset_name'].startswith('榜单V2 · 六维语言'))
            cid=group['id']
            if round_no==1:
                snapshot(cid,'2026年10月 · 六维语言 · 第一期（演示）')
            else:
                live=call('GET','/leaderboard/insights',params={'cohort_id':cid})
                call('PUT','/leaderboard/policy',json={'cohort_id':cid,'weights':{d:2 if d=='逻辑推理' else 1 for d in live['dimensions']}})
                snapshot(cid,'2026年10月 · 六维语言 · 第二期（演示）')
                snapshot(cid,'2026年10月 · 逻辑推理单项（演示）','ability','逻辑推理')
                snapshot(cid,'2026年10月 · 性价比（演示）','value')
        for dsid,industry in [(k12,'education'),(finance,'finance')]:
            for m in aliases:execute(m['id'],dsid,1,'builtin/exact_match',industry,'industry')
            data=call('GET','/leaderboard/insights',params={'board':'special','industry':industry})
            group=next(g for g in data['cohorts'] if g['dataset_name'].startswith('榜单V2'))
            snapshot(group['id'],f'2026年10月 · {"K12学科" if industry=="education" else "金融规则"}专项（演示）','special')
        # A genuine new run awaiting manual verification; no invented anomaly or modified score.
        pending=execute(aliases[0]['id'],language,3)
        reviews=call('GET','/leaderboard/reviews')['items']
        if not any(r['task_id']==pending['id'] for r in reviews):
            call('POST','/leaderboard/reviews',json={'task_id':pending['id'],'reason':'人工复核流程演示：请核对该轮输出与词面相似度评分；尚未判定异常。'})
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as current:
            preservation={}
            for table,records in before.items():
                after={r[0]:hashlib.sha256(repr(r).encode()).hexdigest() for r in current.execute(f'SELECT * FROM {table}')}
                if any(after.get(key)!=digest for key,digest in records.items()):raise RuntimeError(f'Original rows changed in {table}; inspect backup')
                preservation[table]={'before':len(records),'after':len(after),'original_content_unchanged':True}
        output=ROOT.parent/'docs/delivery/leaderboard-v2-staging-evidence.json'
        output.write_text(json.dumps({'backup':str(backup),'tasks':evidence,'preservation':preservation,'public_access_enabled':False,'review_example_task_id':pending['id']},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'phase':'complete','tasks':len(evidence),'evidence':str(output)}),flush=True)

if __name__=='__main__':main()
