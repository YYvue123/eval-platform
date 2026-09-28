# U5 · 验收与交接

> 权限采集、相关回归、UX/AC 映射、可复现命令与诚实结果（pass / fail / blocked / not_run）。禁止用 build 关闭浏览器 UX。

## Exit

- [x] `docs/delivery/frontend-ux/U5.md` 含 UX01–16 与 F01–F12 关闭表
- [x] AC 映射表（相关子集；全量 AC01–46 不假装全绿）
- [x] `npm run collect-permissions` + `npm run verify:ux-static` + `npm run build`
- [x] 隔离后端相关回归有日志摘要（63 OK → `u5-regression.log`）
- [x] STATUS / M4 追加 U5；未跑浏览器标 not_run

## Work

1. 静态：路由权限候选与 discovered permissions 一致性脚本
2. 回归：agent_runtime / service_shadow / ops_governance / tool_gateway / safety / tenant 子集
3. 文档：复现手册、缺陷关闭、AC↔证据
4. 浏览器：无专用 E2E 环境则全表 not_run，并写清入口缺口
