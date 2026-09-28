# 本次验证记录

代码基线90056950c28c4fac669dd79b2979f75ba3431dd8；2026-09-28；Windows环境。业务代码没有更改。所有运行测试使用本目录下新SQLite文件及uploads/logs/backups，不访问原backend/eval_platform.db。

| 项目 | 实际结果 | 证据 |
|---|---|---|
| 后端语法 | 70应用文件AST解析通过 | design-validation.json |
| 前端构建 | Vite 5.4.21构建通过；含大chunk警告，未执行npm prebuild权限写入 | frontend-build.txt |
| 原有虚拟环境 | Python311解释器不可用 | backend-tests.txt |
| requirements原样安装 | Python3.12.14、SQLAlchemy2.1.1等；缺greenlet，13项运行中10项错误 | backend-tests-isolated.txt、backend-package-versions.json |
| 补greenlet后的全套尝试 | 登录/Agent/基础裁判先通过；端到端长时间等待，人工中断，不能算完整通过 | backend-tests-with-greenlet.txt |
| 隔离基础/接口子集 | 11项，9.090秒，OK；不含2个执行/队列用例 | bounded-smoke.txt/json |
| 单独端到端执行 | 全新execution.db，45秒超时终止；25秒线程转储显示SQLite调用和HTTP等待 | bounded-execution.txt/json |
| 任务模板队列用例 | 未完成验证，不记为通过 | 后续WP00/WP04执行 |
| 空输出裁判反例 | 幻觉/标识误判满分均复现，属于缺陷证据 | static-probes.json、design-validation.json |
| 交付契约 | 5 Schema、2样例、4非法计划、引用/DAG及链接检查通过 | design-validation.json |

11项通过的原有测试覆盖：登录看板、规则式Agent、内置基础裁判、batch与资源匹配、字段映射质量门禁、health/metrics/TLS配置、榜单服务单、内置Manifest、模型映射ACL场景、解析质量、提示词生成审核优化。它们没有证明真实LLM多智能体、正式安全评分、生产租户隔离或分布式调度。

测试环境包安装在本目录被忽略的backend-deps与deps，未改现有.venv。依赖版本清单是本次重建结果，不代表项目已经有正式lockfile；WP00需要建立兼容性经过测试的锁文件。

可复跑脚本：verify_design.py需要jsonschema；run_isolated_tests.py使用当前Python、隔离backend-deps和backend源码，参数smoke或execution。重跑应使用新的测试数据目录/数据库或显式清理仅属于测试的数据库；脚本当前按子集命名，不能在业务数据库上运行。测试数据库和生成制品不放入交接压缩包。

本次没有修改代码来修复缺陷，也没有把超时记为通过。超时根因尚需定位；SQLite长事务、请求审计flush与后台任务时序是代码证据支持的排查方向。
