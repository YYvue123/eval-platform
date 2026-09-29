# Spec review D Task 3

Read:
- docs/superpowers/plans/2026-09-29-subproject-d-frontend.md Task 3
- .superpowers/sdd/task-d3-brief.md
- .superpowers/sdd/task-d3-report.md
- frontend/src/router/index.js
- frontend/src/views/NotFound.vue
- frontend/src/views/Agents.vue (page-desc, planner model, trial_run, createSession)
- frontend/src/views/Models.vue
- frontend/scripts/verify-ux-static.mjs
- frontend/tests/unit/forbiddenNav.test.mjs

Must:
- unauthorized → /not-found?reason=forbidden&from=
- NotFound 403 copy
- Agents desc exact; no auto items[0]; 生成计划 disabled without planner
- Models hint exact; verify-ux-static error without 无法探测或试调用; still reject 留空则使用本地 Mock; no 不会回退到本地 Mock as pass condition

Output .superpowers/sdd/task-d3-review.diff. Do not implement. No git commit.
