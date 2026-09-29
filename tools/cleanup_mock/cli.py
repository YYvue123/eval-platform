from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.cleanup_mock.apply import apply_plan
from tools.cleanup_mock.backup_sqlite import consistent_backup
from tools.cleanup_mock.fingerprint import resolve_sqlite_path
from tools.cleanup_mock.inventory import build_plan
from tools.cleanup_mock.verify import verify_clean


def _print_path(path: Path) -> None:
    print(str(path.resolve()), flush=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tools.cleanup_mock")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser("plan")
    p_plan.add_argument("--db", required=True)
    p_plan.add_argument("--out", required=True)

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--db", required=True)
    p_apply.add_argument("--manifest", required=True)
    p_apply.add_argument("--confirm-fingerprint", required=True)
    p_apply.add_argument("--backup-dir", required=True)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--db", required=True)

    p_backup = sub.add_parser("backup")
    p_backup.add_argument("--db", required=True)
    p_backup.add_argument("--out", required=True)

    args = parser.parse_args(argv)
    path = resolve_sqlite_path(args.db)
    _print_path(path)

    if args.command == "plan":
        plan = build_plan(path)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    if args.command == "apply":
        manifest_path = Path(args.manifest)
        plan = json.loads(manifest_path.read_text(encoding="utf-8"))
        try:
            apply_plan(
                path,
                plan,
                confirm_fingerprint=args.confirm_fingerprint,
                backup_dir=Path(args.backup_dir),
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.command == "verify":
        report = verify_clean(path)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get("ok") else 1

    if args.command == "backup":
        consistent_backup(path, Path(args.out))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
