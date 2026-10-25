export const reviewText = value => ({ approved: '通过', rejected: '驳回', needs_evidence: '需补证' }[value] || '未提交')
export const taskStatusText = value => ({ draft: '草稿', pending_review: '待审核', queued: '排队中', running: '执行中', success: '已完成', failed: '失败', partial_failed: '部分失败', cancelled: '已取消', paused_budget: '预算暂停' }[value] || value)
export const scoreStatusText = value => ({ scored: '已评分', error: '评分失败', skipped: '未评分', legacy_unverified: '待验证' }[value] || '未评分')
export const datasetStatusText = value => ({ published: '已发布', draft: '草稿', pending_review: '待审核', approved: '已审核', archived: '已归档' }[value] || value)

// Integer hundredths distribute rounding remainders so presets total exactly 100%.
export function percentageWeights(values) {
  const entries = Object.entries(values)
  if (entries.some(([,value]) => !Number.isFinite(Number(value)) || Number(value) < 0)) return {}
  const total = entries.reduce((sum, [,value]) => sum + Number(value), 0)
  if (!entries.length || !Number.isFinite(total) || total <= 0) return {}
  const portions = entries.map(([key,value]) => ({ key, raw: Number(value) / total * 10000 }))
  const result = Object.fromEntries(portions.map(p => [p.key, Math.floor(p.raw)]))
  const remainder = 10000 - Object.values(result).reduce((sum,value) => sum + value, 0)
  portions.sort((a,b) => (b.raw-Math.floor(b.raw)) - (a.raw-Math.floor(a.raw)))
  for (let index=0; index<remainder; index++) result[portions[index].key]++
  return Object.fromEntries(Object.entries(result).map(([key,value]) => [key,value/100]))
}

export function validPercentages(weights) {
  const values = Object.values(weights)
  return values.length > 0 && values.every(v => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 100)
    && values.reduce((sum,v) => sum + Math.round(v*100), 0) === 10000
}
