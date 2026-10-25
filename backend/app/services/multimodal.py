"""Frozen multimodal inputs for OpenAI-compatible evaluation transports.

Media bytes live in versioned extended_content, never fetched from external URLs.
"""
import base64
import binascii
import hashlib
import io
import json
import re

from PIL import Image

from app.utils.jsonutil import loads


def capabilities(model):
    raw = (getattr(model, "support_modal", "text") or "text").strip()
    if raw.startswith("{"):
        value = json.loads(raw)
        for key in ("input", "output"):
            if not isinstance(value.get(key), list) or any(not isinstance(v, str) or v not in {"text", "image", "audio", "video"} for v in value[key]):
                raise ValueError("模型模态声明input/output须为text/image/audio/video数组")
        inputs, outputs = set(value["input"]), set(value["output"])
    else:
        inputs = set(re.split(r"[, /+]+", raw))
        # Legacy broad labels do not constitute an explicit image capability.
        outputs = {"text"}
    return inputs, outputs


def media_of(item):
    value = loads(item.extended_content or "{}", {})
    if not isinstance(value, dict):
        raise ValueError("样本扩展元数据必须为对象")
    media = value.get("media", [])
    if not isinstance(media, list) or len(media) > 8:
        raise ValueError("media必须为数组，每题最多8个媒体附件")
    frozen = []
    for entry in media:
        if not isinstance(entry, dict) or entry.get("modality") not in {"image", "audio", "video"}:
            raise ValueError("media.modality必须为image/audio/video")
        modality = entry["modality"]
        uri = entry.get("data_url", "")
        if not isinstance(uri, str):
            raise ValueError("data_url必须是字符串")
        match = re.fullmatch(r"data:(image/(?:png|jpeg|webp)|audio/(?:wav|mpeg|mp3)|video/(?:mp4|webm));base64,([A-Za-z0-9+/=]+)", uri)
        if not match or match[1].split('/')[0] != modality or len(uri) > 34 * 1024 * 1024:
            raise ValueError("媒体必须为内嵌PNG/JPEG/WebP/WAV/MP3/MP4/WebM，禁止可变外链")
        try:
            data = base64.b64decode(match[2], validate=True)
        except binascii.Error as exc:
            raise ValueError("无效媒体base64") from exc
        limit = (10 if modality == "image" else 25) * 1024 * 1024
        if not data or len(data) > limit:
            raise ValueError("图片最多10MB，音视频最多25MB")
        subtype = match[1].split('/')[1]
        derived = {}
        if modality == "image":
            try:
                with Image.open(io.BytesIO(data)) as image:
                    if image.format.lower().replace("jpg", "jpeg") != subtype or image.width * image.height > 25_000_000:
                        raise ValueError("图片格式或尺寸不合法")
                    derived = {"width": image.width, "height": image.height}
                    image.verify()
            except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
                raise ValueError("无效图片") from exc
            processing = "original_image"
        else:
            from app.services.media_processing import inspect_clip
            signatures = {"wav": data[:4] == b"RIFF" and data[8:12] == b"WAVE",
                "mp3": data[:3] == b"ID3" or (len(data)>1 and data[0] == 255 and data[1] & 224 == 224),
                "mpeg": data[:3] == b"ID3" or (len(data)>1 and data[0] == 255 and data[1] & 224 == 224),
                "mp4": data[4:8] == b"ftyp", "webm": data[:4] == bytes.fromhex("1a45dfa3")}
            if not signatures.get(subtype):
                raise ValueError("媒体实际格式与声明不匹配")
            mode = entry.get("video_mode", "native") if modality == "video" else ""
            if modality == "video" and mode not in {"native", "frames"}:
                raise ValueError("video_mode只允许native或frames")
            times = entry.get("frame_timestamps", [])
            if not isinstance(times, list) or any(type(t) not in (int,float) for t in times):
                raise ValueError("frame_timestamps必须是秒数数组")
            derived = inspect_clip(data, "mp3" if subtype == "mpeg" else subtype, mode, tuple(times))
            processing = "sampled_frames_with_audio" if mode == "frames" and derived["has_audio"] else "sampled_frames" if mode == "frames" else "original_" + modality
        digest = hashlib.sha256(data).hexdigest()
        if entry.get("sha256") and entry["sha256"] != digest:
            raise ValueError("媒体校验失败")
        regions = entry.get("regions", [])
        if not isinstance(regions, list):
            raise ValueError("regions必须为数组")
        for region in regions:
            box = region.get("box") if isinstance(region, dict) else None
            if not isinstance(box, list) or len(box) != 4 or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in box) or box[0] >= box[2] or box[1] >= box[3]:
                raise ValueError("图片区域box须为归一化[x1,y1,x2,y2]")
        segments = entry.get("segments", [])
        if not isinstance(segments, list):
            raise ValueError("segments必须为时间段数组")
        for segment in segments:
            if not isinstance(segment, dict) or any(type(segment.get(k)) not in (float,int) for k in ("start", "end")) or not 0 <= segment["start"] < segment["end"] <= derived.get("duration_seconds", 0):
                raise ValueError("时间段start/end须为时长范围内的秒数")
        # Derived data is rebuilt from source bytes, never trusted from import metadata.
        clean = {k:v for k,v in entry.items() if k not in {"frames", "audio_track", "has_audio", "has_video", "duration_seconds", "processing"}}
        frozen.append({**clean, **derived, "sha256": digest, "processing": processing, "regions": regions, "segments": segments})

    return frozen


