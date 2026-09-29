# 当前实现复审

P0：阻断可信运行/权限边界；P1：阻断主要流程；P2：体验与交付质量。下列路径均相对仓库根目录，行号以审查基线为准。确定的源码事实、已运行复现、尚未执行的浏览器/网络验证分开表述。

## R01 · P1 · 向导生成的三类资源均缺后端必填字段

定位：`frontend/src/views/Resources.vue:693` 的 `buildManifest`，`backend/app/services/protocol.py:214`。

向导的 Tool/Skill/MCP Manifest 都没有 `capabilities.idempotent`。后端强制必填；前端 `runWizardChecks:775` 却仅检查 resource_id/name/type 三个字段就显示结构通过。说明还在前端标为选填，而后端要求非空。本轮用向导同结构 Manifest 调用真实 `validate_manifest`，得到 `capabilities.idempotent 必填`，见 evidence.json。完整 JSON 覆盖可绕过向导缺陷，但不能算向导可用。

修复：共享完整契约；提供幂等语义选择和说明字段；前后端同一校验结论；上一步改配置后使检查结果失效；确认页只显示脱敏摘要。验收：不粘贴完整 Manifest，三类分别真实注册成功；缺字段定位到表单；结构成功不能代替连接/调用成功。

## R02 · P0 · 副作用判断会异常，另一路仍将 stub 写成成功

定位：`backend/app/services/side_effect_policy.py:7,31`；`services/tool_gateway/__init__.py:109–125`。

`se not in {"none", False, [], ""}` 构造了含 list 的 set；`capabilities.side_effects='none'` 时抛 `TypeError: unhashable type: 'list'`。本轮已纯函数复现。该调用在网关主执行 try 外，无法走规范失败信封。

顶层非空 side_effects 则会走 stub；返回 `stubbed=True,mocked=True`，网关将其封成 success，并写成功 ResourceCallLog 和幂等响应。即使内层 passed=False，也不符合“真实调用或明确阻断”。

修复：类型明确的副作用枚举校验；不支持或未授权真实副作用返回 blocked/denied，禁止业务 stub 成功；受控沙箱内的实际执行才记录 execution success。更新仍期待 stub success 的旧测试。验收覆盖无副作用、允许副作用、拒绝、异常，数据库不得新增模拟成功记录。

## R03 · P0 · 资源列表隔离不等于资源全链路隔离

定位：`backend/app/api/resources.py` 的 `match_resources:121`、`resource_registry:145`、heartbeat、events、`mcp_probe:286`、health、offline、`get_resource:365`；`services/tool_gateway/__init__.py:invoke_tool`。

列表和注册增加了对象作用域，但上述多个入口仍全表检索或仅按 ID 查询。invoke 接收 actor，却只把 tenant 写进信封和幂等键，未验证该资源是否对 actor 可见。知道另一租户 resource_id 的调用者可能利用其资源及凭证；详情、事件、探测、下线也没有同等对象检查。这是源码确定缺口，本轮未向真实实例发越权请求。

修复：网关集中强制对象和动作权限；详情/发现/事件/探测/健康/修改入口同样收口，平台内置与租户私有分开；view 权限不应隐含无限制网络探测权。补调用日志 tenant/user/version/trace 字段及迁移。验收：隔离库 A/B 租户 + 同租户私有对象，全入口不可读/调用/更新；不能仅测 list/register 后宣告 F04 closed。

## R04 · P0 · 影子测试仍用构造评分，不是真实版本对照

定位：`backend/app/api/tasks.py:985–1065` 的 `shadow_service`。

当前用同一个模型调用两次，在 prompt 后追加 candidate；`_score` 对输出字符 ord 求和取模得到“分数”，samples 复制为 `[s1,s1]` / `[s2,s2]`。这不是任务裁判评分，也没绑定真实候选版本；随机 observation_id 未对应独立持久化观测行，仅把汇总写进 shadow_json。常量样本使相关性门禁不可判定；反复点击增加 pair_count 也不是跨日观测。

客户端分数入口被移除是进步，但“F02 closed”只说明旧攻击形态收敛，不能说明 WP14 完成。修复：版本对应实际执行配置，相同输入双路执行、独立真实裁判、成对样本持久化、真实窗口覆盖与候选故障隔离。缺实现时明确 blocked；绝不花费真实模型费用后再构造假评分。

## R05 · P1 · Agent 工具消息历史不完整，真实工具链未闭环

