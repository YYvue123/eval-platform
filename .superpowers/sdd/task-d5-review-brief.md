# Spec review D Task 5

Read:
- docs/superpowers/plans/2026-09-29-subproject-d-frontend.md Task 5
- .superpowers/sdd/task-d5-brief.md
- .superpowers/sdd/task-d5-report.md
- frontend/tests/unit/remainingPages.test.mjs
- TaskDetail, DatasetDetail, Dashboard, Leaderboard, TaskTemplates, Benchmarks, Safety, Ops, RolePermission, NotificationManage, ApiDocs, Profile, Login, AuditLog, Users vue files

Must:
- TaskDetail results paginated
- DatasetDetail failure + always pager
- Leaderboard no independent obs skin as page identity
- Audit export disabled + 当前环境未开放导出, not API 未完整开放
- Users disable via status, no invite
- remaining pages PageAsyncState/loadError
- Login form error

Output .superpowers/sdd/task-d5-review.diff. Do not implement. No git commit.
