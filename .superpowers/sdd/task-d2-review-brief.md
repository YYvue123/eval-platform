# Spec review D Task 2

Read:
- docs/superpowers/plans/2026-09-29-subproject-d-frontend.md Task 2
- .superpowers/sdd/task-d2-brief.md
- .superpowers/sdd/task-d2-report.md
- frontend/src/utils/listQuery.js
- frontend/src/utils/request.js
- frontend/src/api/index.js (getUnreadCount)
- frontend/src/views/Dashboard.vue
- frontend/src/views/Agents.vue (loadList)
- frontend/src/views/NotificationManage.vue (loadUsers)
- frontend/tests/unit/listQuery.test.mjs

Must:
- readListQuery/writeListQuery as specified
- skipErrorToast no ElMessage; 401 still logout except auth endpoints; always reject
- getUnreadCount skipErrorToast
- Dashboard/Agents/NotificationManage fail set error, not silent items=[]
- Dashboard must not show EmptyState 暂无待办 on load failure

Output .superpowers/sdd/task-d2-review.diff: Approved or Needs fixes with file/line/command.

Do not implement. No git commit.
