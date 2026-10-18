"""Pick a subtitle track and turn SRT/VTT/JSON captions into plain text.

Bilibili (via yt-dlp) currently places AI captions such as ``ai-zh`` in the
regular ``subtitles`` map, not in ``automatic_captions``. Human-written Chinese
tracks are preferred, then AI Chinese, then English.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Danmaku is a comment overlay, not a transcript.
_SKIP_LANGS = {"danmaku"}
_EXT_ORDER = {"srt": 0, "vtt": 1, "json": 2, "srv3": 3, "srv1": 4, "srv2": 5}

PREFERRED_LANGS = [
    "zh-Hans",
    "zh-CN",
    "zh-cn",
    "zh",
    "chi",
    "zho",
    "zh-Hant",
    "zh-TW",
    "zh-HK",
    "ai-zh",
    "en",
    "en-US",
    "en-GB",
    "ai-en",
]

_TIMESTAMP_RE = re.compile(
    r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[.,]\d{3}"
)
_TAG_RE = re.compile(r"</?[^>]+>")


def select_subtitle_track(
    subtitles: dict[str, list[dict[str, Any]]] | None,
    automatic_captions: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Return ``(language, track)`` or None.

    Manual/subtitle tracks are searched before automatic captions. Within a
    pool, ``PREFERRED_LANGS`` wins. A leftover non-danmaku track is the last
    resort so a video that only has, for example, ``ai-zh`` still matches.
    """

    pools = [subtitles or {}, automatic_captions or {}]
    for pool in pools:
        for lang in PREFERRED_LANGS:
            track = _track_for_lang(pool, lang)
            if track is not None:
                return lang, track
    for pool in pools:
        for lang, tracks in pool.items():
            if lang.lower() in _SKIP_LANGS:
                continue
            track = _best_track(tracks)
            if track is not None:
                return lang, track
    return None


def subtitle_to_text(payload: str, ext: str | None = None) -> str:
    """Convert one subtitle document into plain paragraphs."""

    text = (payload or "").strip()
    if not text:
        return ""
    kind = (ext or "").lower().lstrip(".")
    if kind == "json" or text[0] in "{[":
        parsed = _json_to_text(text)
        if parsed:
            return parsed
    if kind == "vtt" or text.startswith("WEBVTT"):
        return _caption_to_text(text)
    return _caption_to_text(text)


def _track_for_lang(pool: dict[str, list[dict[str, Any]]], lang: str) -> dict[str, Any] | None:
    for key, tracks in pool.items():
        if key.lower() == lang.lower():
            return _best_track(tracks)
    return None


def _best_track(tracks: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    usable = []
    for track in tracks or []:
        ext = str(track.get("ext") or "").lower()
        if ext == "xml":
            continue
        if not (track.get("data") or track.get("url")):
            continue
        usable.append(track)
    if not usable:
        return None
    usable.sort(key=lambda track: _EXT_ORDER.get(str(track.get("ext") or "").lower(), 9))
    return usable[0]


def _json_to_text(payload: str) -> str:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    lines: list[str] = []
    body = data.get("body") if isinstance(data, dict) else data
    if isinstance(body, list):
        for line in body:
            if isinstance(line, str):
                content = line.strip()
            elif isinstance(line, dict):
                content = str(line.get("content") or line.get("text") or "").strip()
            else:
                content = ""
            if content:
                lines.append(content)
    elif isinstance(data, dict):
        content = str(data.get("content") or data.get("text") or "").strip()
        if content:
            lines.append(content)
    return "\n".join(lines).strip()


def _caption_to_text(payload: str) -> str:
    lines: list[str] = []
    for raw in payload.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        if line.isdigit():
            continue
        if _TIMESTAMP_RE.match(line) or "-->" in line:
            continue
        line = _TAG_RE.sub("", line).strip()
        if line:
            lines.append(line)
    # Collapse consecutive duplicates that some SRT writers emit.
    deduped: list[str] = []
    for line in lines:
        if not deduped or deduped[-1] != line:
            deduped.append(line)
    return "\n".join(deduped).strip()
