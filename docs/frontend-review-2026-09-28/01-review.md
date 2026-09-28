# 实现复审与整改清单

## 审查口径

核对了原始开发/验收计划、STATUS/M4、重点 WP 交付报告、全部页面入口与路由；深入检查 Agents、Resources、Benchmarks、Safety、EvalServices、Ops 及对应关键后端链路。其余页面是结构与交互抽查，不等于全面安全审计。未运行全量后端测试、真实付费调用和浏览器全站测试；不把构建成功当成交互通过。

P0：阻断正式可信交付；P1：阻断主要用户流程或重要权限边界；P2：效率、表达与视觉一致性。下述行号对应审查时工作区，变更后以函数名定位。

## F01 · P0 · Agent live 实际仍走 Mock

- 证据：`frontend/src/views/Agents.vue:startRuntime` 写死 `provider: 'mock', sync: true`；`backend/app/services/agent_runtime.py:step_once` 的 live 分支仍调用 `_mock_select_tool`，仅追加 `provider.fallback_mock_select` 事件；随后固定 `_charge_tokens(run, 10)`。
- 影响：界面上的“启动 Runtime”不是已经实现真实模型决策；固定 token 消耗不能作为真实 usage。DeepSeek 普通 Chat Completions/trial 的 L3 证据不能证明 AC27 的 Agent tool-calling。
- 修复：按用户最新要求删除演示/Mock provider；必须调用配置的真实规划模型，校验真实 tool calls，经受控工具执行并把 observation 交回模型；不支持时返回清晰不可用状态，禁止静默降级。usage 未返回则标记未知，不估算成实测。
- 验收：可控 provider 断言真实请求与工具参数；缺配置、非法工具、超预算、恢复均有断言；至少一条真实规划模型工具循环留有脱敏 trace。对应 AC27–29。

## F02 · P0 · 影子门禁仍信任客户端伪造的观测

- 证据：`frontend/src/views/EvalServices.vue:shadow` 提交固定 production/candidate 分数与样本；`backend/app/api/tasks.py:shadow_service` 原样传给 `evaluate_shadow`；`backend/app/services/shadow_router.py:_server_scores` 读取请求中的 `score/server_score`。拒绝逻辑仅针对只有 `client_score` 的特定输入名。
- 影响：改字段名即可让客户端数据被当成服务端观测；七天门禁检查的是起始时间差，而非七天真实观测覆盖。`returned='production'` 字符串也不能证明发生了双路调用和失败隔离。
- 修复：浏览器只提交版本/流量配置；观测由服务端执行链产生并持久化，按租户、服务、版本、时间窗查证。缺成对样本时不得用延迟差替代相关性后通过。区分“配置已保存”“正在采样”“证据不足”“允许转正”。
- 验收：请求伪造 `score`、`server_score`、`samples` 均不能改变可信统计；空观测、单次观测等待七天、跨服务 evidence_id 均不得转正；候选异常不影响实际生产响应。对应 AC42/43。纯函数复现不代表已实际攻击生产接口。
- 本轮实测：运行 `verify_review.py`，请求形状的 score/samples 和两个空对象均被 `evaluate_shadow` 判为 ready；向 `can_promote` 传入八天前起始时间，两者都返回 true。见 [evidence.json](evidence.json)，含源码 SHA256。该脚本只加载纯函数，无数据库/网络/业务写入。

## F03 · P0 · 未执行发布演练即可登记通过

- 证据：`frontend/src/views/Ops.vue:logDrill` 直接提交 `result: 'pass'` 和固定 checklist，没有证据；`backend/app/api/ops.py:DrillBody` 默认 pass；`ops_governance.py:record_drill` 直接存储结果。
- 影响：一键操作可生成看似完成的发布演练记录，违反“未测不得正式通过”。不要与页面上另一个实际恢复演练动作混为一谈。
- 修复：登记默认草稿/未验证；填写真实步骤、结果、证据、执行人与复核记录。正式通过必须由服务端证据校验或明确人工签署；自动恢复演练仍保留实测 hash/RPO/RTO。
- 验收：无证据不能登记正式 pass；失败保留失败记录；不允许把勾选固定清单等同于执行 AC46。

## F04 · P1 · 资源注册与服务单尚未闭合对象隔离

