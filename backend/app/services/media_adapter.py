"""媒体输入适配：真实 URI/文件，禁止字符串描述冒充。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.benchmark_packs import fixtures_root

_MAGIC = {
    "image": [b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"],
    "audio": [b"RIFF"],
    "video": [b"ftyp"],  # 出现在 offset 4
}


def resolve_media_uri(uri: str) -> Path:
    if not uri or not isinstance(uri, str):
        raise ValueError("media_uri_required")
    if uri.startswith("fixture://media/"):
        name = uri.removeprefix("fixture://media/")
        path = fixtures_root() / "media" / "assets" / name
        if not path.is_file():
            raise FileNotFoundError(f"media_fixture_missing:{name}")
        return path
    if uri.startswith("file://"):
        path = Path(uri.removeprefix("file://"))
        if not path.is_file():
            raise FileNotFoundError(f"media_file_missing:{path}")
        return path
    # 相对 fixtures 路径
    path = Path(uri)
    if path.is_file():
        return path
    raise ValueError(f"unsupported_media_uri:{uri}")


def _matches_magic(data: bytes, media_type: str) -> bool:
    needles = _MAGIC.get(media_type) or []
    if media_type == "video":
        return any(n in data[:32] for n in needles)
    return any(data.startswith(n) for n in needles)


def validate_media_sample(sample: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if sample.get("media_as_string"):
        errors.append("media_must_not_be_string_description")
    if isinstance(sample.get("media"), str) and not sample.get("media_uri"):
        errors.append("media_must_not_be_string_description")
    uri = sample.get("media_uri")
    media_type = sample.get("media_type")
    if not uri:
        errors.append("media_uri_required")
        return errors
    if media_type not in {"image", "audio", "video"}:
        errors.append("invalid_media_type")
        return errors
    try:
        path = resolve_media_uri(str(uri))
    except (ValueError, FileNotFoundError) as exc:
        errors.append(str(exc))
        return errors
    data = path.read_bytes()
    if len(data) < 8:
        errors.append("media_too_small")
    elif not _matches_magic(data, media_type):
        errors.append(f"media_magic_mismatch:{media_type}")
    return errors


def describe_media(uri: str, media_type: str) -> dict[str, Any]:
    path = resolve_media_uri(uri)
    data = path.read_bytes()
    return {
        "uri": uri,
        "media_type": media_type,
        "path": str(path),
        "size": len(data),
        "decodable_stub": _matches_magic(data, media_type),
    }
