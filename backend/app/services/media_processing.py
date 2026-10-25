"""Bounded local media inspection and deterministic video sampling. No network IO."""
import base64
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import re
import subprocess
import tempfile

MAX_SECONDS = 120


def ffmpeg(command, *, timeout=20):
    import imageio_ffmpeg
    try:
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-nostdin", "-hide_banner",
            "-protocol_whitelist", "file,pipe", *command], capture_output=True, timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as exc:
        raise ValueError("媒体处理超时") from exc
    if result.returncode:
        raise ValueError("媒体解码失败，请使用有效的WAV/MP3/MP4/WebM")
    return result


@lru_cache(maxsize=4)
def inspect_clip(data: bytes, extension: str, video_mode: str, requested_times: tuple):
    with tempfile.TemporaryDirectory(prefix="eval-media-") as folder:
        source = Path(folder) / ("sample." + extension)
        source.write_bytes(data)
        probe = ffmpeg(["-i", str(source), "-t", "0", "-f", "null", "-"])
        info = probe.stderr.decode("utf-8", errors="replace")
        match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", info)
        if not match:
            raise ValueError("媒体必须具有可确定时长")
        duration = int(match[1])*3600 + int(match[2])*60 + float(match[3])
        if not 0 < duration <= MAX_SECONDS:
            raise ValueError("音视频时长必须在0至120秒之间")
        has_audio = bool(re.search(r"Stream .*Audio:", info))
        has_video = bool(re.search(r"Stream .*Video:", info))
        if extension in {"wav", "mp3"} and (not has_audio or has_video):
            raise ValueError("音频文件格式或音轨不合法")
        if extension in {"mp4", "webm"} and not has_video:
            raise ValueError("视频缺少画面轨道")
        result = {"duration_seconds": duration, "has_audio": has_audio, "has_video": has_video}
        if video_mode == "frames":
            times = requested_times or tuple(round(i*max(duration-.05, 0)/3, 3) for i in range(4))
            if len(times) > 8 or any(not math.isfinite(t) or not 0 <= t < duration for t in times):
                raise ValueError("抽帧时间必须在视频时长内，最多8帧")
            # Use decoded PTS rather than assuming FPS. Low-FPS and variable-FPS
            # clips can have no frame exactly at the requested timestamp.
            decoded = ffmpeg(["-i", str(source), "-an", "-vf", "showinfo", "-f", "null", "-"])
            pts = sorted({float(t) for t in re.findall(r"pts_time:([\d.eE+-]+)", decoded.stderr.decode("utf-8", errors="replace"))})
            if not pts:
                raise ValueError("无法获得视频真实帧时间戳")
            frames = []
            for timestamp in times:
                actual = max((t for t in pts if t <= timestamp), default=pts[0])
                raw = ffmpeg(["-ss", str(actual), "-i", str(source), "-frames:v", "1",
                    "-vf", "scale=1024:1024:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-vcodec", "mjpeg", "-q:v", "3", "-"]).stdout
                if not raw:
                    raise ValueError("指定时间没有可解码的视频帧")
                frames.append({"requested_timestamp_seconds": timestamp, "timestamp_seconds": actual, "sha256": hashlib.sha256(raw).hexdigest(),
                    "data_url": "data:image/jpeg;base64," + base64.b64encode(raw).decode()})
            result["frames"] = frames
            if has_audio:
                raw = ffmpeg(["-i", str(source), "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", "-"]).stdout
                result["audio_track"] = {"modality": "audio", "sha256": hashlib.sha256(raw).hexdigest(),
                    "data_url": "data:audio/wav;base64," + base64.b64encode(raw).decode(), "processing": "extracted_audio_track"}
        return result