- 证据：`backend/app/models/resource.py:BaseResource` 无租户字段、resource_id 全局唯一；`api/resources.py:list_resources/register_resource` 全表查找，注册同 ID 会更新现有资源，权限检查未约束创建者/租户；`resource_out` 原样返回 manifest。`api/tasks.py:shadow_service/promote_service` 按主键取服务单且仅检查动作权限。
- 影响：动作 RBAC 不等于对象授权。全局内置资源可以共享，但不能让普通资源创建权限覆盖其他主体资源。manifest 允许 token 时还需要输出脱敏。
- 修复：先明确平台共享资源与租户资源边界；内置资源受平台权限保护；私有资源、事件、版本、调用记录和服务单接入对象策略。返回凭证引用及配置状态，不回显原文 token。需补迁移与旧数据归属策略。
- 验收：隔离环境 A/B 两租户同角色测试 list/view/register/update/invoke/events/shadow/promote；B 不可见、不可覆盖 A。此项是源码确定缺少相关检查，实际可达范围需测试验证，不声称已完成全链路越权复现。

## F05 · P1 · Agent 会话状态串页与审批表达错误

- 证据：`Agents.vue:loadSession` 仅在有 active_run_id/task_id 时加载，没有清空旧 run/events/delegations/evidence、停止旧轮询；`approvalId` 会回退取首条审批，即便不是 approved；`canConfirm` 还允许仅凭 session 状态启用。澄清提交使用左侧全局 objective/requirement，未随所选会话重建。
- 影响：A 切到空会话 B 仍可能显示/操作 A 的运行；旧响应晚到也可能覆盖 B。失效审批导致按钮可点但请求失败，澄清可能带入另一目标。
- 修复：以 sessionId/runId 为上下文；切换即重置并取消请求或使用 generation 拒绝过时响应；表单从当前会话初始化；审批有效性由后端判定并给出原因。
- 验收：A→B→A 慢网乱序、B 无任务、审批过期/被消费/计划修改场景；页面显示和每个请求 ID 始终归属当前会话。后端防重放不能被 UI 改动削弱。

## F06 · P1 · 轮询与写操作缺少并发和恢复控制

- 证据：`Agents.vue:startPoll/refreshRun` 使用异步 setInterval，直接拼接事件；`loadRun` 将游标取自另一次请求的 run.event_seq；确认每次点击生成 Date.now invocation ID，按钮无独立提交锁。`Resources.vue` 同样定时轮询批次。
- 影响：慢网可能重叠请求、重复事件；事件列表如果分页可能跳过未收取的 seq（需核对接口上限复现）；轮询失败会被全局 Toast 反复打断。后端已有幂等保护仍需前端稳定重试键配合。
- 修复：单请求完成后再调度、退出/切换停止、退避与手动重连；按 runId+seq 去重，游标来自实际消费事件；重试同一业务意图复用键，成功/修改意图后换键。写按钮各自 loading，取消显示“取消中”直到服务端终态。
- 验收：接口耗时大于轮询间隔、断网恢复、重复点击、断响应重试、卸载组件无后台请求。

## F07 · P1 · MCP 远程地址可能被默认资源遮蔽

- 证据：`Resources.vue:openProbe` 默认 resource_id 为 builtin/mcp_gateway；表单同时显示 endpoint；`api/resources.py:mcp_probe` 优先走非空 resource_id 分支。
- 影响：用户输入远程 endpoint 后点击探测，实际可能仍测内置资源，形成错误的连接认知。
- 修复：显式单选“已注册连接/临时远程地址”；切换清空另一来源；请求前校验互斥，服务端也拒绝两者同时存在。结果固定展示本次实际目标、模式、时间与 trace。
- 验收：填写远程地址后本地 builtin 不被调用；两参数同时存在返回明确 4xx；失败不能显示连接成功。

## F08 · P1 · 工具底座只有开发者入口

- 证据：`Resources.vue:register` 仅 JSON textarea + 无局部捕获的 JSON.parse；`tryInvoke` 固定北京/北京，MCP 固定 initialize；响应统一 `ElMessage.success`，缺状态兜底为 ok。列表固定 page_size 100 没有分页；页面没有资源详情工作流。
- 影响：非 exact_match 工具无法合理试用；应用层失败仍弹绿色通知；超过 100 条的资源无法浏览；普通用户必须自己学习 Manifest。
- 修复：接入向导、Schema 参数表单、结果面板、可搜索分页目录、详情抽屉；JSON 留在高级模式。客户端校验和服务端 Schema 校验同时保留。schema-only 注册校验不得显示实测健康通过。
- 验收：三种不同 Schema 工具不用改源码即可输入参数试用；无效 JSON 定位错误并保留内容；HTTP 200 + tool failed 渲染失败；第 101 个资源可访问。

