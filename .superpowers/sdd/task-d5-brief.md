# D Task 5：详情与其余页

Work from E:\eval-platform. No git commit. TDD. Do not start Task 6 evidence screenshots unless you have time after verify commands.

Use `deriveAsyncState` + `PageAsyncState` + EmptyState. No Mock slogans. Never catch → items=[] without error. No new permission codes unless you must (prefer `user:edit` for disable).

## Must

### TaskDetail.vue
`tasksApi.results` currently `{ page_size: 100 }` as dump. Add `page`/`page_size`/`total` pager (always visible after success). load() catch → `loadError` + PageAsyncState; do not render empty results as success.

### DatasetDetail.vue
`loadDetail`/`loadItems` catch → `loadError`. Sample pager: remove `v-if="itemTotal > itemPageSize"`; always show pager or 「第 x 页」. Failure must not look like zero samples.

### Dashboard.vue
Failed-tasks card: successful empty → EmptyState (not a naked hint that could be confused with load fail). loadError already hides content (keep that).

### Leaderboard.vue
Remove independent "obs" marketing skin as the page identity: use the same `page-header` + `el-card`/`el-button`/`el-table` patterns as other pages. Colors from `var(--text-primary)` / `var(--bg-card)` / `var(--el-color-primary)` etc., not a separate copper/glow theme as the only look. Keep publish/refresh/rollback/export actions and filters. Add loading/error/empty via PageAsyncState. Keep English kicker "Cohort · Frozen Scale" only if it is operational; otherwise Chinese product copy. No Mock slogans.

### TaskTemplates.vue
EmptyState when items empty after success. loadError + PageAsyncState on failure. Keep category catalog.

### Remaining pages — each needs load/fail/empty:
- Benchmarks.vue
- Safety.vue
- Ops.vue (status/backup sections)
- RolePermission.vue
- NotificationManage.vue (list catch + PageAsyncState; usersLoadError already exists)
- ApiDocs.vue (if swagger fail, show error + next step, not blank host)
- Profile.vue
- Login.vue: keep submit lock (`loading`); show login error on the form (not only toast). Do not swallow catch with empty body.

### AuditLog.vue
There is **no** `/audit/export` API (`auditApi` is list-only). Add a **disabled** export button with title/hint: `当前环境未开放导出`. **Forbidden** wording: `API 未完整开放` / `API 尚未完整开放`.

### Users.vue
Backend `UserUpdate.status` is `active|disabled`. Add 禁用/启用 using `usersApi.update(id, { status })` behind `user:edit`. Confirm before disable. **Do not invent invite.** `creatorOptions` catch must set an error flag (same rule).

## Tests

`frontend/tests/unit/remainingPages.test.mjs` source asserts:
- TaskDetail results call includes `page` and not only `page_size: 100` dump
- DatasetDetail has loadError; no `itemTotal > itemPageSize`
- Leaderboard uses `page-header` or `PageAsyncState`; fewer raw `#` hex skins in style is optional
- AuditLog contains `当前环境未开放导出` and not `API 尚未完整开放`
- Users.vue contains `status: 'disabled'` or `status: \"disabled\"` update
- Login.vue catch is not empty (`if (e?.errors) return` alone is not enough — must set form error or displayMsg)

## Verify

cd frontend
npm run test:unit
npm run verify:ux-static

Report `.superpowers/sdd/task-d5-report.md`
Do not git commit. Do not start Task 6 unless tests pass and you only add the evidence markdown stub.
