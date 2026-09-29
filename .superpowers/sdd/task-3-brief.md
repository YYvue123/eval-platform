# Task 3：实现确定性统计核心

## Files

- Create: `tools/__init__.py`
- Create: `tools/stats_service/__init__.py`
- Create: `tools/stats_service/core.py`
- Create: `tools/stats_service/tests/__init__.py`
- Create: `tools/stats_service/tests/test_core.py`

## Interfaces

```python
parse_measurements(text: str) -> list[dict[str, float | str]]
compute_stats(values: list[dict], target_unit: str | None = None) -> dict
```

## Required behavior

单位表：

```python
UNITS = {
    "mm": ("length", 0.001), "cm": ("length", 0.01),
    "m": ("length", 1.0), "km": ("length", 1000.0),
    "mg": ("mass", 0.000001), "g": ("mass", 0.001), "kg": ("mass", 1.0),
    "ms": ("time", 0.001), "s": ("time", 1.0),
    "min": ("time", 60.0), "h": ("time", 3600.0),
}
```

解析正则必须避免 `m` 抢占 `mm`/`min`：

```python
MEASUREMENT = re.compile(
    r"(?<![\w.])([-+]?(?:\d+(?:\.\d+)?|\.\d+))\s*"
    r"(mm|cm|km|mg|kg|ms|min|m|g|s|h)\b",
    re.I,
)
```

`compute_stats`：
- 使用 `math.isfinite` 拒绝 NaN/Infinity；
- 拒绝空数组、未知单位、混合量纲、目标单位量纲不一致；
- 将所有值转换到 target_unit 后计算；
- target_unit 未给定时使用第一项的单位；
- 返回 JSON 可序列化的 `count/sum/mean/min/max/variance/unit/dimension/converted`；
- variance 为总体方差 `sum((x-mean)**2)/count`；
- 不允许针对样例硬编码。

## TDD tests

必须先创建测试并观察模块不存在的 RED，覆盖：

1. `"样本为 100 cm、2 m 和 500 mm"` 解析后转 m 得 `[1.0, 2.0, 0.5]`；
2. count=3，mean=3.5/3，dimension=length；
3. 1m 与 3m 的总体方差为 1.0；
4. 1m + 1kg 抛包含“量纲”的 ValueError；
5. NaN 抛包含“有限”的 ValueError；
6. 空数组；
7. 未知单位；
8. target_unit 量纲不一致。

命令：

```powershell
cd E:\eval-platform
backend\.venv\Scripts\python.exe -m unittest tools.stats_service.tests.test_core -v
```

GREEN 必须全部 PASS。

## Global constraints

- 纯确定性计算，不访问网络、不写数据库。
- 不新增依赖；使用 Python 标准库。
- 只创建列出的文件，不做相邻重构。
- 当前工作区已有用户改动，不得覆盖、删除或回滚。
- 不创建 commit。

## Report

写入 `.superpowers/sdd/task-3-report.md`，包含 RED/GREEN、测试数、文件清单、自审和关注点。
