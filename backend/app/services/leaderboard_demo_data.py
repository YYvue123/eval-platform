"""Synthetic UI examples only; never persisted into eval_tasks/eval_results."""
from datetime import datetime, timedelta

DIMENSIONS = {
    'vision':['物体识别','场景理解','文字识别','空间关系','图表理解','视觉推理'],
    'video':['动作识别','时序理解','事件定位','场景变化','视频摘要','跨帧推理'],
    'audio':['语音识别','说话人区分','语种识别','情绪识别','语音理解','噪声鲁棒性'],
    'safety':['有害内容防护','越狱防护','隐私保护','事实可靠性','偏见与公平','合规拒答'],
}
NAMES = {'vision':'图像','video':'视频','audio':'语音','safety':'安全可信'}

def demo_payload(category):
    dims=DIMENSIONS[category];now=datetime.utcnow();items=[];history=[]
    for i in range(3):
        scores=[round(.53+((j*7+i*11)%37)/100,2) for j in range(6)]
        key=f'demo-{category}-{i}'
        items.append({'key':key,'model_id':key,'model_name':f'[模拟展示] {NAMES[category]}模型{chr(65+i)}','version':'演示版本',
            'company':'虚构模型 · 非真实厂商','source_type':['open','closed','open'][i],'demo_alias':True,
            'description':'仅用于展示交互的合成示例，无实际模型调用和正式评测证据。','sample_count':60,'score':sum(scores)/6,
            'dimensions':{d:{'score':s,'count':10,'expected':10} for d,s in zip(dims,scores)},'pass_rate':.7+i*.04,
            'latency_ms':650+i*320,'p95_latency_ms':1000+i*400,'cost':.03+i*.01,'tokens':0,'simulation':True,'updated_at':now.isoformat()})
        for period in range(4):
            history.append({'key':key,'score':round(sum(scores)/6-(3-period)*.025,4),'at':(now-timedelta(days=7*(3-period))).isoformat()})
    return {'items':items,'history':history,'dimensions':dims,'scale':{'min':0,'max':1,'unit':'演示比例'},
        'cohort_id':f'demo-{category}','cohorts':[{'id':f'demo-{category}','dataset_name':f'{NAMES[category]}六维模拟数据','label':f'{NAMES[category]}六维模拟数据','judge_name':'模拟指标，无真实评分器','count':3}],
        'profiles':[{'key':r['key'],'model_name':r['model_name'],'source_type':r['source_type'],'cells':{f'demo-{category}':{'score':r['score'],'samples':60}}} for r in items],
        'simulation':True,'category':category,'categories':{key:3 for key in DIMENSIONS},'overview':{'models':3*len(DIMENSIONS),'runs':0},
        'industries':[],'scenes':[],'model_options':[],'version_options':[],'pending_review_total':0,'excluded_total':0,
        'rules':'所有模型、分数、样本数、费用与趋势均为合成展示数据。未执行模型调用，不属于正式评测结果，不可发布。'}
