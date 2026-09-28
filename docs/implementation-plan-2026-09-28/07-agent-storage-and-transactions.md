# Agent持久化与事务实现补充

本文件给出WP07—09的数据库约束与关键事务，作为03的实现补充。字段类型基于目标PostgreSQL；所有时间使用timestamptz，JSON结构使用jsonb并带schema_version，敏感正文优先Artifact引用。

## 1 表与约束

| 表 | 关键列 | 唯一约束与索引 |
|---|---|---|
| agent_definition_versions | id、definition_id、version、role、prompt_artifact_id、model_config_version_id、tools_json、limits_json、status | UNIQUE(definition_id,version)；发布后不可修改 |
| agent_sessions | 保留现有id，增加tenant_id/workspace_id、active_run_id、row_version、archived_at | INDEX(tenant_id,workspace_id,updated_at) |
| agent_runs | id、session_id、status、graph_version、definition_version_id、current_plan_version、checkpoint_thread_id、lease_owner/until、fencing_token、budget_reserved/used、pending_action_id、row_version | UNIQUE(checkpoint_thread_id)；INDEX(status,lease_until)；session.active_run_id配合行锁保证一活跃run |
| agent_plan_versions | id、run_id、version、plan_json、canonical_hash、validation_json、policy_version、created_by | UNIQUE(run_id,version)；UNIQUE(run_id,canonical_hash)可选去重 |
| agent_steps | id、run_id、node_id、attempt、status、input_ref、output_ref、started/finished、error_code | UNIQUE(run_id,node_id,attempt) |
| agent_delegations | id、run_id、parent_step_id、agent_definition_version_id、context_hash、budget_slice、deadline、status、result_ref | UNIQUE(run_id,parent_step_id,context_hash,agent_definition_version_id)防重复同任务委派 |
| agent_approvals | id、run_id、plan_hash、action_hash、scope_json、expires_at、status、approver_id、consumed_invocation_id、row_version | INDEX(tenant_id,status,expires_at)；消费动作由invocation唯一键保护 |
| agent_tool_invocations | id、run_id、step_id、tool_id/version、action、correlation_id、request_hash、status、effect_class、approval_id、result_ref、provider_request_id、error_code | UNIQUE(tenant_id,tool_id,tool_version,action,correlation_id)；INDEX(run_id,created_at) |
| agent_events | id、run_id、seq、type、step_id、payload_ref/小JSON、created_at | UNIQUE(run_id,seq)；seq在run行锁内递增，不用进程内计数 |
| agent_monitor_states | task_id、run_id、last_event_seq、last_summary_hash、risk_level、next_check_at、last_llm_at | UNIQUE(tenant_id,task_id)；多个会话订阅通过单独subscriber表复用监控 |
| knowledge_candidates | id、source_run_id、source_artifacts、claim_json、status、reviewer、reason | INDEX(tenant_id,status,created_at) |
| knowledge_entries/chunks | entry_id、version、source_hash、content_ref、review_status、valid_until、ACL、embedding_model/version | UNIQUE(entry_id,version,chunk_no)；检索索引必须带tenant过滤 |

所有关联采用租户约束；approval与run、plan必须同租户和工作空间。工具输出、LLM调用、检查点的访问权限随run，不因知道UUID可读。删除会话先归档，后按保留策略清理无业务引用的内容；审批/审计/计费记录不能随聊天删除直接消失。

## 2 并发消息和run领取

接收消息事务：验证用户→锁session→检查client_message_id唯一(session,id)→重复返回原message/run→检查expected_version→写消息→若waiting_user唤醒原run，否则active run期间写pending_instruction→没有active run则新建run并设置active_run_id→写outbox→commit。发送HTTP202不代表run已完成。

worker领取事务：选择到期work_item并锁→验证无有效run lease→递增fencing_token、设置lease→commit。图每个提交边界检查fencing；checkpoint操作与业务状态不能原子时，用agent_step执行日志作为桥梁：prepare step→执行幂等工具→保存工具结果→更新step→保存checkpoint→写状态事件。恢复发现step已完成而checkpoint落后时，直接加载step输出推进，不重复执行。

LangGraph存储表和业务表即使都在PostgreSQL，也不能假设SDK自动参与相同事务。必须有上述调用日志桥梁和故障注入测试。图checkpoint中的task_id只是引用，任务当前状态以TaskService为准。

## 3 审批与工具副作用事务

```text
execute_business_tool(actor, run, plan_hash, approval_id, correlation_id, args):
  1. canonical_request_hash = hash(tool_version + action + canonical(args))
  2. 开始事务，查询/插入幂等invocation（由数据库唯一约束竞争）
  3. 已存在：hash不同→409；completed→返回已存结果；processing→202
  4. 对新invocation：锁approval，必须为approved且未过期，校验plan/action hash和scope；pending不可执行
  5. 重验actor当前权限、对象状态与预算；标记approval消费绑定invocation
  6. 可信内部业务写：在同事务调用TaskService、写result和outbox，commit
  7. 外部写：事务只保存prepared与预占；commit后调用外部idempotency key
  8. 外部响应：短事务写completed/failed/outcome_unknown、结算、outbox
```

内部写工具的TaskService不得自行commit，应由调用层unit of work控制；否则工具日志与业务写脱节会重新产生重复创建风险。外部调用不持数据库事务等待网络，未知结果需要provider状态查询或人工核对，不允许审批消费后失败就无限“重新批准”自动再写。

同一批准计划可以含多个授权动作，scope记录动作列表和上限，每个动作有独立action_hash/消费记录；不能仅一个consumed布尔值导致计划首步后其余合法步骤无法执行，也不能一张approval无限次复用。建议增加approval_actions(id,approval_id,action_hash,max_uses,used_count)，默认max_uses=1；任务批次展开后的明确run数量绑定动作范围。

## 4 预算事务

reserve：锁tenant/workspace/run预算账户→检查available≥requested→创建唯一invocation reservation→reserved累加。settle：锁reservation→只有reserved/pending状态可结算→真实usage写不可变ledger→释放差额→标settled。duplicate settle返回原ledger。unknown不释放预占，后台对账；超过核对期由人工明确write_off/charge，留审计。

子Agent预算从父预占额度切片，不在tenant再次重复扣整笔额度；真实调用ledger按invocation计费，归属到子run并汇总父run。任务模型/裁判费用与Agent规划费用分列，合计受plan上限。人民币微元之外需要其他币种时新增price版本和汇率来源，不在本版静默换算。

## 5 资源版本与审批过期

stable发生变化不影响已冻结plan；但资源版本被撤销、用户权限变化、数据授权到期、风险策略升级时，执行前校验应拒绝或重新审批。计划审批hash不包含密钥值，凭证轮换不自动改变计划业务语义；若endpoint/数据目的地改变，则视为新资源配置和新审批。

用户等待时间不计入Agent活跃运行时间，但approval有有效期、资源有授权有效期、run有保留期限。恢复不能用“等了很久”为理由自动批准或自动增加预算。

## 6 最小故障注入点

分别在领取后、LLM返回后、工具prepared后、业务commit后、checkpoint前后、SSE写出前后kill worker。每次恢复验证：内部副作用次数、已结算费用、最终状态、事件重复处理、checkpoint版本、fencing、审批消费。外部未知结果允许进入outcome_unknown，但必须可见且有处置入口。这些测试是生产Agent验收必要项。
