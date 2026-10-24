"""Human readable tool names, independent of execution identifiers."""
JUDGE_NAMES = {
    'builtin/exact_match': '精确匹配', 'builtin/contains': '关键词包含',
    'builtin/regex': '正则匹配', 'builtin/fuzzy': '文本相似度',
    'builtin/safety_gen_risk': '生成内容风险检测', 'builtin/safety_watermark': '合成标识检测',
    'builtin/safety_alignment': '价值对齐评测', 'builtin/safety_hallucination': '幻觉检测',
}

def judge_name(resource_id):
    return JUDGE_NAMES.get(resource_id, '自定义评测工具' if resource_id else '未配置')
