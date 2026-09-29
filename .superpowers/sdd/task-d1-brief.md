# D Task 1：六态纯函数 + PageAsyncState

Work from E:\eval-platform. No git commit.

Create:
- frontend/src/utils/asyncState.js
- frontend/src/components/PageAsyncState.vue
- frontend/tests/unit/asyncState.test.mjs

```javascript
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
```

PageAsyncState.vue:
- props: state, errorMessage
- For loading/error/forbidden/empty/uncreated: show StatusBadge (phase maps: loading->running, error->failed, forbidden->blocked, empty->idle, uncreated->idle) PLUS the title and next text. Never color-only.
- For success: default slot.
- No Mock slogans.

Tests: all six branches; forbidden wins over loading; createdOnce empty vs uncreated.

Run from frontend: npm run test:unit
If verify:ux-static is fast, run it too.

Report .superpowers/sdd/task-d1-report.md
