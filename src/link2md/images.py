"""Download remote images and rewrite Markdown links to vault-relative paths."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from link2md.log import get_logger

_IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_EXT_BY_FMT = {
    "jpeg": ".jpg",
    "jpg": ".jpg",
    "png": ".png",
    "gif": ".gif",
    "webp": ".webp",
    "bmp": ".bmp",
    "svg": ".svg",
}
_MAGIC = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG", ".png"),
    (b"GIF8", ".gif"),
    (b"RIFF", ".webp"),
)


class ByteFetcher(Protocol):
    def get_bytes(self, url: str, headers: dict[str, str] | None = None) -> bytes: ...


class ImageLocalizer:
    """Rewrite ``![alt](https://...)`` to a path relative to the note file."""

    def __init__(
        self,
        dest_dir: Path,
        note_dir: Path,
        http: ByteFetcher,
        *,
        referer: str | None = None,
        min_bytes: int = 80,
    ) -> None:
        self.dest_dir = dest_dir
        self.note_dir = note_dir
        self.http = http
        self.referer = referer
        self.min_bytes = min_bytes
        self._saved: dict[str, str] = {}
        self._index = 0

    def rewrite(self, markdown: str) -> str:
        if not markdown:
            return markdown

        def replace(match: re.Match[str]) -> str:
            alt = match.group(1)
            url = match.group(2).strip()
            local = self._localize(url)
            if local is None:
                return match.group(0)
            return f"![{alt}]({local})"

        return _IMG_RE.sub(replace, markdown)

    def _localize(self, url: str) -> str | None:
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith(("http://", "https://")):
            return None
        cached = self._saved.get(url)
        if cached:
            return cached
        headers = {"Referer": self.referer} if self.referer else None
        try:
            payload = self.http.get_bytes(url, headers=headers)
        except Exception as exc:  # download failures should not drop the note
            get_logger().warning("图片下载失败，保留原链接：%s（%s）", url, exc)
            return None
        if len(payload) < self.min_bytes:
            get_logger().info("跳过过小的图片（%s 字节）：%s", len(payload), url)
            return None
        self._index += 1
        ext = _guess_ext(url, payload)
        filename = f"img-{self._index:03d}-{_short_hash(url)}{ext}"
        self.dest_dir.mkdir(parents=True, exist_ok=True)
        path = self.dest_dir / filename
        path.write_bytes(payload)
        relative = Path(os_relpath(path, self.note_dir)).as_posix()
        self._saved[url] = relative
        return relative


def os_relpath(path: Path, start: Path) -> str:
    import os

    return os.path.relpath(path, start)


def _short_hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]


def _guess_ext(url: str, payload: bytes) -> str:
    query = urlsplit(url).query
    for key in ("wx_fmt", "fmt"):
        match = re.search(rf"(?:^|&){key}=([A-Za-z0-9]+)", query)
        if match:
            ext = _EXT_BY_FMT.get(match.group(1).lower())
            if ext:
                return ext
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    for magic, ext in _MAGIC:
        if payload.startswith(magic):
            return ext
    return ".jpg"
