#!/usr/bin/env python3
"""生成简易 SBOM（组件清单），供 CI 归档。非完整 CycloneDX，但含哈希与版本线索。"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    req = root / "backend" / "requirements.txt"
    components = []
    if req.exists():
        for line in req.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            components.append({"type": "library", "purl_hint": s})
    app_dir = root / "backend" / "app"
    py_files = sorted(app_dir.rglob("*.py")) if app_dir.exists() else []
    tree_hash = hashlib.sha256()
    for p in py_files:
        tree_hash.update(p.relative_to(root).as_posix().encode())
        tree_hash.update(file_sha256(p).encode())
    doc = {
        "bomFormat": "eval-platform-sbom-lite",
        "specVersion": "0.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {
            "component": {
                "name": "eval-platform",
                "version": "0.1.0",
                "source_tree_sha256": tree_hash.hexdigest(),
            }
        },
        "components": components,
        "requirements_sha256": file_sha256(req) if req.exists() else None,
    }
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "sbom.json"
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
