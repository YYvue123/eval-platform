# Spec review D Task 4

Read:
- docs/superpowers/plans/2026-09-29-subproject-d-frontend.md Task 4
- .superpowers/sdd/task-d4-brief.md
- .superpowers/sdd/task-d4-report.md
- frontend/tests/unit/listPages.test.mjs
- Datasets, Tasks, Quality, Prompts, EvalServices, Users, AuditLog vue files
- frontend/src/components/ResourcePicker.vue

Must:
- URL page/q/status via listQuery
- pager visible even when total small (no total > pageSize hide)
- Quality/Prompts/EvalServices not dump 50 as full set
- PageAsyncState + no silent empty
- ResourcePicker load more appends pages

Output .superpowers/sdd/task-d4-review.diff. Do not implement. No git commit.
