"""Alibaba Cloud DashScope Paraformer.

Recorded-file ``paraformer-v2`` requires a public ``file_urls`` entry. A personal
CLI has a local file, so the default model is ``paraformer-realtime-v2``, whose
SDK ``Recognition.call(path)`` accepts that file. Long files are converted to
16 kHz mono WAV and split before recognition.
"""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable

from link2md.audio import split_wav, to_wav_16k
from link2md.errors import ConfigError, MediaError
from link2md.log import get_logger
from link2md.models import Transcript


def import_dashscope() -> Any:
    try:
        import dashscope
    except ImportError as exc:
        raise ConfigError(
            '云端转写需要可选依赖：pip install "link2md[cloud]"'
        ) from exc
    return dashscope


class DashScopeTranscriber:
    name = "dashscope"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "paraformer-realtime-v2",
        base_websocket_api_url: str = "",
        chunk_seconds: int = 600,
        work_dir: Path | None = None,
        importer: Callable[[], Any] = import_dashscope,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_websocket_api_url = base_websocket_api_url.strip()
        self.chunk_seconds = chunk_seconds
        self.work_dir = work_dir
        self._importer = importer

    def ensure_available(self) -> None:
        if not self.api_key:
            raise ConfigError(
                f"使用 dashscope 转写需要设置环境变量（默认 DASHSCOPE_API_KEY）。"
            )
        self._importer()

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> Transcript:
        self.ensure_available()
        work = self.work_dir or audio_path.parent
        wav = work / f"{audio_path.stem}-16k.wav"
        to_wav_16k(audio_path, wav)
        parts = split_wav(wav, work / f"{audio_path.stem}-parts", self.chunk_seconds)
        pieces: list[str] = []
        for index, part in enumerate(parts, start=1):
            get_logger().info("正在转写第 %s/%s 段音频", index, len(parts))
            pieces.extend(self._recognize(part, language=language))
        return Transcript(text="\n".join(pieces).strip(), language=language, segments=pieces)

    def _recognize(self, wav_path: Path, *, language: str | None) -> list[str]:
        dashscope = self._importer()
        try:
            from dashscope.audio.asr import Recognition
        except ImportError as exc:
            raise ConfigError("已安装 dashscope，但缺少语音识别模块 dashscope.audio.asr。") from exc
        dashscope.api_key = self.api_key
        if self.base_websocket_api_url:
            dashscope.base_websocket_api_url = self.base_websocket_api_url
        hints = _language_hints(language)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "format": "wav",
            "sample_rate": 16000,
            "callback": None,
        }
        if hints and "paraformer-realtime-v2" in self.model:
            kwargs["language_hints"] = hints
        recognition = Recognition(**kwargs)
        result = recognition.call(str(wav_path))
        status = getattr(result, "status_code", None)
        if status not in (HTTPStatus.OK, 200):
            message = getattr(result, "message", None) or status
            raise MediaError(f"DashScope 转写失败：{message}")
        return _sentence_texts(result)


def _language_hints(language: str | None) -> list[str]:
    if not language:
        return ["zh", "en"]
    if language.lower().startswith("zh"):
        return ["zh", "en"]
    if language.lower().startswith("en"):
        return ["en"]
    return [language]


def _sentence_texts(result: Any) -> list[str]:
    getter = getattr(result, "get_sentence", None)
    sentences = getter() if callable(getter) else None
    if sentences is None:
        return []
    if isinstance(sentences, dict):
        sentences = [sentences]
    texts: list[str] = []
    for sentence in sentences:
        if isinstance(sentence, dict):
            text = str(sentence.get("text") or "").strip()
        else:
            text = str(sentence).strip()
        if text:
            texts.append(text)
    return texts
