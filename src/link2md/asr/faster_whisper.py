"""Local transcription with faster-whisper. The package is an optional extra."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from link2md.errors import ConfigError
from link2md.models import Transcript


def import_faster_whisper() -> Any:
    try:
        import faster_whisper
    except ImportError as exc:
        raise ConfigError(
            '本地转写需要可选依赖：pip install "link2md[asr]"'
        ) from exc
    return faster_whisper


class FasterWhisperTranscriber:
    name = "faster-whisper"

    def __init__(
        self,
        *,
        model: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: Path | None = None,
        importer: Callable[[], Any] = import_faster_whisper,
    ) -> None:
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self._importer = importer
        self._model: Any = None

    def ensure_available(self) -> None:
        self._importer()

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> Transcript:
        module = self._importer()
        if self._model is None:
            kwargs: dict[str, Any] = {
                "device": self.device,
                "compute_type": self.compute_type,
            }
            if self.download_root is not None:
                self.download_root.mkdir(parents=True, exist_ok=True)
                kwargs["download_root"] = str(self.download_root)
            self._model = module.WhisperModel(self.model_name, **kwargs)
        segments, info = self._model.transcribe(
            str(audio_path),
            language=language or None,
            vad_filter=True,
        )
        pieces: list[str] = []
        for segment in segments:
            text = (getattr(segment, "text", "") or "").strip()
            if text:
                pieces.append(text)
        detected = getattr(info, "language", None)
        return Transcript(text="\n".join(pieces).strip(), language=detected, segments=pieces)
