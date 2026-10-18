"""Parser contract.

One module per platform. Register the class in ``link2md.parsers.registry``.
Douyin and Xiaohongshu are intentionally absent: add a module, read
``config.cookies.douyin`` / ``config.cookies.xiaohongshu``, and insert the
parser ahead of the generic fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from link2md.config import AppConfig
from link2md.models import Item


class SupportsHttp(Protocol):
    def get_text(self, url: str, headers: dict[str, str] | None = None) -> str: ...

    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes: ...

    def download(self, url: str, dest: Path, headers: dict[str, str] | None = None) -> Path: ...

    def resolve(self, url: str) -> str: ...


class SupportsMedia(Protocol):
    def extract(self, url: str, *, cookiefile: str | None = None): ...

    def download_audio(self, url: str, dest_dir: Path, *, cookiefile: str | None = None) -> Path: ...


@dataclass
class ParseContext:
    config: AppConfig
    http: SupportsHttp
    media: SupportsMedia
    cache_dir: Path


class Parser(Protocol):
    platform: str

    def match(self, url: str) -> bool: ...

    def parse(self, url: str, ctx: ParseContext) -> Item: ...
