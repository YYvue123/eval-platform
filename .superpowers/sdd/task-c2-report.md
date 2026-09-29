# Task C2 报告：REAL02 数据集

## 状态

**DONE** — `tests.test_real_fill` 4 项 unittest 全部通过；未 commit；未写入 `backend/eval_platform.db`。

## RED

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

**关键输出：**

```
ImportError: cannot import name 'real02_dataset' from 'tools.real_fill.scenarios'
FAILED (errors=1)
```

**失败原因：** 测试已引用 `real02_dataset`，函数尚未实现（TDD 预期 RED）。

## GREEN

**命令：**

```powershell
cd E:\eval-platform\backend
.venv\Scripts\python.exe -m unittest tests.test_real_fill -v
```

**结果：** `Ran 4 tests in 2.595s` — **OK**

| 用例 | 说明 |
| --- | --- |
| `test_isolated_url_is_not_business_db` | `DATABASE_URL` 经 `assert_isolated_database`，文件名不是业务库 `eval_platform.db` |
| `test_fill_client_login_admin` | 既有 FillClient 登录 |
| `test_real01_viewer_cannot_register` | 既有 REAL01 |
| `test_real02_dataset_import_returns_ids` | `real02_dataset` 返回正整数 `dataset_id`/`version_id`；description 含「AI 生成确定性题集」；该版本 4 条样本 |

GREEN 运行时 REAL01 仍会打出预期 `HTTPException ... status=403`；另有 Starlette TestClient 既有 deprecation warning。

## 修改文件

| 文件 | 操作 |
| --- | --- |
| `tools/real_fill/scenarios.py` | 新增 `real02_dataset`：`POST /api/datasets` → `POST /api/datasets/{id}/import`（4 条 JSON）→ `POST /api/quality/run` |
| `backend/tests/test_real_fill.py` | 新增 `test_real02_dataset_import_returns_ids` |

未改动数据集/质检 API；未创建 commit。

## 自审

- [x] TDD：先测后码；RED 为 `cannot import name 'real02_dataset'`。
- [x] 隔离 TestClient；`from tests import isolated_env`。
- [x] 未调用付费模型；题面为本地确定性问答。
- [x] 未发明字段：创建用 `DatasetCreate`（name/task_type/data_source/description）；导入用 `file` 上传；质检用已有 `POST /api/quality/run?dataset_id=&version_id=`。
- [x] 测试从 `backend/` 运行。
- [x] 未 git commit；未写 `backend/eval_platform.db`。

## 关注点

1. **`source_kind` 不在 DatasetCreate 上：** 按计划写入 `description`：`source_kind=ai_generated_input；AI 生成确定性题集`。
2. **导入字段：** JSON 键为 `input`/`answer`，走 parser 默认映射，未传 `field_mapping`。
3. **质检：** 计划写「若 API 存在则调用」；本仓库有 `/api/quality/run`，场景内要求 200，并把 `quality_status` 放进返回 dict（测试只断言 id 与 4 条）。
