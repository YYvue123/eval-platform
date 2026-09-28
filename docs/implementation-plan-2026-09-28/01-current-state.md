# 现状核查与需求差距

本文件路径均相对仓库根目录；函数名是稳定定位点。条文 D/I 的段落编号见本目录两份原文索引。缺失结论指当前仓库代码，不代表企业基础设施一定不存在。

## 1 优先处理的正确性问题

| 编号 | 证据 | 影响与结论 | 工作包 |
|---|---|---|---|
| B01 | `backend/app/services/task_runner.py:236` 调用 `run_builtin_tool`，本文件无导入；异常分支设 score=0；288 行仍设 success | 静态确认未定义引用，裁判失败被掩盖；现有端到端测试只检查 success 和条数，不能证明分数正确 | WP00 |
| B02 | `builtin_tools.py::run_builtin_tool` 的 hallucination 分支使用 `prediction in ref`；watermark 分支搜索 reference | 纯函数复现：空 prediction、reference=北京获得满分；空 prediction、reference=AIGC 也通过标识检测 | WP00、WP12 |
| B03 | `task_runner.py` 只调用内置工具；`api/resources.py::invoke_resource` 另有 HTTP/Skill/MCP 分发 | 注册了外部裁判不等于任务能够调用，两个路径的鉴权、限流、追踪不一致 | WP02 |
| B04 | `api/agents.py::confirm_session` 直接构造 EvalTask；`validate_eval_config` 无模型 ACL/场景校验；普通 `api/tasks.py::create_task` 有此校验 | Agent 确认路径与常规任务校验不一致；另无已确认状态守卫和幂等约束，重复提交可重复创建任务。需隔离集成测试补证 | WP01、WP03、WP08 |
| B05 | `task_queue.py::dispatch_queue` 查运行数后依次 await；无原子 claim；runner 长事务仅 flush | 并发领取竞争、状态可见性差、取消读取可能命中同一 Session 缓存；重启恢复和真分布式执行未实现 | WP04 |
| B06 | `datasets.py::patch_item` 与 `quality.py::handle_issue` 原位改历史 DatasetItem | 版本 ID、checksum 与实际内容可能不一致；已有任务无法保证复现 | WP03 |
| B07 | runner 根据 task.model_id 读取当前 EvalModel，而非冻结 ModelAccessConfig；工具版本只是记录当前值 | 历史模型版本 ID 存在不等于执行了历史配置，资源重新注册覆盖旧 manifest | WP02、WP03 |
| B08 | `batch.py::get_shard` 可省略 snapshot_id，未验证传入快照属于 batch；`freeze_snapshot` 未校验 version 属于 dataset | 跨批次/跨数据集引用和读取风险；还缺租户范围校验 | WP01、WP05 |
| B09 | batch 结果写入无分片边界/样本成员校验；失败明细重复 extend；预算耗尽设 failed | 错误分片可影响进度、重复结果污染统计，且不符 I9.5 暂停语义 | WP05 |
| B10 | `protocol.py` response 将 status 放 header，auth={}，usage 在顶层；每次 response 新建 trace_id | 不满足 I4 的 body.status/result/metadata.usage、caller_id 和连续 trace；“信封1.3已实现”不可作为兼容证明 | WP02 |
| B11 | 规范 side_effects 位于 Manifest 顶层数组，`resources.py` 却读取 capabilities.side_effects | 按规范声明的副作用可能未被拦截；数组放错位置还可能触发不可 hash 的错误。Mock 返回不等于真实沙箱 | WP06 |
| B12 | `api/datasets.py`、agents、tasks 等 list/get 只有动作权限，缺对象过滤；workspace 仅账面配额 | 已有 RBAC 不等于租户隔离，用户对未授权对象的访问范围必须补齐 | WP01 |
| B13 | `leaderboard.py::latest_success_tasks` 不排除 trial/mock/不同比较集；成本按每条0.2秒估算 | 榜单可混入不可比结果，性价比没有真实成本依据 | WP13 |
| B14 | `tasks.py::shadow_service` 直接信任 production/candidate 字典，promote 缺完整真实验证 | 是影子指标录入原型，不是实际影子调用和评分灰度 | WP14 |
| B15 | health_check 将 HTTP<500 当健康；ops_acceptance 多个 ok 写死 True | 401/403/404 不代表可用；准入验收页不能作为实际验收证据 | WP03、WP15 |
| B16 | requirements.txt使用sqlalchemy>=2.0.25未声明asyncio extra；隔离解析到2.1.1后缺greenlet | 按当前未锁定依赖安装出现10项测试导入/启动错误；仅在隔离环境补依赖后11项基础/接口测试通过，端到端任务仍45秒超时 | WP00、WP04 |