def validate_compatibility(model, item, *, judge=False):
    media = media_of(item)
    inputs, outputs = capabilities(model)
    required = {"text"}
    for entry in media:
        if entry["modality"] == "video" and entry.get("video_mode") == "frames":
            required.add("image")
            if entry["has_audio"]:
                required.add("audio")
        else:
            required.add(entry["modality"])
            if entry["modality"] == "video" and entry["has_audio"]:
                required.add("audio")
    if judge and "audio" in request_options(item).get("response_modalities", []):
        required.add("audio")
    if not required <= inputs:
        raise ValueError("模型未声明" + ",".join(sorted(required, key=lambda value: (value != "text", value))) + "输入能力，禁止执行不匹配媒体样本")
    requested = ["text"] if judge else request_options(item).get("response_modalities", ["text"])
    if not set(requested) <= outputs or "text" not in outputs:
        raise ValueError("模型不支持所需输出模态；评测至少需要text输出")
    return media


def request_options(item):
    metadata = loads(item.extended_content or "{}", {})
    requested = metadata.get("response_modalities", ["text"])
    if requested not in (["text"], ["text", "audio"]):
        raise ValueError("response_modalities只允许[text]或[text,audio]")
    if "audio" not in requested:
        return {}
    config = metadata.get("audio_output", {"voice": "alloy", "format": "wav"})
    if not isinstance(config, dict) or config.get("format") not in {"wav", "mp3"} or not isinstance(config.get("voice"), str) or not config["voice"].strip():
        raise ValueError("audio_output需要voice及wav/mp3格式")
    return {"response_modalities": requested, "audio": config}


def messages_for(prompt, media):
    blocks = [{"type": "text", "text": prompt}]
    for entry in media:
        modality = entry["modality"]
        if modality == "image":
            blocks.append({"type": "image_url", "image_url": {"url": entry["data_url"], "detail": "high"}})
        elif modality == "audio":
            subtype, encoded = entry["data_url"].split(";base64,")
            blocks.append({"type": "input_audio", "input_audio": {"data": encoded, "format": "wav" if subtype.endswith("wav") else "mp3"}})
        elif entry.get("video_mode") == "frames":
            blocks.append({"type": "text", "text": f"视频抽帧证据，时长{entry['duration_seconds']}秒；仅覆盖列出的时间点。"})
            for frame in entry["frames"]:
                blocks.extend([{"type": "text", "text": f"视频帧 t={frame['timestamp_seconds']}s"},
                    {"type": "image_url", "image_url": {"url": frame["data_url"], "detail": "high"}}])
            if entry.get("audio_track"):
                blocks.extend(messages_for("原视频音轨", [entry["audio_track"]])[0]["content"])
        else:
            blocks.append({"type": "video_url", "video_url": {"url": entry["data_url"]}})
    return [{"role": "user", "content": blocks if media else prompt}]


