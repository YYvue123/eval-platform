export function deriveAsyncState({ loading, error, forbidden, items, createdOnce }) {
  if (forbidden) return 'forbidden'
  if (loading) return 'loading'
  if (error) return 'error'
  const list = Array.isArray(items) ? items : items == null ? [] : [items]
  const emptyList = list.length === 0
  if (emptyList && createdOnce) return 'empty'
  if (emptyList && !createdOnce) return 'uncreated'
  return 'success'
}

export const ASYNC_STATE_COPY = {
  loading: { title: '正在加载', next: '请稍候。' },
  error: { title: '加载失败', next: '检查网络后重试，已填写内容会保留。' },
  forbidden: { title: '没有权限', next: '请联系管理员开通后刷新本页。' },
  empty: { title: '没有符合条件的结果', next: '调整筛选条件，或清空筛选后重试。' },
  uncreated: { title: '还没有记录', next: '使用页面上的主要动作创建第一条。' },
  success: { title: '已加载', next: '' },
}
