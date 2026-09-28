"""远程加密通道：mTLS / HTTPS / VPN 网关 / 明文联调。"""
from __future__ import annotations

from pathlib import Path

from app.config import settings


def httpx_tls_kwargs(channel_type: str = "https") -> dict:
    ch = (channel_type or "https").lower()
    if ch == "plain":
        if (settings.APP_ENV or "").lower() == "production":
            raise RuntimeError("生产环境禁止明文通道(channel_type=plain)")
        return {"verify": False}
    if ch == "mtls":
        cert = (settings.MTLS_CERT_FILE or "").strip()
        key = (settings.MTLS_KEY_FILE or "").strip()
        ca = (settings.MTLS_CA_FILE or "").strip()
        if not cert or not Path(cert).exists() or not key or not Path(key).exists():
            raise RuntimeError("mTLS 通道已启用，但 MTLS_CERT_FILE / MTLS_KEY_FILE 未配置或文件不存在")
        kw: dict = {"cert": (cert, key), "verify": True}
        if ca:
            if not Path(ca).exists():
                raise RuntimeError("MTLS_CA_FILE 不存在")
            kw["verify"] = ca
        return kw
    # https / vpn / gateway：TLS 校验；证书由系统或网关终止
    return {"verify": True}
