"""评测数据文件解析：Excel / CSV / JSON / JSONL / TXT / ZIP。"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path


INPUT_KEYS = ("input", "question", "prompt", "query", "input_content", "原文", "问题")
REF_KEYS = ("reference", "answer", "output", "label", "reference_answer", "expected_output", "答案", "参考答案")
REQ_KEYS = ("requirement", "task_requirement", "instruction", "任务要求")
LABEL_KEYS = ("data_label", "tag", "标签")
DIFF_KEYS = ("difficulty", "difficulty_level", "难度")
EXPECTED_KEYS = ("expected", "expected_output")

TARGET_KEYS = {
    "input_content": INPUT_KEYS,
    "reference_answer": REF_KEYS,
    "expected_output": EXPECTED_KEYS,
    "task_requirement": REQ_KEYS,
    "difficulty_level": DIFF_KEYS,
    "data_label": LABEL_KEYS,
}


def _pick(row: dict, keys: tuple[str, ...], default: str = "") -> str:
    lower = {str(k).strip().lower(): v for k, v in row.items()}
    for key in keys:
        val = lower.get(key.lower())
        if val is not None and str(val).strip() != "":
            return str(val)
    return default


def normalize_row(row: dict, index: int) -> dict:
    extra = {k: v for k, v in row.items() if k}
    return {
        "item_no": index,
        "input_content": _pick(row, INPUT_KEYS),
        "reference_answer": _pick(row, REF_KEYS),
        "expected_output": _pick(row, EXPECTED_KEYS),
        "task_requirement": _pick(row, REQ_KEYS),
        "difficulty_level": _pick(row, DIFF_KEYS),
        "data_label": _pick(row, LABEL_KEYS),
        "extended_content": extra,
    }


def suggest_mapping(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    lower = {str(c).strip().lower(): c for c in columns if c}
    used = set()
    for target, keys in TARGET_KEYS.items():
        for key in keys:
            src = lower.get(key.lower())
            if src and src not in used:
                mapping[target] = src
                used.add(src)
                break
    return mapping


def apply_mapping(raw_rows: list[dict], mapping: dict | None) -> list[dict]:
    if not mapping:
        return [normalize_row(row, i) for i, row in enumerate(raw_rows, start=1)]
    rows = []
    for i, row in enumerate(raw_rows, start=1):
        def val(field: str) -> str:
            src = mapping.get(field)
            if not src:
                return ""
            v = row.get(src)
            return "" if v is None else str(v)
        extra = {k: v for k, v in row.items() if k}
        rows.append({
            "item_no": i,
            "input_content": val("input_content"),
            "reference_answer": val("reference_answer"),
            "expected_output": val("expected_output"),
            "task_requirement": val("task_requirement"),
            "difficulty_level": val("difficulty_level"),
            "data_label": val("data_label"),
            "extended_content": extra,
        })
    return rows


def parse_bytes(filename: str, data: bytes, mapping: dict | None = None) -> list[dict]:
    raw = parse_raw_bytes(filename, data)
    return apply_mapping(raw, mapping)


def parse_raw_bytes(filename: str, data: bytes) -> list[dict]:
    name = (filename or "").lower()
    if name.endswith(".zip"):
        return _parse_zip_raw(data)
    if name.endswith(".jsonl"):
        return _parse_jsonl_raw(data.decode("utf-8-sig"))
    if name.endswith(".json"):
        return _parse_json_raw(data.decode("utf-8-sig"))
    if name.endswith(".csv") or name.endswith(".txt"):
        text = data.decode("utf-8-sig")
        if name.endswith(".txt") and "," not in text.split("\n", 1)[0] and "\t" not in text.split("\n", 1)[0]:
            return _parse_txt_raw(text)
        return _parse_csv_raw(text)
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return _parse_excel_raw(data)
    raise ValueError("不支持的文件格式，请上传 Excel、CSV、JSON、JSONL、TXT 或 ZIP")


def preview_raw(filename: str, data: bytes, limit: int = 20) -> dict:
    raw = parse_raw_bytes(filename, data)
    columns: list[str] = []
    seen = set()
    for row in raw[:200]:
        for k in row.keys():
            if k not in seen:
                seen.add(k)
                columns.append(str(k))
    mapping = suggest_mapping(columns)
    sample = raw[:limit]
    return {
        "total": len(raw),
        "columns": columns,
        "suggested_mapping": mapping,
        "sample": sample,
    }


def _as_list(payload):
    if isinstance(payload, dict):
        for key in ("items", "data", "samples"):
            if isinstance(payload.get(key), list):
                return payload[key]
        return [payload]
    if not isinstance(payload, list):
        raise ValueError("JSON 内容必须是对象数组")
    return payload


def _parse_json_raw(text: str) -> list[dict]:
    payload = _as_list(json.loads(text))
    rows = []
    for item in payload:
        if isinstance(item, str):
            item = {"input": item}
        if isinstance(item, dict):
            rows.append({str(k): v for k, v in item.items() if k is not None})
    return rows


def _parse_jsonl_raw(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if isinstance(obj, str):
            obj = {"input": obj}
        if isinstance(obj, dict):
            rows.append({str(k): v for k, v in obj.items() if k is not None})
    return rows


def _parse_csv_raw(text: str) -> list[dict]:
    sample = text[:2048]
    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;") if sample.strip() else csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = []
    for row in reader:
        rows.append({k: v for k, v in row.items() if k is not None})
    return rows


def _parse_txt_raw(text: str) -> list[dict]:
    return [{"input": line.strip()} for line in text.splitlines() if line.strip()]


def _parse_excel_raw(data: bytes) -> list[dict]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError("服务器未安装 openpyxl，无法解析 Excel") from exc
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = next(rows_iter, None)
    if not headers:
        return []
    keys = [str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(headers)]
    rows = []
    for values in rows_iter:
        row = {keys[j]: ("" if v is None else v) for j, v in enumerate(values) if j < len(keys)}
        rows.append(row)
    return rows


def _parse_zip_raw(data: bytes) -> list[dict]:
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir() or info.filename.startswith("__MACOSX"):
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix not in {".json", ".jsonl", ".csv", ".txt", ".xlsx", ".xls"}:
                continue
            part = zf.read(info.filename)
            rows.extend(parse_raw_bytes(info.filename, part))
    return rows