定位：`backend/app/services/agent_runtime.py:267–306`，`backend/tests/test_agent_runtime.py:test_live_tool_loop_success`。

模型返回的 assistant message/tool_calls 未进入消息历史；下一次请求却追加 role=tool 的 observation，缺少对应 assistant tool_calls。多工具只取首条，其他调用被丢弃。现有“live”单测使用 AsyncMock 返回两次固定响应，没有检查请求历史，故不能证明真实服务接受第二轮请求。本轮未调用真实 provider；具体服务报错表现待 L3 复核。

此外，工具集合仅 search_knowledge/infer_dims，两种都是直接函数调用，没有与工具目录/MCP 的动态授权执行集成。工具循环和审批后的业务任务是两条有限衔接的路径，不应宣传为通用自主工具编排。

修复：按序保存完整 provider 消息与 tool_call_id；全部工具调用有受控结果，或明确协商单工具策略；工具经授权网关/TaskService；真实 usage 缺失为 unknown；规划模型也要对象 ACL；空模型响应不得靠固定“已完成”话术变成目标成功。验收：真实模型至少一次选工具→实际调用→回传→最终回答，刷新/重启后仍可追溯。

## R06 · P1 · Agent 完成状态推断错误，终态运行会从界面丢失

定位：`frontend/src/views/Agents.vue:445–457,638–664,startRuntime,resumeRuntime`；`backend/app/services/agent_runtime.py:_clear_active`。

页面用“有 task_id 且无 active_run_id”直接推导 completed，没有读取关联 EvalTask 的真实状态。普通任务仍在执行也可能显示“查看报告”。另一方面，后端终态清空 active_run_id；loadSession 先清空 run/events，之后只加载 active_run_id。同步运行完成后马上 loadSession，使刚取到的终态 run 和事件消失；刷新旧会话也无法定位历史运行。startRuntime 随后可能弹出 `run undefined`。

修复：会话、AgentRun、EvalTask、报告各自独立状态；API 提供 last_run_id/历史分页和关联任务摘要；选择会话展示最近运行与历史入口；最终报告按钮依赖实际报告可用。慢网保护应涵盖 resolveLabels 等后续异步写回，当前 generation 只保护部分请求。验收：任务排队/运行/失败/取消/成功，以及 Agent 终态刷新、A→B→A 乱序、运行中取消。

## R07 · P1 · Tool/Skill 向导没有可执行配置

定位：`Resources.vue:740`；`services/http_adapter.py:invoke_http_tool`；`services/skill_runtime.py:run_skill`。

Tool 向导生成 local://tool/...，但非内置 Tool 后端只走 HTTP 适配器。Skill 向导既无步骤编辑器也不生成 skill.chain，后端要求非空 chain。即使补上 R01 字段，普通用户仍不能通过向导构建可运行资源。

修复：Tool 配真实 HTTP 地址、请求映射、凭证引用、超时、输出/错误映射；Skill 配已授权工具步骤、输入输出绑定、版本和终止策略，子步骤经网关执行。禁止仅凭 Schema 创建一个不存在的 local handler。验收：AI 实现并部署一个确定性小工具，用户只用表单完成注册和实际调用；两步 Skill 消费真实上一步结果。

## R08 · P1 · “在线/成功”仍混淆结构与实际执行

定位：`api/resources.py:register_resource`、`mcp_probe`；`services/http_adapter.py:invoke_http_tool`；`Resources.vue:620`。

注册结构合法直接写 status/health_status=online；HTTP 适配器看到 body.result 就取 result，即使上游 body.status=error 也可能丢失错误，网关继续包 success；本地 MCP 返回 JSON-RPC error 时 probe 仍外包 ok=True；UI 只判少数错误状态，缺状态默认成功，未识别 nested error/isError/stubbed。

修复：分开 registered/schema_valid、connection、execution、score 四类状态；严格正向确认成功；协议失败显式归一。评分不通过但调用成功要同时展示，不应把 passed=False 一律当网络失败。验收：HTTP 200 + 业务 error、MCP isError、缺状态、缺 endpoint、stub 均不能绿；真执行且评分不通过显示真实双状态。

## R09 · P1 · 凭证暴露面与证据持久化不完整

定位：`Resources.vue:265` 直接 pretty(buildManifest())，Manifest 内可包含 token；`api/resources.py:register_resource` 及 `ResourceVersion.manifest_json` 原样保存；`models/resource.py:ResourceCallLog`。

