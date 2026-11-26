"""Tiny silent/black media files for Chromium's fake capture devices.

Meeting pages ask for camera and microphone access before showing the join
form. Fake devices satisfy the request without touching real hardware, and the
launcher switches both tracks off in the pre-join screen.
"""

from __future__ import annotations

import wave
from pathlib import Path

SAMPLE_RATE = 48_000
VIDEO_WIDTH = 640
VIDEO_HEIGHT = 480
VIDEO_FPS = 30
DEFAULT_DIR = Path(__file__).resolve().parent / ".cache" / "media"

SILENCE_NAME = "silence-48000-mono.wav"
BLACK_VIDEO_NAME = "black-640x480.y4m"


def ensure_silence_wav(path: Path, seconds: float = 1.0) -> Path:
    """Create a mono 16-bit PCM silent WAV once."""
    if path.is_file() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(SAMPLE_RATE * seconds)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(SAMPLE_RATE)
        stream.writeframes(b"\x00\x00" * frame_count)
    return path


def ensure_black_video(
    path: Path,
    width: int = VIDEO_WIDTH,
    height: int = VIDEO_HEIGHT,
    fps: int = VIDEO_FPS,
) -> Path:
    """Create a one-frame black Y4M video (a format fake capture understands)."""
    if path.is_file() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f"YUV4MPEG2 W{width} H{height} F{fps}:1 Ip A1:1 C420jpeg\n".encode()
    luma = bytes([16]) * (width * height)
    chroma = bytes([128]) * (width * height // 4)
    path.write_bytes(header + b"FRAME\n" + luma + chroma + chroma)
    return path


def build_fake_media_args(directory: Path | None = None) -> list[str]:
    """Return Chromium flags that emulate a camera and microphone."""
    base = directory or DEFAULT_DIR
    wav = ensure_silence_wav(base / SILENCE_NAME)
    video = ensure_black_video(base / BLACK_VIDEO_NAME)
    return [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-video-capture={video}",
        f"--use-file-for-fake-audio-capture={wav}",
    ]
