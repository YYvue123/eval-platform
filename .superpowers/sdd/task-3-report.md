# Task 3 报告：确定性统计核心

## 状态

**DONE**

确定性统计核心已完成（含两轮 Review Fix）。当前 **`tools.stats_service.tests.test_core`：10/10 PASS**。未做 Task 4 HTTP/MCP，未修改既有业务文件，未创建 commit。

| 阶段 | 用例数 | 说明 |
|------|--------|------|
| 初版 GREEN | 7 | 见下方「RED / GREEN」历史记录 |
| Review Fix #1 | 9 | 换算/统计溢出与非有限聚合 |
| Review Fix #2（当前） | **10** | `parse_measurements` 拒绝 `float()` 为 inf 的超长十进制 |

## RED

命令：

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest tools.stats_service.tests.test_core -v
```

关键输出：

```text
ImportError: Failed to import test module: test_core
...
ModuleNotFoundError: No module named 'tools.stats_service.core'
----------------------------------------------------------------------
Ran 1 test in 0.000s
FAILED (errors=1)
```

说明：loader 将导入失败计为 1 个 ERROR，符合「模块不存在」预期。

## GREEN

命令：与 RED 相同。

关键输出：

```text
test_parse_then_compute_length ... ok
test_population_variance ... ok
test_rejects_empty_values ... ok
test_rejects_mixed_dimensions ... ok
test_rejects_non_finite_values ... ok
test_rejects_target_unit_dimension_mismatch ... ok
test_rejects_unknown_unit ... ok
----------------------------------------------------------------------
Ran 7 tests in 0.001s
OK
```

## 测试覆盖（简报 8 项 → 7 个用例）

| # | 简报要求 | 对应用例 |
|---|----------|----------|
| 1–2 | 解析「100 cm、2 m、500 mm」转 m 为 `[1.0,2.0,0.5]`；count=3、mean=3.5/3、dimension=length | `test_parse_then_compute_length` |
| 3 | 1m 与 3m 总体方差 1.0 | `test_population_variance` |
| 4 | 1m + 1kg → ValueError 含「量纲」 | `test_rejects_mixed_dimensions` |
| 5 | NaN → ValueError 含「有限」 | `test_rejects_non_finite_values` |
| 6 | 空数组 | `test_rejects_empty_values` |
| 7 | 未知单位 | `test_rejects_unknown_unit` |
| 8 | target_unit 量纲不一致 | `test_rejects_target_unit_dimension_mismatch` |

**测试数量（初版）：7** — 当前全集见顶部 **10/10**。

## 新建文件

| 路径 | 说明 |
|------|------|
| `tools/__init__.py` | 包占位 |
| `tools/stats_service/__init__.py` | 子包占位 |
| `tools/stats_service/core.py` | `UNITS`、`MEASUREMENT`、`parse_measurements`、`compute_stats` |
| `tools/stats_service/tests/__init__.py` | 测试包占位 |
| `tools/stats_service/tests/test_core.py` | 核心单元测试 |

## 实现要点

- `MEASUREMENT` 单位 alternation 顺序：`mm|cm|km|mg|kg|ms|min|m|g|s|h`，避免 `m` 抢占 `mm`/`min`。
- 换算：`value * factor(from) / factor(to)`，`factor` 为相对该量纲基准（如 m、kg、s）的倍数。
- `target_unit` 缺省时使用首条样本单位。
- 方差：总体方差 `sum((x-mean)**2)/count`。
- 校验：`_require_finite`（输入、解析、`float()`、换算、聚合统计）、非空、未知单位、混合量纲、目标单位量纲不一致。

## 自审

- [x] 纯函数，无网络/数据库/新依赖。
- [x] 未对简报样例硬编码返回值。
- [x] 仅创建简报列出的 5 个路径（含 `core.py`）。
- [x] 错误信息含简报要求的「量纲」「有限」子串（对应用例）。
- [x] 返回字段为 JSON 可序列化原生类型。

## 关注点

1. **`parse_measurements` 无匹配时** 返回空列表；若直接 `compute_stats([])` 会报「样本不能为空」——调用方需区分「文本无测量」与「统计空样本」。
2. **极端大样本累加** 仍可能在 `sum` 阶段溢出，由 `_require_finite` 拒绝；未做 decimal 精确算术。
3. **`target_unit=None` 且多样本不同单位同量纲** 时以首条单位为目标单位；集成文档宜说明默认规则。

## Commit

无（按用户要求未提交）。

---

## Review Fix：换算/统计溢出与非有限结果

### 问题

有限输入在单位换算或聚合时可能产生 `inf`/`nan`（如 `1e308 km` → `mm`），此前未拦截，违反「拒绝非有限值」与 JSON 可序列化约束。

### RED

先新增 `test_rejects_infinity_input`、`test_rejects_conversion_overflow`，再在未改 `core.py` 前跑溢出用例：

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest tools.stats_service.tests.test_core.StatsCoreTest.test_rejects_conversion_overflow -v
```

关键输出：

```text
test_rejects_conversion_overflow ... FAIL
AssertionError: ValueError not raised
```

（`test_rejects_infinity_input` 在既有输入 `isfinite` 校验下已为 ok。）

### 修改

`core.py`：新增 `_require_finite`；换算 `_to_target`、以及 `sum`/`mean`/`min`/`max`/`variance` 结果均经有限性校验，否则 `ValueError`（信息含「有限」）。

### GREEN

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest tools.stats_service.tests.test_core -v
```

关键输出：

```text
test_parse_then_compute_length ... ok
test_population_variance ... ok
test_rejects_conversion_overflow ... ok
test_rejects_empty_values ... ok
test_rejects_infinity_input ... ok
test_rejects_mixed_dimensions ... ok
test_rejects_non_finite_values ... ok
test_rejects_target_unit_dimension_mismatch ... ok
test_rejects_unknown_unit ... ok
----------------------------------------------------------------------
Ran 9 tests in 0.001s
OK
```

**测试数量（Review Fix #1 当时）：9**

---

## Review Fix #2：解析超长十进制 → inf

### 问题

`parse_measurements('9'*400 + ' m')` 经 `float()` 得 `inf` 仍被 append，绕过有限性约束。

### RED

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest tools.stats_service.tests.test_core.StatsCoreTest.test_rejects_parse_non_finite_decimal -v
```

关键输出：

```text
test_rejects_parse_non_finite_decimal ... FAIL
AssertionError: ValueError not raised
```

### 修改

`parse_measurements`：每条匹配 `float()` 后立即 `_require_finite`，再 append（不截断、不跳过）。

### GREEN

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest tools.stats_service.tests.test_core -v
```

关键输出：

```text
test_parse_then_compute_length ... ok
test_population_variance ... ok
test_rejects_conversion_overflow ... ok
test_rejects_empty_values ... ok
test_rejects_infinity_input ... ok
test_rejects_mixed_dimensions ... ok
test_rejects_non_finite_values ... ok
test_rejects_parse_non_finite_decimal ... ok
test_rejects_target_unit_dimension_mismatch ... ok
test_rejects_unknown_unit ... ok
----------------------------------------------------------------------
Ran 10 tests in 0.001s
OK
```

**当前测试数量：10**
