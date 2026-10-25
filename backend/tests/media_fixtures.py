"""Locally generated binary fixtures; not model capability measurements."""
import base64
from functools import lru_cache
import io
from pathlib import Path
import tempfile
import wave

from app.services.media_processing import ffmpeg


def audio_entry():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)
    return {"modality": "audio", "name": "silence.wav", "data_url": "data:audio/wav;base64," + base64.b64encode(stream.getvalue()).decode(),
            "segments": [{"start": 0, "end": .5, "label": "first half"}]}


@lru_cache(maxsize=4)
def video_entry(with_audio=False, fps=4):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "clip.mp4"
        args = ["-f", "lavfi", "-i", f"color=c=red:s=160x120:d=1:r={fps}", "-f", "lavfi", "-i", f"color=c=blue:s=160x120:d=1:r={fps}"]
        if with_audio:
            args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
        args += ["-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]", "-map", "[v]"]
        if with_audio:
            args += ["-map", "2:a", "-c:a", "aac"]
        args += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)]
        ffmpeg(args)
        return {"modality": "video", "name": "temporal.mp4", "video_mode": "frames", "frame_timestamps": [0, 1.5],
                "data_url": "data:video/mp4;base64," + base64.b64encode(path.read_bytes()).decode(),
                "segments": [{"start": 1, "end": 2, "label": "blue interval"}]}
