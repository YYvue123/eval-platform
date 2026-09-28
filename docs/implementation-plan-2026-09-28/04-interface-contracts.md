# 标准接口与兼容设计

## 1 合同层次

V0.6.1 是业务接入规范文件版本；消息信封版本是1.3；资源version是其自身SemVer；MCP另有独立协议版本。不能混为一个version。原文Manifest的spec_version例子是1.3.0，现有内置值为0.6.1，附录Schema仅约束三段数字，没有明确兼容矩阵：这是原文歧义，必须记录ADR，不静默猜测。

本设计暂采用接入profile `platform-v0.6.1/envelope-1.3`，资源内部规范化记录spec_version原值和profile。兼容导入0.6.1与1.3.0并提示来源差异，未知主版本拒绝；外部正式对接前将profile交规范所有者确认。内部新manifest暂沿用0.6.1，不能因此声称解决了规范歧义。

contracts/source-*.schema.json是从Word附录直接提取的原始Schema，用于可追溯性；它们不是充分验收条件。原始body无条件约束、部分字段描述不完整，必须叠加本文件的运行语义校验。新增agent-plan/tool-result Schema是本项目目标契约，不是原文内容。

## 2 规范冲突与决策记录

| 问题 | 原文/现状 | 处理决定 |
|---|---|---|
| spec_version | I3.2例1.3.0、文档V0.6.1、代码0.6.1 | 明确profile并兼容读取，正式外部导出需规范所有者确认 |
| judge_type | 附录A枚举不含contains/rule_based，代码使用这些值 | 对外映射为custom并在metadata记录实现；不擅自扩规范枚举 |
| Skill引用 | I8为步骤输出引用，代码把$ref当资源ID | 新版step.resource_id和input绑定分开，旧chain经明确转换，不猜语义 |
| side_effects | 原文顶层数组，现代码读capabilities字段 | 以原文顶层为准，旧字段只迁移读取并警告；无法判定风险拒绝执行 |
| batch结果原子性 | I9.5写临时文件后rename，现为DB JSON | 文件适配器遵守同文件系统rename；对象存储写不可变对象+事务更新指针，记录等价实现ADR |
| Eval Kit | V0.6.1修订默认远程，正文保留旧术语/例外 | 历史可识别，非默认交付；不偷偷新增离线部署项目 |
| Agent MUT | I6明确内部Agent，I10对MUT细节不足 | 自定义有版本MUT适配profile，独立协议测试，不把内部管理工具暴露给被测方 |
| 监控每任务Agent | D P2750持续跟踪 | 每task持久订阅与逻辑监控实例；事件驱动调用模型，非每任务常驻LLM |
| 性能数字 | D多处并发与响应数字未明确负载/硬件 | 保留目标，在06定义压测口径，不能用单机演示证明 |

## 3 信封与错误

请求的header含message_id、message_type=request、version=1.3、timestamp、source/destination，可含correlation_id、priority、ttl、tenant_id。ttl默认300秒，网关验证时间与剩余期限；超时不发起新调用。auth.caller_id服务端注入，permissions只可由可信授权层填写，不能信任客户端自报；不要把用户原始长效token传给第三方。

trace_id在同一业务链保持一致，每次调用新span_id、parent_span_id；HTTP传播traceparent，响应不重新生成不相关trace。tenant_id取身份；跨单位必须有tenant，跨租户字段不一致拒绝。

```json
{
  "header": {
    "message_id": "b487f5ce-8418-4a71-b45b-3ed3c3b4f824",
    "message_type": "response", "version": "1.3",
    "timestamp": "2026-09-28T00:00:00Z",
    "source": "eval/judge", "destination": "platform",
    "correlation_id": "invocation-example", "ttl": 300,
    "tenant_id": "tenant-example"
  },
  "trace": {
    "trace_id": "0123456789abcdef0123456789abcdef",
    "span_id": "0123456789abcdef", "parent_span_id": "fedcba9876543210"
  },
  "auth": {"caller_id": "gateway"},
  "body": {
    "status": "success", "result": {"score": 0.8, "passed": true},
    "metadata": {"usage": {
      "prompt_tokens": 100, "completion_tokens": 20,
      "total_tokens": 120, "model": "judge-model"
    }}
  }
}
```