端到端超时的线程转储显示aiosqlite调用与TestClient等待；结合run_task中commit后又flush审计、BackgroundTasks及长事务设计，存在SQLite锁等待嫌疑。当前证据不足以断言唯一根因，需WP00/WP04对锁持有和依赖清理时序进一步定位；不能把该环境观察推断成所有部署均失败。

## 2 业务需求追踪矩阵

“基础已实现”行仍继承 B01—B15 所列横切限制。以下按可交付能力分组，不把重复的输入输出表计为新功能。

| ID | 原始需求 | 当前状态与证据 | 待补内容 | 工作包 |
|---|---|---|---|---|
| D01 | 数据上传/解析/预览 D§5.3.2.1.1.5.1—2 | 基础已实现：`datasets.py::preview_import/import_dataset`、`dataset_parser.py` | 流式大文件、文件限额/ZIP解压限额、失败回收；.xls 用 openpyxl 路径不能算旧格式支持 | WP03 |
| D02 | 分类/标签 D§1.1.5.3—4 | 部分：标签 CRUD、条目 data_label、dataset tags | 统一字典、多对多条目标签、同义提示、使用统计和占用删除 | WP03 |
| D03 | 版本/比较/回滚 D§1.1.5.5 | 部分：DatasetVersion、rollback_version | 不可变版本、逐条 diff、元信息与清洗也生成版本、回滚后复审 | WP03 |
| D04 | 多条件检索 D§1.1.5.6 | 部分：分页、关键词、状态等过滤 | 创建/更新时间范围、标签组合语义、所有查询的对象权限 | WP01、WP03 |
| D05 | 多格式指定范围导出 D§1.1.5.7 | 基础已实现：export_dataset | 导出字段/筛选范围契约、敏感审批和脱敏、大文件异步任务 | WP03 |
| D06 | 数据发布/停用/归档/删除 D§1.1.6 | 部分：提交/审核/发布/逻辑删除及任务占用拦截 | 明确迁移表和已发布不可变约束、正式调用必须发布且质检有效 | WP03 |
| D07 | 任务关联与血缘 D§1.1.5.8 | 部分：DatasetLog、EvalLineage | 血缘与实际读取一致；版本引用所有权校验、样本摘要和原始制品定位 | WP03、WP05 |
| M01 | 模型注册与元信息 D§1.2.5.1/3 | 基础已实现：ModelMeta、models CRUD | I10 内外模型必填字段与模型 manifest 统一校验 | WP03 |
| M02 | 请求/响应映射 D§1.2.5.2 | 部分：model_client.build_request_body/parse_response | 字符串替换转类型安全映射，错误不得静默退默认；多轮、多模态、usage | WP03、WP11 |
| M03 | 模型版本 D§1.2.5.4 | 部分：ModelVersion、ModelAccessConfig | 执行严格读取 pinned 配置；历史证书和凭证引用轮换语义 | WP03 |
| M04 | 健康/周期探测/运行日志 D§1.2.5.5—6/10 | 基础已实现：health_probe、ModelCallLog | 推理探针、401分类、SLA窗口、真实百分位指标、共享半开限流 | WP03、WP15 |
| M05 | 模型 ACL/白名单 D§1.2.5.9 | 部分：_acl_allows 和常规任务创建 | Agent、测试、重试等所有入口统一；运行时权限撤销生效 | WP01 |
| M06 | 加密企业接入 I10.4 | 部分：tls_channel、通道字段 | 生产禁明文、每资源证书、IP白名单、证书到期、真实联调与交付材料 | WP03、WP15 |
| Q01 | 完整性/长度/精确重复/乱码 D§1.3.5 | 基础已实现：quality_checker 五条规则、QualityIssue | 规则版本化和规则实际生效校验 | WP03 |
| Q02 | 格式/准确性/一致性/近重复 D§1.3.5.2—6 | 部分或未见：当前规则不含领域准确性和语义一致性检测 | JSON Schema、领域约束、近重复候选、人工审核与来源证据 | WP10 |
| Q03 | 质量分/问题闭环/清洗建议/报告 D§1.3.5.7—11 | 部分：工单处理、静态建议、报告归档 | 清洗生成新版本并复检，维度权重、误报处置、规则与报告血缘 | WP03、WP10 |
| P01 | 模板/变量/分类/版本/审核 D§1.4.5 | 基础已实现：prompts.py 多个接口与页面 | 变量类型/必填校验、发布版本冻结、对象访问范围 | WP03 |
| P02 | 自动生成与优化 D§1.4.5.4—5 | 原型：prompt_craft 固定模板/规则建议 | 模型生成候选、独立开发集、预算搜索与保留集验证，不能直接替换已发布版本 | WP10 |
| P03 | 效果测试/效果分析/调用日志 D§1.4.5.6/9—10 | 部分：PromptTest/日志/统计 | 同数据同标尺配对实验、置信区间、真实延迟成本、候选选择证据 | WP10 |
| T01 | 任务定义/模板/审核 D§2.3 | 基础已实现：tasks.py 与 Tasks.vue | 统一 TaskService、完整状态机、多模型×多数据集实验展开 | WP03、WP04 |
| T02 | 优先级/依赖/窗口 D§2.3 | 部分：单 depends_on_id、MAX_PARALLEL=4 | DAG、环检测、失败传播、公平调度、周期任务、资源约束 | WP04 |
| T03 | 子任务/并行/恢复 D§2.3 | 原型：50条一组记录，循环串行执行 | 独立 worker、lease、fencing、样本 checkpoint、幂等回写、重启恢复 | WP04、WP05 |
| T04 | 事件/告警/取消 D§2.3 | 部分：TaskEvent、站内通知、cancel API | outbox、事件消费、实时进度、取消可见性、告警去重和关闭 | WP04、WP15 |
| T05 | 结果/报告归档 D§2.3 | 部分：7种摘要格式 | 样本明细、证据、统计口径、渲染失败显式状态、异步可恢复生成 | WP13 |
| E01 | 语言能力 D§2.1 | 原型：2题文本包与规则裁判 | 合格题库、标尺、人工校准、质量与稳定性指标 | WP11 |
| E02 | 语音/视觉/多模态 D§2.1 | 未见真实模态执行：eval_packs 文本模拟 | 真实媒体资产、模型适配器、专用指标与人工复核 | WP11 |
| E03 | 对话/表格/写作/代码/RAG 等11场景 D P2653—2665 | 原型：task_catalog 与两题通用包 | 逐场景 evaluator 和环境，不能共享 contains 作为正式裁判 | WP11 |
| E04 | 单/多智能体被测对象 D P2660—2661、I1.3 | 未见独立 MUT runtime | 场景环境、工具 stub、最终状态 oracle、交互轨迹与协作度量 | WP11 |
| E05 | 14行业专项 D§2.1 | 原型：行业模板和通用“合规/拒绝”样本 | 每行业指标定义、专家金标、适用版本、许可与覆盖度 | WP11 |
| S01 | 生成内容风险 D P2684—2690 | 原型：关键词拒绝判断 | 分级风险、多轮受控自适应场景、安全/过拒联合评估、人工裁判校准 | WP12 |
| S02 | 显隐式标识/鲁棒性 D P2692—2699 | 原型：关键词 | 元数据/签名/OCR/媒体变换、适用规则版本、复核，禁止声称自动法律结论 | WP12 |
| S03 | 价值对齐 D P2700—2707 | 原型：字符串相似度 | 视角/语境变换、立场稳定性、文化分层、争议复核、动态集独立版本 | WP12 |
| S04 | 幻觉 D P2708—2715 | 原型且有 B02 | 断言与证据校验、对象属性关系时序分层、不可判定、检索证据与修正率 | WP12 |
| A01 | 需求理解和计划 D P2744—2748 | 原型：infer_dims/draft_plan | 真实规划模型、澄清、资源检索、结构化计划与版本 | WP07、WP08 |
| A02 | 监控 Agent D P2750 | 原型：手动接口读状态 | 每任务逻辑监控实例、事件触发、变化去重、趋势证据、按需模型分析 | WP09 |
| A03 | 诊断 Agent D P2752 | 原型：状态分支固定建议 | 因果证据、假设验证、部分重试/补测建议、审批后由工具执行 | WP09 |
| A04 | 经验库 D P2753—2754 | 部分：KnowledgeEntry、contains 查询 | 来源、租户过滤、检索索引、引用、过期/撤销、审核后沉淀 | WP09 |
| A05 | 协作/上下文/预算/审批 I6 | 未见真正 agent.execute 子代理协作；有确认按钮 | 持久化运行时、工具权限交集、限轮/限时、检查点、审批绑定与防重放 | WP07—WP09 |
| L01 | 四类榜/权重/雷达/趋势 D§3.1 | 部分：leaderboard.py 和页面 | 可比 cohort、缺失显示、冻结标尺、重复实验、真实成本、发布审核 | WP13 |
| L02 | 快照/导出/异常回退 D§3.1 | 基础已实现：LeaderboardSnapshot | 按租户、筛选条件、cohort/version 缓存；明确更新时间与陈旧标记 | WP13 |
| V01 | 服务申请/报价/交付 D§3.2 | 部分：EvalServiceRequest 和手填报价 | 状态机、报价快照、真实任务生成/绑定、交付质量门禁 | WP14 |
| V02 | 工作空间/配额/计费 D§3.2 | 原型：计数器；交付时累加 | 成员、隔离、用量流水、预占/结算/释放、重复交付不重复扣费 | WP01、WP14 |
| V03 | 影子/灰度/回滚 D§3.2、I12 | 原型：提交指标与字符串切换 | 真实双路调用、独立候选副作用隔离、稳定性报告、路由原子切换 | WP14 |
| O01 | 登录/用户/角色/通知/审计 | 基础已实现：auth/users/roles/notifications/audit | 完整权限负例、禁用用户校验、生产默认凭证禁用、审计敏感脱敏 | WP01、WP15 |
| O02 | 部署/CI/备份/健康 D§4.1 | 部分：deploy、CI、backup/metrics | 容器制品、迁移、备份恢复演练、真实 readiness、滚动/蓝绿/金丝雀与IaC | WP15 |
| O03 | 系统/应用/数据/服务器监控 D§4 | 部分：进程内计数和接口 | 分布式 trace、集群指标、SLO、值班/事件响应、容量和故障演练 | WP15 |
| O04 | 社区/贡献者/团队/制度/开源 D§4.2 | 未见配套平台与制度产物 | 工单与知识库集成、贡献流程/许可清单/SBOM、值班手册；组织运营由人员执行 | WP16 |
| O05 | D§5.4 基准生态系统 | 原文只有标题 | 不臆造范围；先交付已明确的基准版本/许可/贡献审核机制，独立扩展待业务定义 | WP16 |

