# D Task 4：列表页分页与 URL

Work from E:\eval-platform. No git commit. TDD. Do not start Task 5.

Use existing `readListQuery` / `writeListQuery` from `frontend/src/utils/listQuery.js` and `deriveAsyncState` + `PageAsyncState`.

## Shared list pattern (copy per page)

For Datasets, Tasks, Quality (reports+issues), Prompts, EvalServices, Users, AuditLog:

1. Init `page/page_size/q/status` from `readListQuery(route.query)` (map local search field to `q`).
2. On load and on pager/filter change: `writeListQuery(router, { page, page_size, q, status })` then fetch with those params. Extra filters (domain, role, dates) may also go into query as extra keys via writeListQuery patch.
3. **Always show pager** (or a line `第 {{ page }} 页 · 共 {{ total }} 条`) even when `total <= pageSize`. Remove `v-if="total > pageSize"` (Datasets, Users). Tasks already shows when total>0; keep pager visible after successful load including total===0 if you show empty state.
4. `loadError` on catch; never `items=[]` without error. Set `createdOnce=true` only after a successful response.
5. Template: if listState is loading/error/forbidden/uncreated → `PageAsyncState`. If empty/success → table; table `#empty` can keep EmptyState. Do not show EmptyState when loadError.
6. Watch `route.query` so back-navigation restores page/q/status.

## Page-specific

### Quality.vue
Stop `page_size: 50` as full dump. Reports: `page`, `page_size`, `total`. Issues tab: same. Rules table may stay unpaged if API has no paging (document in report). EmptyState + pager.

### Prompts.vue
`promptsApi.list({ page, page_size, search })` + total + pager + URL. Remove relying on 50 as complete set. Keep EmptyState.

### EvalServices.vue
`servicesApi.list({ page, page_size })` + total + pager + URL. Kanban/workspaces can stay separate requests; workspace default first item is OK (not a user-facing model pick).

### Datasets.vue / Tasks.vue / Users.vue / AuditLog.vue
Already paged; add URL sync + always-visible pager + PageAsyncState + error flags. Users.vue currently catch sets items=[] without error — **must fix**.

## ResourcePicker.vue

Do not treat first 30 as full catalog.

- Keep `page` cursor (start 1). `search()` resets to page 1 and replaces options.
- If `res.total > options.length` OR `(res.items||[]).length === page_size`, show a last **el-option disabled=false** labeled `加载更多` with a sentinel value like `'__more__'`.
- On selecting `__more__`: prevent model update; fetch `page+1` with same q; **append** unique options; increment page.
- Alternatively dropdown scroll-to-bottom loads next page (either approach OK).
- hydrateCurrent still fetches the selected id if missing from options. Catch may ignore missing current, but list search failure must set `loadError` shown under the select.

## Tests

`frontend/tests/unit/listPages.test.mjs` source asserts:

- Datasets.vue and Users.vue: no `v-if="total > pageSize"`
- Quality/Prompts/EvalServices: `page_size: 50` as sole list fetch is gone; they pass `page` and `page_size` and read `total`
- Those seven views: `writeListQuery` or `readListQuery` present
- ResourcePicker: page increment or `加载更多` / `__more__`
- Users.vue: `loadError` (or equivalent) in catch

## Verify

cd frontend; npm run test:unit
npm run verify:ux-static

Do not rewrite unrelated dialogs. No git commit.

Report `.superpowers/sdd/task-d4-report.md`