请求body必须含action与parameters；response含status=success/error、result/error和metadata；event含event_type/payload；stream含chunk_id从0递增、data、done，最后块含finish_reason。LLM类响应必须metadata.usage，包含prompt/completion/total/model；非LLM类usage可省略。UI专用ToolResult由网关映射到标准body，不能混淆内部对象和外部信封。

保留原文附录C错误码；增加平台错误使用`PLATFORM_*`命名并记录扩展表。至少覆盖INVALID_MANIFEST、SCHEMA_VALIDATION_FAILED、权限/资源不可用、TOOL_EXEC_FAILED、TASK_HEARTBEAT_LOST、DATASET_LOAD_FAILED、DATASET_SCHEMA_MISMATCH、BUDGET_EXHAUSTED、BATCH_PARTIAL_FAILURE、MODEL_OUTPUT_INVALID、EVAL_REFERENCE_MISSING、EVAL_SCORE_DRIFT。具体已有错误码以原文附录C核对，未在原文定义的名称归扩展，不能冒充标准码。

HTTP 401认证、403无操作权限、404无范围内对象、409版本/幂等冲突、422输入Schema、429限流、502上游协议、503不可用、504超时。标准error包含code、message、details、retryable、trace_id；不得返回密钥、完整内部路径、堆栈或敏感数据。

## 4 注册与统一网关

`POST /api/v1/resources/register`：静态Schema→语义校验→权限/出口/副作用策略→健康与契约测试→记录AdmissionRun。状态submitted/validating/trial/active/canary/draining/deprecated/offline/rejected；注册不能直接设置online或写死passed。

`GET /api/v1/resources` 分页过滤type/tag/status；`POST .../match` 对授权范围硬过滤后返回匹配解释；`GET .../{namespace}/{name}/health` 读取状态；`GET .../events` 为真正SSE。旧/api/resources兼容路由通过同一服务。带斜杠resource_id采用明确namespace/name双段或query参数，避免path路由吞并events等固定端点。

ResourceVersion immutable，instance独立维护endpoint/lease/health；default stable只在新执行解析，任务冻结解析后的version。健康失败排除实例不改历史版本。限流维度tenant/resource/version/provider，Redis原子令牌桶；熔断半开只允许有限探针，不能冷却后全量放行。副作用、凭证、日志/usage和协议验证只能在统一网关一次实现，所有runner、prompt tests、Agent、Skill和MCP桥接都调用它。

评测标尺语义校验按I3.4执行：所有评测类资源必须evaluation_spec；llm_judge的judge_prompt_template与judge_model必须同时提供（现有代码的“二选一”不足）；metric_names须在输出Schema中存在，pass_threshold键必须属于metric_names，阈值类型与指标范围一致，裁判模型引用必须可用且已授权。

幂等键作用域 `(tenant,resource,version,action,correlation_id)`，同时存request_hash；相同键同payload返回原结果，不同payload409，processing返回pending/202。数据操作幂等记录默认保留不短于重试窗口，内部业务动作随审计/运行记录保留；外部未知结果标outcome_unknown，不能无脑重试。

## 5 四种调用模式

