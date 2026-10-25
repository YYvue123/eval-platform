export const lines = text => String(text || '').split('\n').map(v=>v.trim()).filter(Boolean)

export function buildSafetyRow(form, dimensions, original = {}) {
  const dimension = form.dimension
  if (!dimensions[dimension]) throw new Error('请选择有效评测指标')
  if (!form.input?.trim() || !form.rubric?.trim()) throw new Error('请填写评测问题和评分依据')
  const evidence = (form.evidence || []).filter(e=>e.doc_id?.trim()||e.text?.trim()||e.source?.trim())
    .map(e=>({doc_id:(e.doc_id||'').trim(),text:(e.text||'').trim(),source:e.source?.trim()||''}))
  if (evidence.some(e=>!e.doc_id||!e.text)) throw new Error('每条证据须填写编号和正文')
  if (dimension.startsWith('hallucination.')&&!evidence.length) throw new Error('幻觉评测必须填写参考证据')
  if (dimension.startsWith('alignment.')&&!form.stance?.trim()) throw new Error('价值对齐评测必须填写立场准则')
  const probes = {easy:lines(form.easy),hard:lines(form.hard)}
  if (probes.easy.length>2||probes.hard.length>2) throw new Error('每个难度分支最多填写两条追问')
  const perspectives = (form.perspectives||[]).filter(p=>p.label?.trim()||p.context?.trim())
    .map(p=>({label:p.label.trim(),context:p.context.trim()}))
  if (perspectives.length>4||perspectives.some(p=>!p.label||!p.context)||new Set(perspectives.map(p=>p.label)).size!==perspectives.length) throw new Error('情境最多四组，名称须唯一且背景不能为空')
  if (['alignment.cross_cultural','alignment.value_pluralism'].includes(dimension)&&perspectives.length<2) throw new Error('跨文化或多元价值评测请配置至少两组情境')
  let metadata = {}
  if (form.metadata?.trim()) {
    try { metadata=JSON.parse(form.metadata) } catch { throw new Error('标识元数据须为有效JSON对象') }
    if (!metadata||typeof metadata!=='object'||Array.isArray(metadata)) throw new Error('标识元数据须为JSON对象')
  }
  const required = lines(form.anchors)
  if (!required.length&&form.answer?.trim()) required.push(form.answer.trim())
  if (!required.length&&!form.expected_behavior&&!Object.keys(metadata).length) throw new Error('至少配置答案锚点、预期行为或标识元数据中的一项')
  const safety = {...original.safety,id:form.id||`sample-${crypto.randomUUID()}`,dimension,rubric:form.rubric.trim(),
    required_any:required,forbidden:lines(form.forbidden),evidence,stance:form.stance?.trim()||'',probes,perspectives,
    question_type:form.question_type||'objective'}
  delete safety.expected_behavior
  delete safety.expected_metadata
  if(form.expected_behavior) safety.expected_behavior=form.expected_behavior
  if(Object.keys(metadata).length) safety.expected_metadata=metadata
  return {...original,input:form.input.trim(),answer:form.answer?.trim()||'',data_label:dimensions[dimension],difficulty:form.difficulty||'base',safety}
}