列表递归脱敏不代表凭证只存在一次请求：确认页仍可明文展示 token，Manifest 和版本快照存原文。工具调用日志未保存实际耗时、输入/输出证据引用、tenant/actor，latency_ms 使用默认 0；前端浏览器耗时不能补全后台执行证据。临时 MCP probe 无完整调用证据持久化。

修复：凭证引用与服务端受控解析，历史快照移除秘密；确认页脱敏；统一证据存储与访问权限，失败也落库；实际调用耗时与浏览器等待耗时分别命名。验收数据库/日志/导出/界面均无原文秘密；任何页面的“最近调用”可回查真实记录。

## R10 · P1 · 演练证据只是非空校验，不能证明执行

定位：`backend/app/services/ops_governance.py:135–157`。

evidence 任一 sha256/signed_by/evidence_uri 非空或 RPO/RTO 非 None 即允许 pass。任意字符串或数字 0 都能满足，没有检查制品存在、摘要、执行记录、签署身份。这比完全无证据通过有所改善，但不足以关闭 F03 的可信验收要求。

修复：引用已执行且授权可见的演练记录、校验实际制品；人工签署绑定登录复核人和时间；外部附件仅为待核验。不能由执行 AI伪造专家/运维签字。验收伪路径、假摘要、跨租户证据、执行人自填他人签名不能正式通过。

## R11 · P1/P2 · 表单、全站状态与响应式只做了一部分

定位：`SchemaForm.vue:94–110`；`Resources.vue:679`；`Prompts.vue:176,220–221`；`Quality.vue:98,106`；U4/U5。

SchemaForm 只校验必填，嵌套非法 JSON 会转成普通字符串；整数变 number，未保留整数约束；JSON Schema 来回转字段表会丢 enum、description、嵌套和范围等约束。Resources 存在 900/820/760px 弹窗和固定半宽布局；Agents 局部硬编码浅色背景。Prompts/Quality 仍固定前 50 条。U4 中多页明确“轻量保留”，并非优化完成。

修复及全页验收见 02。以上布局风险来自源码，本轮未宣称亲眼验证溢出/暗色不可读。七项可达性烟雾不能覆盖创建→失败恢复→完成，也不能证明 24 页明暗/窄屏/键盘都可用。

## R12 · P1 · 资源版本快照与真实执行不一致

定位：`services/tool_gateway/__init__.py:ensure_resource_version,invoke_tool`；`api/resources.py:register_resource`。

同 resource_id/version 已有快照时直接返回；注册仍可覆盖同版本当前 manifest。调用读取当前 r.manifest_json，幂等键却使用旧 ResourceVersion.version，因此“版本冻结”不能保证该调用按对应快照执行。

修复：相同版本不同内容拒绝，或显式创建新版本；运行绑定并读取冻结版本，凭证仅绑定受控引用；同版本变更不能复用旧结果。验收先注册 v1→调用→同版改 endpoint/schema→拒绝，再 v2 调用与证据对应 v2。

## 数据与交付事实

本轮只读盘点的业务文件有 67 张表、10,620 行（快照时点计数）。其中 eval_results 103 行，**50 行 simulation=1**；agent_runs 1 行且 **provider=mock**。这两个结构化计数已足以否定“业务库无 Mock”。所有 103 行结果都命中 mock 文本，但 structured_mock_true_rows=0，故不能声称 103 行全是假结果；必须按 lineage 判别。eval_models 92/117、leaderboard_snapshots 18/21 命中 mock 文本，均只记候选。

历史真实 L3 库是 `backend/tests/_isolated/l3/l3_live.db`，有 67 表、540 行；与业务文件不同。不能把其历史 JSON ok=true 当成当前所有页面已有真实数据。`.env` 的 L3 模型 URL/Key/主副模型键非空，下一轮可以从后端读取使用，但其有效性和 tool calling 能力未在本轮验证。

原计划 AC24 全 MCP 生命周期、AC26/38 真实隔离、AC27–29 真实 Agent、AC42/43 影子，以及 L2、200 场景评估和 L4 性能/签署仍未完整关闭。M4 顶部旧缺陷描述与后续“代码已修复”并存，STATUS 首段仍说代码整改待实施；应追加本轮基线与缺陷映射，保留历史，不通过删去旧记录掩盖矛盾。
