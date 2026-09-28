"""评测报告归档：分格式状态、证据 ID、可恢复生成。"""
from __future__ import annotations

import csv
import io
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import EvalTask, ReportJob
from app.utils.jsonutil import dumps, loads


def _dest() -> Path:
    p = Path(settings.UPLOAD_DIR) / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _evidence_conclusions(task: EvalTask, extra: dict | None = None) -> list[dict]:
    """每条结论绑定 evidence_id，禁止无证据断言。"""
    extra = extra or {}
    conclusions = []
    conclusions.append({
        "evidence_id": f"ev-{task.id}-summary",
        "claim": "任务汇总通过率与平均分",
        "pass_rate": task.pass_rate,
        "avg_score": task.avg_score,
        "result_ref": f"task:{task.id}",
    })
    for r in (extra.get("results") or [])[:200]:
        rid = r.get("id") or r.get("item_no") or uuid.uuid4().hex[:8]
        conclusions.append({
            "evidence_id": f"ev-{task.id}-r{rid}",
            "claim": "样本评分",
            "score": r.get("score"),
            "passed": r.get("passed"),
            "result_ref": f"result:{rid}",
        })
    return conclusions


def _payload(task: EvalTask, extra: dict | None = None) -> dict:
    extra = extra or {}
    evidence = _evidence_conclusions(task, extra)
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
        "conclusions": evidence,
        "evidence_ids": [c["evidence_id"] for c in evidence],
        **extra,
    }


def write_task_report(task: EvalTask, extra: dict | None = None) -> str:
    """同步写报告（兼容旧路径）；失败可见于 formats 元数据文件。"""
    dest = _dest()
    payload = _payload(task, extra)
    formats: dict[str, dict] = {}
    path = dest / f"task-{task.id}.json"
    try:
        path.write_text(dumps(payload), encoding="utf-8")
        formats["json"] = {"status": "ready", "path": str(path), "error": ""}
    except Exception as exc:  # noqa: BLE001
        formats["json"] = {"status": "failed", "path": "", "error": str(exc)}

    md_path = dest / f"task-{task.id}.md"
    try:
        evidence_lines = "\n".join(f"- `{c['evidence_id']}`: {c['claim']}" for c in payload.get("conclusions") or [])
        md_path.write_text(
            f"# 评测报告 {task.name}\n\n"
            f"- 状态：{task.status}\n"
            f"- 场景：{task.scene} / 行业：{task.industry}\n"
            f"- 样本：{task.total} 通过：{task.success_count} 失败：{task.fail_count}\n"
            f"- 通过率：{task.pass_rate:.2%} 平均分：{task.avg_score:.4f}\n\n"
            f"{task.report_summary}\n\n## 证据\n{evidence_lines}\n",
            encoding="utf-8",
        )
        formats["md"] = {"status": "ready", "path": str(md_path), "error": ""}
    except Exception as exc:  # noqa: BLE001
        formats["md"] = {"status": "failed", "path": "", "error": str(exc)}

    writers = (
        (write_html, "html"),
        (write_csv, "csv"),
        (write_xlsx, "xlsx"),
        (write_docx, "docx"),
        (write_pdf_summary, "pdf"),
    )
    for writer, ext in writers:
        fpath = dest / f"task-{task.id}.{ext}"
        try:
            writer(fpath, payload)
            formats[ext] = {"status": "ready", "path": str(fpath), "error": ""}
        except Exception as exc:  # noqa: BLE001
            formats[ext] = {"status": "failed", "path": "", "error": str(exc)}

    meta = dest / f"task-{task.id}.formats.json"
    meta.write_text(dumps({"task_id": task.id, "formats": formats, "evidence_ids": payload.get("evidence_ids")}), encoding="utf-8")
    return str(path)


async def render_report_job(db: AsyncSession, task: EvalTask, extra: dict | None = None) -> ReportJob:
    job = ReportJob(task_id=task.id, status="rendering", formats_json="{}", evidence_json="[]")
    db.add(job)
    await db.flush()
    try:
        path = write_task_report(task, extra)
        meta_path = Path(settings.UPLOAD_DIR) / "reports" / f"task-{task.id}.formats.json"
        meta = loads(meta_path.read_text(encoding="utf-8"), {}) if meta_path.is_file() else {}
        formats = meta.get("formats") or {}
        failed = [k for k, v in formats.items() if v.get("status") == "failed"]
        job.formats_json = dumps(formats)
        job.evidence_json = dumps((extra or {}).get("conclusions") or loads(Path(path).read_text(encoding="utf-8"), {}).get("conclusions") or [])
        if failed and "json" in failed:
            job.status = "failed"
            job.error_message = "；".join(f"{k}:{formats[k].get('error')}" for k in failed)
        elif failed:
            job.status = "ready"  # 主格式成功，部分格式失败可见
            job.error_message = "partial:" + ",".join(failed)
        else:
            job.status = "ready"
            job.error_message = ""
        task.report_path = path
    except Exception as exc:  # noqa: BLE001
        job.status = "failed"
        job.error_message = str(exc)
        job.formats_json = dumps({})
    await db.flush()
    return job