## F09 · P1 · MCP/Skill 实现范围小于 WP06 原始验收

- 证据：`mcp_client.py` 是单次 HTTP JSON-RPC 包装；WP06 交付自己注明 stdio、list_changed 双缓冲、非 workflow Skill 和进程/容器沙箱未做；原 `05-development-plan.md:WP06` 要求生命周期、四类 Skill 和真实隔离，AC24/26 未因此关闭。
- 修复：明确支持矩阵并在 UI 显示“不支持/未验证”；按原计划补生命周期与安全执行。不能把额外几个表单字段当作已有传输能力。
- 验收：独立 MCP 生命周期与更新期间旧调用排空；真实网络/文件越界受限；未支持类型不能进入正式 ready。协议实现需另核对届时官方规范，本复审不宣称进行了协议合规认证。

## F10 · P0 · 代码用例通过率与媒体可解码证据不足

- 证据：`scenario_simulators.py:code_sandbox_score` 不执行测试，candidate 缺失时直接使用 reference，文本一致即将所有 tests 记为 passed；`benchmark_registry.py` 将 code_pass 设为可观测、代码 oracle_type=unit_tests；`media_adapter.py` 仅检查 magic，输出 decodable_stub。`Benchmarks.vue:runSim` 不传候选代码，仅传套件和模拟器。
- 影响：演示可用，但不是真实代码测试通过率，也不能证明视频可解码或真实模态被模型消费。WP11 的“内部 ready”必须限定意义，不能用于正式评测完成声明。
- 修复：从业务评测链删除参考解比对冒充执行的实现；真实代码评分依赖隔离执行器、真实候选与实际断言；媒体需实际解码和调用证据。缺输入返回 not_run，不默认用参考答案替代被测输出。按用户最新要求不保留模拟业务模式。
- 验收：语义正确但文本不同的候选能按执行结果评分；缺候选不可 pass；伪造 magic 的坏文件不可宣称可解码。对应 AC37/38。

## F11 · P1 · 安全复核不是可用的专家工作台

- 证据：`Safety.vue:resolve` 固定 expert_label=approved、note=专家通过，未提供查看争议证据/修改标签/填写原因；`tryScore` 自动取首条样本的 good 示例。
- 修复：详情呈现输入、实际输出、参考依据、机器结论与争议原因；可填写领域标签、通过/驳回/需补证与理由；试评允许自定义输出并清楚标记示例。
- 验收：能拒绝错误结论、保留理由与审计；按钮受权限与状态约束；示例试评不计入真实模型能力报告。

## F12 · P2 · 全站流程、状态与视觉语言不一致

- 证据：Agents/Resources/Safety 固定列宽与栅格；服务操作列宽 560 且同时出现大量按钮；Tasks 固定拉取前 50 条；Leaderboard 在模板中加载外部字体并使用独立观测台样式；不少页面直接显示 ready、trial、checkpoint、hash。
- 修复：按指导文档统一设计变量、页面框架、中文业务文案、状态枚举、分页和表单；保留有用的现有 EmptyState/ActiveFilterHint、菜单权限与暗色能力，不全部推倒重写。
- 验收：全部路由在明暗主题及 1440/1024/390 宽度检查；390 允许表格区域滚动，主操作不能被遮挡；无数据、无权限、失败、加载状态可区分。

## 交付声明应如何修订

保留历史报告，在 STATUS/M4 追加复审结论与替代证据，不删除不利记录。每个 WP 分成“实现范围、自动化已测、真实联调、生产验收、未关闭事项”。尤其 WP06、07、11、14、16 不能仅凭现有报告的测试数量写作完整关闭。157 项历史单测不等价于 AC01–46 全覆盖；建立逐条 AC → 测试 → trace → 环境 → 结果的映射。

原计划中的 L2 多 worker/独立基础设施、200 场景 Agent 评测、企业 mTLS、外部 MCP、真实媒体和 L4 容量目标继续保留为明确待验收项。没有条件实测时写 blocked/not_run，不能降标成 pass。
