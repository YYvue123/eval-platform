# 模型榜单与客户演示

交付日期：2026-10-24。

> 当前界面、发布复核流程及 staging 第二轮增量数据见 [榜单 V2 交付说明](LEADERBOARD-V2.md)。下文保留初版演示过程记录。

## 使用

演示地址：http://127.0.0.1:5180/leaderboard 。开发演示账号为 `admin` / `admin123`，仅用于本机 APP_ENV=dev。

初次交付使用独立开发库 `backend/leaderboard_demo.db`。随后按用户明确要求，另通过 staging API 增量创建演示配置、题集和真实评测，目标是 `.env` 指向的 `backend/eval_platform.db`；没有用演示库覆盖 staging，也没有直接复制成绩。数据库被 Git 忽略，包含接入凭证，不应发给客户或提交。对客户展示网页即可。

staging 页面地址为 http://127.0.0.1:5173/leaderboard ，API 为本机 :8000；:5180 仍是原独立开发演示环境。

staging 增量补齐命令（已存在的成功任务复用，不重复执行）：

```powershell
cd backend
./.venv/Scripts/python scripts/populate_leaderboard_demo.py --target staging
```

脚本先以 SQLite backup 保存 staging 一致性备份，并核实 API 的模型清单与目标库一致。所有新增任务通过正常平台流程重新实测，因此具有新的执行时间。结束后逐表核对原主键全部保留，并核对原数据集、版本、样本、任务、结果的内容哈希不变。记录见 `leaderboard-staging-evidence.json`，其中包含备份路径与各表前后数量。

重启时分别在两个 PowerShell 终端运行：

```powershell
./backend/scripts/serve_leaderboard_demo.ps1
./frontend/scripts/serve-leaderboard-demo.ps1
```

重新生成或补齐演示数据：

```powershell
cd backend
./.venv/Scripts/python scripts/populate_leaderboard_demo.py
```

脚本默认只写专用开发库；指定 --target staging 才通过 staging API 增量写入。经模型/数据集 API 建档、导入、真实质检、发布，再通过任务创建、提交、审核、执行 API 调用 TaskService 和执行器。不直接写成绩或调度状态；开发库过期租约通过现有 TaskService 恢复，staging 模式不恢复无关任务租约，也不修改已有演示配置的价格。

## 数据与讲解顺序

- 3 个接入别名：稳健、均衡、探索，使用同一底层模型，temperature 分别为 0、0.4、0.9。别名与底层来源明确标注，不能解释为三家厂商或三种独立模型。
- 4 个比较组、14 次真实运行、108 条样本结果。证据见 `leaderboard-demo-evidence.json`。
- 四维精确匹配：8 道小题，覆盖知识、数学、指令、代码理解，三种配置各两次运行，实测全部正确；不能视为通用能力满分。
- 四维开放文本：8 道题，三种配置各两次运行。使用 fuzzy 文本相似度，存在真实分数差异；仅演示词面相似度，不等于答案正确性或能力认证。
- 同一四维题集换 fuzzy 裁判后自动成为独立组，演示不同裁判不混排。
- 双维子集只有一份配置已测，能力档案中其余格显示“未测”，不补零。
- 前两个别名配置演示单价 0.002/千 Token、时间计价为零；第三个没有单价。费用是按真实用量与人工配置的演示单价估算，不是供应商报价或账单。

推荐演示：默认文本相似度组 → 选择模型 → 条形图、雷达、矩阵、效率、历史 → 点模型看证据与任务 → 能力档案查看不同协议和缺测 → 选择另一个比较组 → 导出。

## 实现边界

比较组包含数据版本、裁判、工具版本、规范化权重、行业、场景、提示词及提示词版本。每个模型版本单独成行，先限定协议再取最新完成结果。新接口沿用 leaderboard:view 权限，并按会话租户/数据范围过滤任务、模型、数据集。

维度来自数据集 data_label，均分来自完整的真实逐样本 scored/ok 结果；缺测不补零，不混入 trial/simulation/legacy_unverified。只有已知 0–1 合同的内置裁判可用统一雷达与热力颜色；未知尺度保留原始分且不授予排名。

能力档案逐组列出成绩，不能把各列平均成跨协议综合分。历史截面按任务结束时间回看；历史曲线是同组同模型版本的实际运行记录，不是不可变发布快照。

支持五类 ECharts 图形、悬停数值、图例切换、历史缩放、图片保存、搜索、开闭源筛选、排序、当前视图 CSV 与证据抽屉。旧四类榜单和成本编辑保留在底部高级入口。费用缺单价/用量时留空，时延使用真实结果，不再按题数估算。

本次不伪造竞技场、投票、胜率矩阵或置信区间，也不声称具备未实测的图像、视频和语音维度。

## 验证

- 后端 `tests.test_leaderboard_insights` + `tests.test_leaderboard_reports`：12 项通过，使用 tests/isolated_env.py。
- 前端图表缺值和 CSV 单测：2 项通过。
- 真实浏览器交互验收：1 项通过，覆盖五类图表、搜索、档案、CSV、证据、组切换与移动布局；API 使用真实演示库的只读备份，测试写入限定在 tests/_isolated/leaderboard-ui.db。
- 前端生产构建与 collect-permissions 通过。复用已有 leaderboard:view/edit 与 task:view，无新增权限码。
- 截图位于 `leaderboard-screenshots/`。

浏览器验收前应将 demo DB 使用 SQLite backup 复制到 tests/_isolated/leaderboard-ui.db，启动隔离 API :8011，并以 VITE_API_PROXY_TARGET=http://127.0.0.1:8011 启动前端 :5181，然后执行：

```powershell
cd frontend
node node_modules/@playwright/test/cli.js test --config=playwright.leaderboard.config.mjs
```
