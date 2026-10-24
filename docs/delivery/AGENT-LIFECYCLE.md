# Agent 阶段协作、执行记录与真实开发演示

更新：2026-10-24。本文描述当前代码及验证范围，不代表生产性能或业务准入验收。

## 行为与结构

生成计划先建立规则草案，再创建purpose=planning的LangGraph Run。prepare节点读取当前用户可见的数据集、被测模型及工具（不含凭证），依次运行规划角色，每个专项完成后提交记录。主模型收到实际清单与专项结果，使用propose_resources写入真实配置。规则初选可能与用户指定资源不符，必须核对模型更新后的计划；未完成规划时禁止审批和改配。

plan_analyst、param_advisor、report_reviewer默认绑定；monitor和diagnose保持基础角色。自定义定义的evaluation_spec可配置stages及trigger_keywords：创建新会话时命中关键词后自动绑定，按阶段调用。report_optimizer需显式选择。子Agent共享会话规划模型连接，但有独立提示词、消息、工具范围、迭代及超时限制，使用LangGraph子图。

确认执行仍经审批hash消费、TaskService和任务队列；Agent不写调度内部或评分。确认后创建followup Run，或标记既有审批等待Run续接跟踪。状态快照变化才记录task.observed并调用monitor；失败、预算暂停或终态存在失败样本时调用diagnosis；终态调用review，原报告就绪后按选择调用optimization。诊断及报告分析仅给建议。

原始数据和结果分别由Dataset、EvalTask、EvalResult及TaskEvent维护。AgentRun保存对话与跟踪轮次；AgentEvent、AgentMessage记录主流程；AgentDelegation.evidence_json保存专项的公开输入、响应、工具与结果；AgentGraphCheckpoint保存恢复状态，不把私有思维链当作执行记录。

新增agent_report_revisions表（AgentReportRevision）：保存会话、Run、任务、委派、草稿内容、原报告hash、证据hash、状态及发布时间。优化稿单独生成；人工发布前复核原报告与证据hash，保留原始评分。已发布稿可撤回，历史版本不删除。原始任务报告接口继续提供原始报告，优化版本从Agent会话下载。

## API 与页面

接口前缀/api/agents；以下接口均检查当前操作者和会话对象可见性。

| 接口 | 权限 | 用法 |
| --- | --- | --- |
| POST /sessions | agent:invoke | planner_model_id配合默认auto_plan=true自动规划；auto_plan=false用于明确只创建规则草案的接口场景 |
| POST /sessions/{sid}/runs | agent:invoke | 默认purpose=dialogue；已关联任务可显式传purpose=followup重新核对实际终态，不会重新执行评测 |
| GET /sessions/{sid}/runs?page=1&page_size=50 | agent:view | 按创建顺序分页列出全部Run，返回turn、purpose、输入、阶段与状态 |
| GET /sessions/{sid}/delegations?run_id=… | agent:view | 查询指定轮次的全部专项结果及可折叠证据 |
| GET /sessions/{sid}/report-revisions | agent:view | 查询优化稿和历史状态 |
| GET /report-revisions/{id}/download | agent:view | 下载独立Markdown优化稿 |
| POST /report-revisions/{id}/publish | agent:confirm | 人工确认发布，原报告或证据变化返回409 |
| POST /report-revisions/{id}/revert | agent:confirm | 撤回已发布优化稿，保留审计和原报告 |

主Agent新增get_resource_inventory与get_task_evidence受控工具。工具还需进入主配置和子Agent的白名单；MCP仍受会话绑定、目录Schema、resource:invoke和对象授权限制。

页面“每轮执行明细”支持上一轮、下一轮、下拉选择与“跟随最新”。历史轮次查看不停止后台跟踪。普通新对话以异步Run提交，避免前端30秒请求超时。每轮专项独立折叠，显示角色、状态、模型轮次、用量、完整公开输入及工具返回；主时间线仍可展开原始事件。报告版本卡提供草稿预览、下载、人工发布和撤回。

## 运维与验证

默认由API进程中的Agent worker执行；也可按既有部署使用独立worker。关闭页面不停止已确认会话的跟踪。正常进程退出时，取消中的节点回滚后释放自身租约；异常进程退出仍须等待租约到期，后续claim用fencing token屏蔽旧所有者。

