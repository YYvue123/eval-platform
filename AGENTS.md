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

Permission code format: `resource:action`. Keep resource aligned with modules such as `dashboard`, `user`, `role`, `notification`, `audit`.
