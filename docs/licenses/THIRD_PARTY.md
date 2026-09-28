# 第三方组件与许可清单

生成建议：`python deploy/generate_sbom.py sbom.json`（CI 已跑）。

本文件为**人工维护摘要**，完整依赖以 `backend/requirements.txt` / `frontend/package-lock.json` 与 SBOM 为准。升级依赖后请更新本表关键行。

| 组件 | 用途 | 许可（以上游为准） |
|---|---|---|
| FastAPI / Starlette / Pydantic | 后端 API | MIT |
| SQLAlchemy / aiosqlite | ORM / SQLite | MIT |
| httpx | HTTP 客户 | BSD-3-Clause |
| Vue 3 / Vite / Element Plus | 前端 | MIT |
| ECharts | 榜单图表 | Apache-2.0 |

## 数据与基准

评测样本、金标、企业日志**不在**开源依赖之列；使用前须有 `DataAuthorization`（license_spdx + grantor + purpose）。缺失授权不得用于正式任务。

## 停用

组件停用时在本表标注 deprecated 日期并保留行；SBOM 历史由 CI 产物归档，不删库内授权记录。
