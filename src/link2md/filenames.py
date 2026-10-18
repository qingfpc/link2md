"""Obsidian-safe note filenames."""

from __future__ import annotations

import hashlib
import re

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {
    f"LPT{i}" for i in range(1, 10)
}


def safe_filename(title: str, canonical_url: str) -> str:
    """``{title}-{urlhash}.md``. The hash keeps two different items apart."""

    name = _INVALID.sub(" ", title or "")
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = name[:60].strip(" .")
    if not name or name.upper() in _RESERVED:
        name = "未命名"
    digest = hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()[:8]
    return f"{name}-{digest}.md"
