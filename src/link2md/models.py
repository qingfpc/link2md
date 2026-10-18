"""Shared data objects passed between parsers, the pipeline, and the vault."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Item:
    """Normalized content extracted from one URL.

    ``text`` is the article body or the transcript. ``shownotes`` is optional
    extra context (podcast show notes, video description) that is kept out of
    the ASR/LLM cleanup of the main text.
    """

    platform: str
    title: str
    author: str
    source_url: str
    content_type: str
    text: str = ""
    shownotes: str = ""
    publish_date: str | None = None
    text_source: str = ""
    needs_asr: bool = False
    media_page_url: str | None = None
    direct_media_url: str | None = None
    image_referer: str | None = None
    # Key under ``cookies`` in config, forwarded to yt-dlp when downloading.
    cookie_key: str | None = None


@dataclass
class SaveResult:
    path: Path
    status: str
    title: str = ""
    canonical_url: str = ""


@dataclass
class Transcript:
    text: str
    language: str | None = None
    segments: list[str] = field(default_factory=list)