def report_file(task_id: int, fmt: str) -> Path:
    ext = {"json": "json", "md": "md", "csv": "csv", "xlsx": "xlsx", "docx": "docx", "html": "html", "pdf": "pdf"}.get(fmt, "json")
    return _dest() / f"task-{task_id}.{ext}"


def report_formats_status(task_id: int) -> dict:
    meta = _dest() / f"task-{task_id}.formats.json"
    if not meta.is_file():
        # 推断存在文件
        formats = {}
        for ext in ("json", "md", "csv", "xlsx", "docx", "html", "pdf"):
            p = report_file(task_id, ext)
            formats[ext] = {"status": "ready" if p.is_file() else "missing", "path": str(p) if p.is_file() else "", "error": "" if p.is_file() else "not_generated"}
        return {"task_id": task_id, "formats": formats}
    return loads(meta.read_text(encoding="utf-8"), {"task_id": task_id, "formats": {}})


def write_html(path: Path, payload: dict) -> None:
    rows = payload.get("results") or []
    body = "".join(
        f"<tr><td>{escape(str(r.get('item_no','')))}</td><td>{escape(str(r.get('score','')))}</td>"
        f"<td>{escape(str(r.get('passed','')))}</td></tr>"
        for r in rows[:500]
    )
    ev = "".join(f"<li><code>{escape(c.get('evidence_id',''))}</code> {escape(str(c.get('claim','')))}</li>" for c in (payload.get("conclusions") or [])[:50])
    path.write_text(
        f"<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'><title>报告 {escape(str(payload.get('name')))}</title></head>"
        f"<body><h1>{escape(str(payload.get('name')))}</h1>"
        f"<p>状态 {escape(str(payload.get('status')))} 通过率 {payload.get('pass_rate')} 平均分 {payload.get('avg_score')}</p>"
        f"<p>{escape(str(payload.get('report_summary') or ''))}</p>"
        f"<h2>证据</h2><ul>{ev}</ul>"
        f"<table border='1'><tr><th>#</th><th>score</th><th>passed</th></tr>{body}</table></body></html>",
        encoding="utf-8",
    )


def write_csv(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task_id", "name", "status", "pass_rate", "avg_score", "total"])
        w.writerow([payload.get("task_id"), payload.get("name"), payload.get("status"), payload.get("pass_rate"), payload.get("avg_score"), payload.get("total")])
        w.writerow([])
        w.writerow(["evidence_id", "claim", "result_ref"])
        for c in payload.get("conclusions") or []:
            w.writerow([c.get("evidence_id"), c.get("claim"), c.get("result_ref")])
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
    ws2 = wb.create_sheet("evidence")
    ws2.append(["evidence_id", "claim", "result_ref"])
    for c in payload.get("conclusions") or []:
        ws2.append([c.get("evidence_id"), c.get("claim"), c.get("result_ref")])
    ws3 = wb.create_sheet("results")
    ws3.append(["item_no", "score", "passed"])
    for r in payload.get("results") or []:
        ws3.append([r.get("item_no"), r.get("score"), r.get("passed")])
    wb.save(path)


def write_docx(path: Path, payload: dict) -> None:
    evidence = "; ".join(f"{c.get('evidence_id')}:{c.get('claim')}" for c in (payload.get("conclusions") or [])[:20])
    text = (
        f"评测报告 {payload.get('name')}\n"
        f"状态 {payload.get('status')} 通过率 {payload.get('pass_rate')} 平均分 {payload.get('avg_score')}\n"
        f"{payload.get('report_summary') or ''}\n"
        f"证据 {evidence}"
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
    ev0 = (payload.get("evidence_ids") or ["none"])[:1]
    evid = _pdf_esc(f"evidence={ev0[0]}")
    stream = f"BT /F1 12 Tf 72 720 Td ({title}) Tj 0 -18 Td ({line}) Tj 0 -18 Td ({evid}) Tj ET\n".encode("latin-1", "replace")
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
