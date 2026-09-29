# SDD Progress Ledger

Branch: main (user-approved in-place)
Plan root: docs/implementation-plan-2026-09-28

WP00–WP16: complete. Milestone note: docs/delivery/MILESTONE-M4.md
- Engineering packages closed with unittest + frontend build evidence per docs/delivery/
- Not claimed: L3 live integrations, L4 prod scale, ECO-TBD business scope
- Handoff: README + docs/operations + MILESTONE-M4 for next humans/agents

## 2026-09-29 Review Follow-up Subproject A

Branch: fix/review-followup-d1 (user-approved in-place, no commits)
Plan: docs/superpowers/plans/2026-09-29-subproject-a-d2-closeout.md
Baseline HEAD: 380650893eb44871e4722100c8060def66619d56
Task 1: complete (no commits by user request; review approved)
  Minor: task-1-report.md top summary still says 3 tests while final run is 4/4.
Task 2: complete (no commits by user request; review approved; 3/3 focused tests)
Task 3: complete (no commits by user request; review approved; 10/10 tests)
Task 4: complete (no commits by user request; review approved; 25/25 tests)
  Minor: Starlette TestClient emits an upstream deprecation warning.
Task 5: complete (no commits by user request; review approved; 29/29 related tests)
Task 6: complete (no commits by user request; review approved after HTTPException envelope fix; 11/11 focused tests)
  Minor: 422/409 lack dedicated cases; empty-list `response_result` coerces `[]` to `{}`; `_step_result` shape adapter; NestedSkillError retryable=True.
Task 7: complete (no commits; review approved after resume-id + structuredContent fixes; 8 related tests)
  Minor: parse_sse no flush without blank line; open() does not pin protocolVersion == 2024-11-05.
Task 8: complete (no commits; review approved; 7/7 focused tests)
  Minor: interfaces.shell not rejected; allowlist json.loads not mapped to McpError; Manifest assertion only checks "command_alias" substring.
Task 9: complete (no commits; review approved; 18 MCP tests)
  Minor: catalog_hash uses name+description only; persist_catalog may set stale immediately; run_mcp ignores req_id; no dedicated temp-token digest test.
Task 10: complete (no commits; review approved after sticky-validate fix; 5/5 unit tests)
  Minor: no Vue mount tests for complex JSON drafts; Resources still shows only missing until Task 11.
Task 11: complete (no commits; review approved after pickHistoryLatency fix; 11 unit tests)
  Minor: unknown latency renders as "— ms"; trial badge may show failed while history shows blocked.
Task 12: complete (no commits; review approved; 20 unit tests)
  Minor: Skill default schema still prediction/reference vs $input.text; validateRef lenient on step_N; empty allowedToolIds skips allowlist; stdio probe omits credentialRef.
Task 13: complete (no commits; review approved after stale-identity fix; 33 unit tests)
  Minor: 390px 未点通（Task 14）；成功 list 不清已消失选中工具。
Task 14: complete (no commits; review approved after copy+screenshot fix)
  Evidence: docs/superpowers/evidence/subproject-a.md
  Suites: backend focused 81 OK; discover 208 OK no database is locked; frontend 34 unit; 55 permission codes
  Minor: 390 crowding; Skill source not shown in trial table; leftover 1440 PNGs may show old page-desc fragment.
Whole-branch review: Ready to merge (no Critical/Important). Minors: Agents.vue slogan; A-ISO import-cover test; adhoc probe error_message not redacted.

## 2026-09-29 Subproject B Mock cleanup

Branch: fix/review-followup-d1 (in-place, no commits)
Plan: docs/superpowers/plans/2026-09-29-subproject-b-mock-cleanup.md
Task 1: complete (no commits; review approved; 4/4 tests)
  Minor: test name says rejects but only asserts isolated path; mkdtemp not cleaned.
Task 2: complete (no commits; review approved; 5/5 tests)
  Minor: URI fallback untested; RO checkpoint often no-ops.
Task 3: complete (no commits; review approved; 7/7 tests)
  Minor: missing optional tables always noted; sim-task non-sim results not auto-listed.
Task 4: complete (no commits; review approved; 12/12 tests)
  Minor: action type not filtered; backup content not opened in success test.
Task 5: complete (no commits; review approved; 14/14 tests)
  Minor: verify opens writable connection.
Task 6: complete (no commits; review approved)
Task 7: complete (no commits; review approved; 18 tests)
Task 8: complete (no commits; isolated copy cycle verify ok; live apply blocked: active tasks; 22 tests)

## 2026-09-29 Subproject C real fill

Branch: fix/review-followup-d1 (in-place, no commits)
Plan: docs/superpowers/plans/2026-09-29-subproject-c-real-fill.md
Task 1: complete (no commits; review approved; 3/3 tests)
  Minor: real01_accounts takes two FillClients (brief) not one client (plan); viewer denied is 403.
Task 2: complete (no commits; review approved; 4 tests)
  Minor: quality_status not asserted in unit test.
Task 3: complete (no commits; review approved; 6/6 tests)
  Minor: stats tool registered but not invoked; REAL05 if rid optional.
Task 4: complete (no commits; review approved after REAL06 invoke-only pass)
  Minor: invoke failure still starts agent run; status missing treated as success.
Task 5: complete (no commits; review approved; 19 tests)
  Minor: REAL12 restore not asserted; synthetic notification.
Task 6: complete (no commits; CLI fingerprint gate + isolated evidence JSON; 28 tests; live 8001 blocked)
  Evidence: docs/superpowers/evidence/subproject-c.md
  Minor: REAL10 isolated publish still 200; live REAL01/02/04/05 blocked (no 8001).

## 2026-09-29 Subproject D frontend 24 pages

Branch: fix/review-followup-d1 (in-place, no commits)
Plan: docs/superpowers/plans/2026-09-29-subproject-d-frontend.md
Task 1: complete (no commits; review approved; 39 unit tests; verify:ux-static OK)
  Minor: component tests are SFC source asserts; empty/uncreated share idle badge.
Task 2: complete (no commits; review approved; 48 unit tests; skipErrorToast + listQuery)
  Minor: interceptor tests are source asserts; fetchList still swallows.
Task 3: complete (no commits; review approved; 53 unit tests; 403 + slogans)
  Minor: Dashboard denied banner leftover; no browser e2e.
Task 4: complete (no commits; review approved; 58 unit tests; URL pager + ResourcePicker more)
  Minor: source-regex tests; Quality rules unpaged; EvalServices Promise.all coupling.
Task 5: complete (no commits; review approved; 65 unit tests; remaining pages)
  Minor: source-regex tests; radar null as 0; export hint title-only.
Task 6: complete (no commits; review approved; evidence + 12 screenshots; 65 unit; build OK)
  Minor: Models/Resources list still lack PageAsyncState; Quality rules unpaged; 390 crowding.
Subproject D: complete with honest remaining gaps (Models/Resources PAS, Quality rules, live C/B apply).

