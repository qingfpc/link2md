"""ASR backends. Register a new one in ``create_transcriber``."""

from __future__ import annotations

from pathlib import Path

from link2md.asr.dashscope import DashScopeTranscriber
from link2md.asr.faster_whisper import FasterWhisperTranscriber
from link2md.config import AppConfig
from link2md.errors import ConfigError


def create_transcriber(config: AppConfig, *, work_dir: Path | None = None):
    """Build the configured transcriber.

    v1 ships two backends:

    * ``faster-whisper`` — local model
    * ``dashscope`` — Alibaba Cloud Paraformer (Chinese-friendly)

    To add a provider, implement ``ensure_available`` / ``transcribe`` and
    branch on ``config.asr.backend`` here.
    """

    backend = config.asr.backend
    if backend == "faster-whisper":
        root = config.cache_path() / "whisper"
        options = config.asr.faster_whisper
        return FasterWhisperTranscriber(
            model=options.model,
            device=options.device,
            compute_type=options.compute_type,
            download_root=root,
        )
    if backend == "dashscope":
        options = config.asr.dashscope
        return DashScopeTranscriber(
            api_key=config.dashscope_api_key(),
            model=options.model,
            base_websocket_api_url=options.base_websocket_api_url,
            chunk_seconds=options.chunk_seconds,
            work_dir=work_dir or config.cache_path() / "asr",
        )
    names = "faster-whisper、dashscope"
    raise ConfigError(f"未知的 ASR 后端：{backend}。可选：{names}")