- sync：执行到timeout返回标准信封；上游声明>300秒的长任务使用async。
- async：POST /tasks返回task_id/status；GET /tasks/{id}状态/结果；DELETE取消；POST /tasks/{id}/heartbeat。>300秒任务每60秒心跳，180秒丢失标TASK_HEARTBEAT_LOST并按幂等/租约策略处理。
- stream：优先HTTP SSE，校验chunk序号、终止块、finish_reason，断流标不完整；tool_calls交给工具循环，不能当最终文本。usage出现在约定终止元数据中，未收到则计量待核对。
- batch：只经/batch/*提交/拉片/回写，不能按普通endpoint循环伪装批处理；详见下节。

## 6 DataSource与batch

DataSource适配接口 `metadata、create_snapshot、read_shard、release_snapshot`，来源mount/api/stream分开；stream需物化确定窗口才能进入正式可复现评测。支持jsonl/csv/json，parquet单独适配并契约测试，不能注册了格式就声称能读。

POST /batch/run 接受dataset_id、version_id、resource_version、shard_size、token_budget、execution_mode和correlation_id，校验归属后冻结snapshot；返回batch_id/snapshot_id/checksum/shard_count。GET /batch/status/{id}提供各状态计数、failed_details引用与budget状态。

GET /batch/{id}/shards/{n} 强制snapshot_id且等于batch绑定值；分片号0≤n<shard_count，负数/越界422；租户不符404。加载前校验存储hash，逐条Schema错标skipped并记录原因。

PUT结果输入snapshot_id、attempt、lease_token、results[{sample_key,execution_status,score_status,metrics,error,usage}]、payload_hash。校验分片成员、无重复/未知样本、指标范围、tokens非负、租约与状态。DB唯一(batch,shard,attempt)，同hash重传不重复累计；不同hash冲突409。先发布不可变结果Artifact，后事务提交指针和统计；失败对象可GC，已提交指针永不指向半文件。

预算达到上限paused_budget保留结果，增加预算需授权后恢复，不能直接failed。worker每30秒上报进度；cancel后拒绝新结果结算但保留实际已发生成本和迟到记录。结果导出JSONL/CSV包含真实样本状态。快照至少保留7天，活动任务有引用租约不能GC；超长任务结束后补足追溯期。这个延长保留是对原文7天的安全实现补充，需要记录生命周期策略。

## 7 MCP与Skill

MCP使用官方SDK接真实远程服务，协商支持的版本（最低满足原文2025-03-26或更新），锁定版本做互操作测试。实现initialize、initialized、tools/resources/prompts list和调用、list_changed、分页/超时/取消、JSON-RPC错误映射。生产不启动用户提供的任意stdio命令；本地Dev/Test如启用也需沙箱和allowlist。HTTP授权按协商协议，不把用户Bearer直接透传。

能力双缓冲：收到通知→异步构建candidate清单→Schema/权限校验→原子active_generation切换；存量调用持有old_generation直到结束，再释放；删除工具标draining。新请求不能路由旧版本；加载失败保留旧版本并告警，不能把空清单覆盖有效能力。并发热切换必须有测试。

Skill定义trigger、execution_type、entry_point、dependencies、variables、version。四类执行：prompt_template调用规划/生成模型；workflow执行受限DAG；code仅沙箱；agent委派到明确AgentDefinition。Skill不是随意执行Markdown中的命令。

步骤含step_id、resource_id/version、input、output_schema。表达式支持原文`$ref:step_1.output.entities[0].text`、`$global.dataset_id`、`$input.user_query`；环境变量例子有冒号/点差异，规范化只开放显式allowlist非密钥配置，拒绝任意宿主环境读取。用解析器取路径，不eval；未知引用、未来引用、循环、越界、类型错返回标准错误。前步输出真实传后步输入，所有步骤通过统一网关并记录血缘。

## 8 被测模型与MUT

模型Manifest核对附录D：model_id/name/type、scene_white_list、max_context_tokens、support_stream、version、parallel_limit必填；外部企业名称/代码、内部source/base/deploy字段条件必填。请求支持messages、temperature、max_tokens、stream；响应finish_reason和usage严格校验，TLS和鉴权失败不能当健康。

MUT适配profile建议：create_episode(initial_state,goal,tool_catalog,budget)→episode_id；step(user_message/tool_observation)→message/tool_requests/status；get_trace；cancel；close。所有工具请求交SandboxBroker，返回stub/隔离环境结果；被测方不能指定tenant/真实网关凭证。episode结束用隐藏oracle验证最终环境状态，不能只读被测方“已完成”的自述。第三方无法提供轨迹时标black_box，协作过程指标not_observable，不补造数据。

## 9 准入验收

每个资源版本生成AdmissionRun和带证据测试包。基础级校验Manifest、加密通道、连续3次成功、非法输入/超时/信封；完整级增加压测、安全、幂等、鲁棒性、裁判校准、沙箱和观测。I15原文阈值：通道延迟≤100ms、连通响应<2秒、裁判与人工一致≥90%、稳定性差异≤±5%，需在报告注明网络与样本条件。

试点默认14天且≤5%任务，≥3次P0或评分漂移超阈值重置/终止；完整级之后5%灰度7天再正式。灰度I12.4：平均差异≤5%、单项≤10%、方差≤基线1.2倍、Pearson≥0.95。零基线/常量向量时相对差和Pearson未定义，标inconclusive并走补充绝对误差与人工审批，不自动算0或1。不得通过手填stable=true转正。
