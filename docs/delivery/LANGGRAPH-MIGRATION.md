# LangGraph 编排内核迁移

日期：2026-10-24。当前默认内核为 `langgraph-v1`，使用 `langgraph==1.2.17`、`langgraph-checkpoint==4.3.0`。历史 WP07/WP09 文档记录的是当时的轻量运行时，不代表当前实现。

## 实现边界

主图由 `select_tool → observe → select_tool` 工具循环、`reply → verify` 结果核验，以及 `await_approval` 人工审批节点组成。节点与边由 LangGraph `StateGraph` 驱动；原有 API、会话、事件和 checkpoint 投影继续兼容前端。

`AgentCheckpointer` 实现 LangGraph 的异步 checkpoint 存取协议，将 checkpoint、pending writes 和父 checkpoint 关系保存到新增 `agent_graph_checkpoints` 表。它复用本次运行的 SQLAlchemy 事务，使图状态与业务写入共同提交或回滚。主图与每个子 Agent 分别使用命名空间；不使用内存 saver 作为持久化替代品，不额外依赖 LangSmith 或托管服务。

新增表由现有 `init_db()` / `Base.metadata.create_all()` 创建，不重写历史运行记录。恢复没有 LangGraph checkpoint 的历史 run 时，从原 `checkpoint_json.phase` 导入，再由新图继续执行。没有提供历史 checkpoint 的公共回放/时间旅行 API。

每个节点在外部调用前通过数据库条件更新验证 fencing 并持有本次运行的事务锁，不能只相信 ORM 缓存中的旧令牌。租约为 660 秒，覆盖当前最长 600 秒子 Agent 超时；进程崩溃后的运行需等租约过期后回收，取消在节点之间生效。生产多机行为仍需专项验证。

## 补齐的能力

- 自定义子 Agent 运行独立的模型/工具子图，使用独立消息历史、最大轮次、超时和工具白名单；用当前会话的规划模型连接，可覆盖模型名、温度和输出长度。子 Agent 用量计入父运行预算，未知用量保持 unknown。
- 子 Agent 只能使用查询、知识、绑定 Skill 和 MCP 等受控能力，不能修改计划、创建/恢复任务或递归委派。配置规划模型时，内置方案、参数、监控、诊断、审校及可选报告优化均执行真实模型子图；无规划模型的旧接口仍保留确定性分析回退。阶段协作与开发环境实测见 [后续交付说明](AGENT-LIFECYCLE.md)。
- MCP 接受 `arguments`，从探测保存的工具目录暴露并校验 `inputSchema`，使用创建者当前身份经过网关。非内置连接可正常进行对象授权；没有目录的工具需要先探测。业务错误作为错误 observation 交回模型纠正，权限或结构校验错误仍明确失败。
- 主 Agent 可调用 `request_task_execution` 请求人工审批。图暂停后，只有数据库存在与计划 hash 和实际任务匹配的已消费审批，才可继续；传入恢复命令本身不能批准执行。用户仍通过现有确认入口授权，任务仍经 TaskService 入队。
- 图等待实际任务终态后核验结果。响应新增 `completion`；普通对话完成不意味着评测目标通过。正式执行核验要求：任务 success、报告路径存在于任务记录、非 trial、非 simulation、样本数大于零，且每个样本都有 `execution_status=ok`、`score_status=scored` 的非模拟结果。该核验范围是 `evaluation_execution`，不等于自动验证任意自然语言业务目标或模型质量达标。
- 后台 worker 会处理异步排队、审批/任务结果就绪和过期 lease 恢复。每推进一个主图节点提交一次；已完成工具调用被记录并跳过，MCP 使用稳定关联 ID 复用网关幂等结果。外部非幂等副作用仍受原网关策略限制，不承诺任意外部调用 exactly-once。
- Runtime 不再构造管理员身份。运行、事件、取消、恢复和确认入口校验会话对象范围；模型调用检查创建者状态、对象可见性和模型 ACL。

## 运行与验证

先更新后端虚拟环境依赖，再启动后端。`AGENT_WORKER_ENABLED=true` 默认启用 API 进程内 Agent worker；`python -m app.worker` 也可处理 Agent 队列。仅使用独立 worker 时可以关闭 API 进程内 Agent worker。隔离测试明确关闭自动 worker，worker 测试通过受控调度入口验证。

回归命令（PowerShell；数据库固定在测试隔离目录）：

```powershell
cd backend
$env:DATABASE_URL='sqlite+aiosqlite:///E:/eval-platform/backend/tests/_isolated/langgraph-final.db'
.\.venv\Scripts\python.exe -m unittest tests.test_agent_runtime tests.test_agent_approval tests.test_orchestration_capabilities tests.test_collaboration tests.test_tool_gateway tests.test_agent_langgraph -q
```

本轮隔离回归 74 项通过，包含恢复不重放、部分工具失败后重试、审批门禁、MCP 本地真实 HTTP、子 Agent 工具循环、预算、跨租户、禁用用户和事务回滚。脚本化模型响应只作为基础设施回归，不计为真实模型验收。

前端 `npm run build` 通过，包含权限采集（61 个权限码）。没有新增页面或 API 权限码；新工具复用 `agent:invoke`，MCP 另外检查 `resource:invoke`，评测确认继续要求 `agent:confirm`。

真实模型联调使用 `python scripts/verify_langgraph_live.py`。它从现有 `L3_MODEL_*` 配置读取凭证，仅在 `tests/_isolated/langgraph-live.db` 创建资源，通过实际 API 完成以下链路：

1. 真实规划模型 → 自定义子 Agent → 带参数本地 MCP → 主 Agent 汇总。
2. 真实模型请求审批 → LangGraph interrupt → 用户确认 API → TaskService 正式执行 → 报告和逐样本实测结果核验。重复确认返回同一任务。

脱敏证据：[LANGGRAPH-LIVE.json](evidence/LANGGRAPH-LIVE.json)。联调结束清除所建模型及访问配置快照中的凭证。证据中不包含凭证和模型原始回答。

## 尚未宣称完成

未进行生产多机容量验收、所有模型供应商兼容性验收、第三方托管 MCP 全覆盖或浏览器全流程验收。子 Agent 当前按需顺序执行，没有开放任意递归并行代理、代码执行沙箱或通用业务目标语义验收。Checkpoint 历史保留与归档策略需要结合实际运行规模另行配置。

已验证的是上述实际链路与隔离回归，不把局部成功扩展为全量生产验收。

实现参考：[LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)、[持久化](https://docs.langchain.com/oss/python/langgraph/persistence)、[Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)。