长节点外部请求未返回时不会保证立即取消；专项记录在相应节点事务提交后可见。资源快照有上限，需要时使用搜索工具。模型用量包含输入、输出和子Agent调用，最后一次调用可能超出预算；预算暂停须提高预算并创建新Run，不能把该轮当作成功。轮次历史仍保留。

隔离回归使用tests/isolated_env.py，验证资源授权、关键词角色绑定、公开协议记录及去重、任务快照跟踪、历史分页、报告发布证据保护、审批与恢复等。脚本化模型响应只用于基础设施回归，不计为真实模型验收。

真实演示脚本：backend/scripts/demo_agent_development.py。在backend目录使用现有.venv，读取.env的真实模型连接，仅经当前开发服务认证API创建资源及执行。脚本限制现有本地开发配置，不导入isolated_env、不创建数据库、不直接插入任务或评分。脚本保留数据，并将脱敏ID、状态、委派及报告版本写入[开发演示证据](agent-development-evidence-2026-10-24.json)。

```powershell
cd backend
.venv/Scripts/python.exe scripts/demo_agent_development.py --prepare-only
.venv/Scripts/python.exe scripts/demo_agent_development.py
```

真实工具来自项目自带tools/stats_service，地址127.0.0.1:8765；重启服务使用tools/stats_service/run.ps1。解析、统计、工作流Skill和MCP均有实际调用记录。模型接入复用.env供应商，所以不同“被测模型”名称表示独立配置对象，并不宣称不同供应商或不同基础权重。题集由AI生成，参考答案可人工核对，不能替代行业基准。

四个自定义角色的触发词、阶段和测试输入见[用户手册17.6节](../user-manual/大模型智能评测平台用户使用手册.md)。运行状态及真实测试结论以证据文件和关联任务为准；预算暂停、失败和中断记录同样保留，不冒充成功。

## 实际验证结果

截至2026-10-24，本轮61项隔离回归通过，另1项自动规划未知用量专项回归通过；前端构建、权限采集及diff空白检查通过。浏览器验证了历史轮次切换、子Agent完整公开记录展开、优化稿人工发布与撤回，检查时未见控制台错误。

经业务API再次读取原库，6个真实任务共72条结果：5个成功任务有60条execution_status=ok、score_status=scored、非模拟评分结果；1个故障演示任务有12条真实执行失败记录，score为null。6个会话共44次子Agent委派。汇总及结果事实hash见[最终核对证据](agent-lifecycle-verification-2026-10-24.json)。

| 会话 | 任务 | 实际结果与用途 |
| --- | --- | --- |
| 16 | 40 | 修复后从新建会话开始的完整复测；12条实测成功；规划、客服覆盖、数据覆盖、监控、审校、优化全部完成 |
| 11 | 35 | 客服回归，12条成功；历史预算暂停和新轮次保留；修订#1已测试发布、撤回 |
| 12 | 36 | 金融数值，12条成功；finance_verifier实际调用compute_stats，工具返回count=3、mean=60 |
| 13 | 37 | 数据覆盖审查，12条成功；报告优化修订#3 |
| 14 | 38 | 真实供应商拒绝故意配置的无效型号；12条失败；diagnose和failure_analyst实际运行，保留失败结论和修订#4 |
| 15 | 39 | 报告边界题集，12条成功；修复后跟踪Run#23核对终态并生成修订#5 |

最完整的后修复验证见[会话16证据](agent-fresh-lifecycle-evidence-2026-10-24.json)：任务#40在running、58%时留下监控记录，继续等待，直到success、100%后才结束，measured_results=12，报告优化修订#6已保存。故障链路详情见[会话14证据](agent-failure-development-evidence-2026-10-24.json)。

真实验证修复了预算暂停遗留规划标记、排队中的审批节点无法进入等待、进度唤醒误结束跟踪、旧计划审批轮不能承接新确认计划等问题。早期Run#19/#21曾提前结束，历史保留；新Run#22/#23已分别核对真实失败及成功终态。正常关闭、预算暂停和失败记录均不计为正式评测通过。

当前仍为本地SQLite开发验证，长模型节点会延迟其他写请求；未进行生产并发压测或全行业准入验收。模型生成的优化稿仍需人工核对。用户手册V1.4已更新并生成Word，结构检查通过；因环境缺少LibreOffice，Word逐页排版未核验，以Markdown为阅读基准。
