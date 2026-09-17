"""评测报告归档：JSON/Markdown/CSV/Excel/Word/HTML/PDF 摘要。"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook

from app.config import settings
from app.models import EvalTask
from app.utils.jsonutil import dumps


def _dest() -> Path:
    p = Path(settings.UPLOAD_DIR) / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _payload(task: EvalTask, extra: dict | None = None) -> dict:
    return {
        "task_id": task.id,
        "name": task.name,
        "status": task.status,
        "scene": task.scene,
        "industry": task.industry,
        "template_code": getattr(task, "template_code", "") or "",
        "dataset_id": task.dataset_id,
        "dataset_version_id": task.dataset_version_id,
        "model_id": task.model_id,
        "model_version_id": getattr(task, "model_version_id", None),
        "prompt_id": task.prompt_id,
        "prompt_version_id": task.prompt_version_id,
        "judge_resource_id": task.judge_resource_id,
        "tool_version": getattr(task, "tool_version", "") or "",
        "snapshot_id": task.snapshot_id,
        "batch_id": task.batch_id,
        "total": task.total,
        "success_count": task.success_count,
        "fail_count": task.fail_count,
        "avg_score": task.avg_score,
        "pass_rate": task.pass_rate,
        "report_summary": task.report_summary,
        "tokens_used": getattr(task, "tokens_used", 0) or 0,
        **(extra or {}),
    }


def write_task_report(task: EvalTask, extra: dict | None = None) -> str:
    dest = _dest()
    payload = _payload(task, extra)
    path = dest / f"task-{task.id}.json"
    path.write_text(dumps(payload), encoding="utf-8")
    (dest / f"task-{task.id}.md").write_text(
        f"# 评测报告 {task.name}\n\n"
        f"- 状态：{task.status}\n"
        f"- 场景：{task.scene} / 行业：{task.industry}\n"
        f"- 样本：{task.total} 通过：{task.success_count} 失败：{task.fail_count}\n"
        f"- 通过率：{task.pass_rate:.2%} 平均分：{task.avg_score:.4f}\n\n"
        f"{task.report_summary}\n",
        encoding="utf-8",
    )
    for writer, ext in (
        (write_html, "html"),
        (write_csv, "csv"),
        (write_xlsx, "xlsx"),
        (write_docx, "docx"),
        (write_pdf_summary, "pdf"),
    ):
        try:
            writer(dest / f"task-{task.id}.{ext}", payload)
        except Exception:
            pass
    return str(path)


def report_file(task_id: int, fmt: str) -> Path:
    ext = {"json": "json", "md": "md", "csv": "csv", "xlsx": "xlsx", "docx": "docx", "html": "html", "pdf": "pdf"}.get(fmt, "json")
    return _dest() / f"task-{task_id}.{ext}"


def write_html(path: Path, payload: dict) -> None:
    rows = payload.get("results") or []
    body = "".join(
        f"<tr><td>{escape(str(r.get('item_no','')))}</td><td>{escape(str(r.get('score','')))}</td>"
        f"<td>{escape(str(r.get('passed','')))}</td></tr>"
        for r in rows[:500]
    )
    path.write_text(
        f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>报告 {escape(str(payload.get('name')))}</title></head>"
        f"<body><h1>{escape(str(payload.get('name')))}</h1>"
        f"<p>状态 {escape(str(payload.get('status')))} 通过率 {payload.get('pass_rate')} 平均分 {payload.get('avg_score')}</p>"
        f"<p>{escape(str(payload.get('report_summary') or ''))}</p>"
        f"<table border='1'><tr><th>#</th><th>score</th><th>passed</th></tr>{body}</table></body></html>",
        encoding="utf-8",
    )


def write_csv(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task_id", "name", "status", "pass_rate", "avg_score", "total"])
        w.writerow([payload.get("task_id"), payload.get("name"), payload.get("status"), payload.get("pass_rate"), payload.get("avg_score"), payload.get("total")])
        w.writerow([])
        w.writerow(["item_no", "score", "passed"])
        for r in payload.get("results") or []:
            w.writerow([r.get("item_no"), r.get("score"), r.get("passed")])


def write_xlsx(path: Path, payload: dict) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "summary"
    ws.append(["字段", "值"])
    for k in ("task_id", "name", "status", "scene", "industry", "pass_rate", "avg_score", "total", "report_summary"):
        ws.append([k, payload.get(k)])
    ws2 = wb.create_sheet("results")
    ws2.append(["item_no", "score", "passed"])
    for r in payload.get("results") or []:
        ws2.append([r.get("item_no"), r.get("score"), r.get("passed")])
    wb.save(path)


def write_docx(path: Path, payload: dict) -> None:
    text = (
        f"评测报告 {payload.get('name')}\n"
        f"状态 {payload.get('status')} 通过率 {payload.get('pass_rate')} 平均分 {payload.get('avg_score')}\n"
        f"{payload.get('report_summary') or ''}"
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>" + escape(text) + "</w:t></w:r></w:p></w:body></w:document>"
    )
    ctypes = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ctypes)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document_xml)
    path.write_bytes(buf.getvalue())


def write_pdf_summary(path: Path, payload: dict) -> None:
    title = _pdf_esc(f"Eval report task {payload.get('task_id')}")
    line = _pdf_esc(
        f"status={payload.get('status')} pass_rate={payload.get('pass_rate')} avg={payload.get('avg_score')} total={payload.get('total')}"
    )
    stream = f"BT /F1 12 Tf 72 720 Td ({title}) Tj 0 -18 Td ({line}) Tj ET\n".encode("latin-1", "replace")
    parts = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(parts, 1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(parts)+1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer << /Size {len(parts)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(out))


def _pdf_esc(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:200]
