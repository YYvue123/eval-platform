from __future__ import annotations

import json
import sys

from tools.stats_service.mcp_protocol import dispatch


def _write(message: dict) -> None:
    print(
        json.dumps(message, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )


def main() -> None:
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            )
            continue

        response, _ = dispatch(message)
        if response is not None:
            _write(response)


if __name__ == "__main__":
    main()
