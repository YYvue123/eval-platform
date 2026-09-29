# D Task 2：listQuery 与 request 静默

Work from E:\eval-platform. No git commit. TDD. Follow task-d1 style tests (node:test).

## 1. frontend/src/utils/listQuery.js (new)

```javascript
export function readListQuery(query = {}) {
  const page = Math.max(1, Number.parseInt(query.page, 10) || 1)
  let page_size = Number.parseInt(query.page_size, 10)
  if (!Number.isFinite(page_size) || page_size < 1) page_size = 20
  page_size = Math.min(100, page_size)
  const q = typeof query.q === 'string' ? query.q : ''
  const status = typeof query.status === 'string' ? query.status : ''
  return { page, page_size, q, status }
}

export async function writeListQuery(router, patch) {
  const current = { ...(router.currentRoute.value.query || {}) }
  const next = { ...current, ...patch }
  for (const key of Object.keys(next)) {
    const v = next[key]
    if (v === '' || v == null) delete next[key]
    else next[key] = String(v)
  }
  return router.replace({ query: next })
}
```

Tests frontend/tests/unit/listQuery.test.mjs:
- missing query → page 1, page_size 20, q '', status ''
- page=0 or NaN → 1
- page_size=500 → 100
- writeListQuery merges and drops empty keys; call a fake router with currentRoute.value.query and replace

## 2. frontend/src/utils/request.js

In the response error interceptor, if `error.config?.skipErrorToast` is true (also check `error.response?.config?.skipErrorToast`), do NOT call ElMessage.error. Still logout+redirect on 401 (except auth endpoints). Always reject.

401 auth endpoints currently toast — skipErrorToast should still suppress that toast if set.

Network errors (no response): also honor skipErrorToast.

## 3. NotificationCenter polling — skipErrorToast

Change `notificationsApi.getUnreadCount` to:
`request.get('/notifications/mine/unread-count', { skipErrorToast: true })`

Optional: store.fetchUnreadCount already swallows; that is OK for poll. Do not leave poll toasting.

Do NOT silently empty fetchList without tracking error if you touch it; polling change is unread-count.

## 4. Forbidden silent-empty pattern — MUST set error

### Dashboard.vue
Current onMounted catch sets stats={} and empty workbench arrays — FORBIDDEN.
- Add `loadError` ref (string).
- On failure: set loadError to message; do not pretend workbench is a successful empty list.
- On success: clear loadError.
- Template: if loadError, show PageAsyncState state="error" :errorMessage="loadError" (or equivalent title+next). Do not show EmptyState "暂无待办" as if the request succeeded.

### Agents.vue loadList
Current: `modelsApi.list(...).catch(() => ({ items: [] }))` — FORBIDDEN.
- If models list fails, set `modelsLoadError` (string) and plannerModels=[] only together with that error shown near the planner model select.
- Sessions list failure should also set an error, not look like "暂无会话".
- Do NOT auto-change plannerModelId defaulting in this task beyond existing behavior (Task 3 removes items[0] default).

### NotificationManage.vue loadUsers
Current catch sets users=[] — FORBIDDEN.
- Set `usersLoadError`; show it near the audience/user select in create form. Empty users only with error text.

## 5. Comment/doc in listQuery.js header

One-line: page catch must not assign items=[] without setting an error flag.

## Verify

cd frontend; npm run test:unit
npm run verify:ux-static if fast

Report .superpowers/sdd/task-d2-report.md
Do not start Task 3 (403/slogans).
