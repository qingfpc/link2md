"""ffmpeg helpers used before cloud ASR. faster-whisper can read the original file."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from link2md.errors import MediaError
from link2md.log import get_logger


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_available() -> bool:
    return shutil.which("ffprobe") is not None


def to_wav_16k(src: Path, dest: Path) -> Path:
    if not ffmpeg_available():
        raise MediaError("转成 16kHz WAV 需要 ffmpeg，请先安装 ffmpeg。")
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-vn",
        str(dest),
    ]
    _run(command, "音频转码失败")
    return dest


def duration_seconds(path: Path) -> float | None:
    if not ffprobe_available():
        return None
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        get_logger().debug("ffprobe 失败：%s", exc)
        return None
    try:
        return float(completed.stdout.strip())
    except ValueError:
        return None


def split_wav(src: Path, dest_dir: Path, chunk_seconds: int) -> list[Path]:
    """Split a PCM wav into pieces. Returns ``[src]`` when the file is short."""

    if chunk_seconds <= 0:
        return [src]
    length = duration_seconds(src)
    if length is None or length <= chunk_seconds + 1:
        return [src]
    if not ffmpeg_available():
        raise MediaError("切分长音频需要 ffmpeg，请先安装 ffmpeg。")
    dest_dir.mkdir(parents=True, exist_ok=True)
    pattern = dest_dir / "part-%03d.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-f",
        "segment",
        "-segment_time",
        str(chunk_seconds),
        "-c",
        "copy",
        str(pattern),
    ]
    _run(command, "切分音频失败")
    parts = sorted(dest_dir.glob("part-*.wav"))
    if not parts:
        raise MediaError("切分音频后没有得到文件。")
    return parts


def _run(command: list[str], message: str) -> None:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError as exc:
        raise MediaError(f"{message}：{exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"退出码 {completed.returncode}"
        raise MediaError(f"{message}：{tail}")
