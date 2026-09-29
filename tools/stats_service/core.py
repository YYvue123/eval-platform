from __future__ import annotations

import math
import re

UNITS = {
    "mm": ("length", 0.001),
    "cm": ("length", 0.01),
    "m": ("length", 1.0),
    "km": ("length", 1000.0),
    "mg": ("mass", 0.000001),
    "g": ("mass", 0.001),
    "kg": ("mass", 1.0),
    "ms": ("time", 0.001),
    "s": ("time", 1.0),
    "min": ("time", 60.0),
    "h": ("time", 3600.0),
}

MEASUREMENT = re.compile(
    r"(?<![\w.])([-+]?(?:\d+(?:\.\d+)?|\.\d+))\s*"
    r"(mm|cm|km|mg|kg|ms|min|m|g|s|h)\b",
    re.I,
)


def _require_finite(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("数值必须为有限数")
    return value


def parse_measurements(text: str) -> list[dict[str, float | str]]:
    results: list[dict[str, float | str]] = []
    for match in MEASUREMENT.finditer(text):
        value = _require_finite(float(match.group(1)))
        unit = match.group(2).lower()
        results.append({"value": value, "unit": unit})
    return results


def _normalize_unit_key(unit: str) -> str:
    key = unit.lower()
    if key not in UNITS:
        raise ValueError(f"未知单位: {unit}")
    return key


def _to_target(value: float, from_unit: str, target_unit: str) -> float:
    from_dim, from_factor = UNITS[from_unit]
    to_dim, to_factor = UNITS[target_unit]
    if from_dim != to_dim:
        raise ValueError("量纲不一致，无法混合计算")
    return _require_finite(value * from_factor / to_factor)


def compute_stats(
    values: list[dict], target_unit: str | None = None
) -> dict:
    if not values:
        raise ValueError("样本不能为空")

    parsed: list[tuple[float, str]] = []
    for item in values:
        raw_value = item.get("value")
        raw_unit = item.get("unit")
        if raw_unit is None:
            raise ValueError("未知单位")
        unit_key = _normalize_unit_key(str(raw_unit))
        if raw_value is None:
            raise ValueError("数值必须为有限数")
        value = _require_finite(float(raw_value))
        parsed.append((value, unit_key))

    first_unit = parsed[0][1]
    dimension = UNITS[first_unit][0]
    resolved_target = (
        _normalize_unit_key(target_unit) if target_unit is not None else first_unit
    )
    target_dimension = UNITS[resolved_target][0]
    if target_dimension != dimension:
        raise ValueError("目标单位量纲与样本量纲不一致")

    converted: list[float] = []
    for value, unit_key in parsed:
        if UNITS[unit_key][0] != dimension:
            raise ValueError("量纲不一致，无法混合计算")
        converted.append(_to_target(value, unit_key, resolved_target))

    count = len(converted)
    total = _require_finite(sum(converted))
    mean = _require_finite(total / count)
    minimum = _require_finite(min(converted))
    maximum = _require_finite(max(converted))
    variance = _require_finite(sum((x - mean) ** 2 for x in converted) / count)

    return {
        "count": count,
        "sum": total,
        "mean": mean,
        "min": minimum,
        "max": maximum,
        "variance": variance,
        "unit": resolved_target,
        "dimension": dimension,
        "converted": converted,
    }
