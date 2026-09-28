# Project Instructions

## Permission Workflow

When adding a page, button, or API that needs permission control, complete the related permission updates in the same change.

1. Frontend buttons/pages
   - For buttons, add `v-if="userStore.hasPermission('resource:action')"` or `v-permission="'resource:action'"`.
   - For routes, declare the permission code in `meta.permission`.

2. Backend APIs
   - Use `require_permission("resource:action")` on the matching route.

3. `backend/app/permissions.json`
   - Add the new permission to the `permissions` array.

4. `backend/app/services/permission_loader.py`
   - If the action is not already in `ACTION_NAMES`, add it there.

5. `backend/app/services/rbac.py`
   - Add the new permission to `RESEARCHER_PERMISSIONS` and `VIEWER_PERMISSIONS` according to business needs.

6. Run permission collection.

```bash
cd frontend && npm run collect-permissions
```

Permission code format: `resource:action`. Keep resource aligned with modules such as `dashboard`, `user`, `role`, `notification`, `audit`, `ops`.

## Hard rules

- Tests must use `tests/isolated_env.py` (or equivalent); never point tests at the business `eval_platform.db`.
- Do not mark Mock / hardcoded `ok=True` / unmeasured admission items as formal pass.
- Production (`APP_ENV=production`): non-default `SECRET_KEY`; no default `admin123` bootstrap.
- Agent must not write scheduler internals or scoring facts directly; use gated tools / TaskService.

## Doc pointers

| Need | Where |
| --- | --- |
| WP delivery status | `docs/delivery/STATUS.md` |
| M4 handoff / open gaps | `docs/delivery/MILESTONE-M4.md` |
| Ops runbook | `docs/operations/` |
| Design / acceptance | `docs/implementation-plan-2026-09-28/` |
