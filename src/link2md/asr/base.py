"""Transcription interface. Add a provider by subclassing ``Transcriber``."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from link2md.models import Transcript


class Transcriber(Protocol):
    name: str

    def ensure_available(self) -> None:
        """Raise ConfigError before a long download if this backend cannot run."""

    def transcribe(self, audio_path: Path, *, language: str | None = None) -> Transcript:
        """Transcribe a local audio file."""
