# D Task 6：证据

Work from E:\eval-platform. No git commit.

## Commands (must run, paste output into report)

```
cd E:\eval-platform\frontend
npm run test:unit
npm run verify:ux-static
npm run build
```

All three must pass. If build fails, fix only if caused by Task 1–5 (don't start new features).

## Evidence file

Create `docs/superpowers/evidence/subproject-d.md`:

1. Date, no commits, tests never hit eval_platform.db (N/A frontend).
2. Command results with pass counts.
3. **24-page six-state matrix**: for each routed page, mark loading/error/forbidden/empty/uncreated/success as code-backed (PageAsyncState/loadError/EmptyState) or gap. Honest — do not claim browser pass without screenshots.
4. Screenshots: 1440 / 1024 / 390 for Login, Resources, Agents, Tasks.
   - Save under `docs/superpowers/evidence/d-screenshots/` with names like `login-1440.png`.
   - If no frontend server: try `npm run preview` after build (Vite preview) OR skip and mark **blocked** with reason. Do not fake images.
   - If login required and credentials unknown, screenshot Login at three widths and mark authenticated pages blocked.

5. List remaining known gaps (Quality rules unpaged, live C fill, B apply busy, etc.).

## Tests

No new tests required unless build fails.

Report `.superpowers/sdd/task-d6-report.md`