def measurement(media, output_audio=None):
    modalities = sorted({entry["modality"] for entry in media}) or ["text"]
    modality = "video" if "video" in modalities else "audio" if "audio" in modalities else modalities[0]
    outputs = ["text", "audio"] if output_audio else ["text"]
    scopes = []
    for entry in media:
        scopes.append("视频抽帧与完整音轨" if entry["processing"] == "sampled_frames_with_audio" else "视频抽帧（非连续画面）" if entry["processing"] == "sampled_frames" else {"image":"原图", "audio":"原始音频", "video":"原生视频"}[entry["modality"]])
    transports = set()
    for entry in media:
        if entry["modality"] == "video" and entry.get("video_mode") == "frames":
            transports.add("image")
        else:
            transports.add(entry["modality"])
        if entry["modality"] == "video" and entry.get("has_audio"):
            transports.add("audio")
    return {"transport_modalities": sorted(transports or {"text"}), "input_modality": modality, "input_modalities": modalities, "output_modality": "+".join(outputs),
            "media": media, "output_audio": output_audio,
            "measurement_scope": "、".join(scopes or ["文本"]) + "输入→" + ("文本及音频" if output_audio else "文本") + "输出",
            "unmeasured": ["image_generation", "implicit_watermark"] + (["continuous_video"] if any(m["processing"].startswith("sampled_frames") for m in media) else [])}


def media_summary(media):
    return [{k:v for k,v in entry.items() if k not in {"data_url", "frames", "audio_track"}} |
            {"frame_timestamps": [f["timestamp_seconds"] for f in entry.get("frames", [])]} for entry in media]


def without_media_bytes(value):
    """Keep immutable references in textual planning context; actual bytes stay in results."""
    if isinstance(value, dict):
        return {k: without_media_bytes(v) for k,v in value.items() if k not in {"data_url", "data"}}
    if isinstance(value, list):
        return [without_media_bytes(v) for v in value]
    if isinstance(value, str) and value.startswith("data:"):
        return "[原始媒体保留于任务证据；文本摘要不替代媒体判断]"
    return value


async def validate_plan_media(db, plan):
    """Shared preflight for manual and Agent plans; never creates task facts."""
    from sqlalchemy import select
    from app.models import Dataset, DatasetItem, DatasetVersion, EvalModel, ModelVersion
    from app.services.model_access import get_access_for_version, model_call_view
    dataset = await db.get(Dataset, plan.get("dataset_id"))
    model = await db.get(EvalModel, plan.get("model_id"))
    if not dataset or not model:
        raise ValueError("多模态校验需要可用的数据集和模型")
    vid = plan.get("dataset_version_id") or dataset.current_version_id
    version = await db.get(DatasetVersion, vid) if vid else None
    if not version or version.dataset_id != dataset.id:
        raise ValueError("基准版本不属于所选数据集")
    mid = plan.get("model_version_id") or model.current_version_id
    mv = await db.get(ModelVersion, mid) if mid else None
    if mid and (not mv or mv.model_id != model.id):
        raise ValueError("模型版本不属于所选模型")
    view = model_call_view(model, await get_access_for_version(db, model.id, mid))
    items = (await db.scalars(select(DatasetItem).where(DatasetItem.version_id == vid, DatasetItem.status == "active"))).all()
    counts, processing, outputs = {}, set(), set()
    for item in items:
        media = validate_compatibility(view, item)
        modes = {entry["modality"] for entry in media} or {"text"}
        for mode in modes:
            counts[mode] = counts.get(mode, 0) + 1
        processing.update(entry["processing"] for entry in media)
        outputs.update(request_options(item).get("response_modalities", ["text"]))
    return {"input_modalities": counts, "output_modalities": sorted(outputs), "processing": sorted(processing),
            "dataset_content_checksum": version.content_checksum or version.checksum,
            "notice": "抽帧只覆盖列出的时间点；Agent资源编排不等同于规划模型直接理解原始媒体。"}