## 3 工具底座规范差距

| ID | I 条文 | 当前状态 | 待补 | 工作包 |
|---|---|---|---|---|
| I01 | 3 Manifest/评测标尺 | 部分：手写字段检查 | 附录A Schema、条件必填、SemVer、指标与阈值、准入记录 | WP02 |
| I02 | 4 信封/Trace/usage | 部分且格式偏差 | 四种消息 Schema、TTL、可信 caller/tenant、链路传播、真实 usage | WP02 |
| I03 | 5 sync/async/stream/batch | sync 基础；其余模式未完整 | 长任务心跳、流式末块、按模式路由与取消 | WP02、WP05 |
| I04 | 6 Agent描述/会话/协作 | 原型 | 多轮接口、agent.execute、授权工具、循环检测、预算和持久化 | WP07—WP09 |
| I05 | 7 MCP | 原型：本地 JSON-RPC 函数 tools/list/call | 真远程 initialize/协商、Tools/Resources/Prompts、通知、双缓冲、认证 | WP06 |
| I06 | 8 Skill | 原型：把 $ref 当工具ID，对每步传同一body | 四 execution_type、输出引用/全局变量、触发、版本、隔离 | WP06 |
| I07 | 9 DataSource/batch | 部分：本地 JSON快照、拉片/回写 | 来源适配、checksum校验、成员绑定、预算暂停、30秒进度、原子发布 | WP05 |
| I08 | 10 模型/Agent MUT | 模型部分、MUT未见 | 标准模型manifest与完整推理、流式、内部/外部字段、独立被测环境 | WP03、WP11 |
| I09 | 11 外部API | 部分：HTTP JSON bearer | OAuth刷新、类型映射、429退避、熔断探针、错误映射；按需协议适配 | WP02、WP06 |
| I10 | 12 注册发现/版本/灰度/SSE | 部分：DB列表、心跳、事件列表 | 多实例lease、多版本路由、真实SSE、稳定性门禁、原子灰度回滚 | WP02、WP14 |
| I11 | 13 RBAC+ABAC/凭证/沙箱 | 部分：动作RBAC与Mock分支 | 对象ABAC、网关凭证库、出口策略、独立沙箱、顶层副作用声明 | WP01、WP06 |
| I12 | 14 日志指标审计血缘 | 部分：表与进程内metrics | 统一trace、分层token/cost、完整字段、租户脱敏、保留与检索 | WP15 |
| I13 | 15 分级准入/交付 | 原型：验收状态页 | 每版本实测基础级与完整级、试点/灰度周期、证据包和审批 | WP15 |

## 4 可复用与需要替换的边界

继续复用管理页、ORM实体的稳定字段、登录/RBAC机制、数据解析、基础规则裁判、模板目录、审计入口和报告导出入口。将 API 中散落业务校验下沉到领域服务。替换规则式 Agent 内核、进程内调度假设、静态验收结果和启发式正式评分。现有 API 采用兼容适配，不建议整站重写。

未进入在线测试的边界需要保留在验收报告：现有接口能启动、外部调用可达、跨租户漏洞是否可复现以及性能上限，均不能由本次静态核查直接证明。
