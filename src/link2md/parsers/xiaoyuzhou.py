"""Xiaoyuzhou (小宇宙) public episode pages.

Checked against a live episode page (2026-10): the audio URL is in
``<meta property="og:audio">`` and in ``__NEXT_DATA__`` ``episode.enclosure.url``.
``episode.transcript`` on that page was only ``{"mediaId": "..."}`` with no
text, so the pipeline transcribes ``enclosure.url`` unless a real transcript
is present. Paid or private episodes often have no enclosure URL.
"""

from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any
from urllib.parse import urlsplit

from link2md.errors import ParseError
from link2md.html_to_md import date_prefix, html_to_markdown, normalize_space
from link2md.models import Item
from link2md.parsers.base import ParseContext
from link2md.urls import hostname

_NEXT_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)
_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:(?P<prop>[^"\']+)["\'][^>]+content=["\'](?P<content>.*?)["\']',
    re.IGNORECASE,
)


class XiaoyuzhouParser:
    platform = "xiaoyuzhou"

    def match(self, url: str) -> bool:
        return hostname(url).endswith("xiaoyuzhoufm.com")

    def parse(self, url: str, ctx: ParseContext) -> Item:
        if "/episode/" not in urlsplit(url).path:
            raise ParseError("小宇宙目前只支持单集链接（路径里包含 /episode/）。")
        html = ctx.http.get_text(url)
        episode = parse_episode_html(url, html)
        if not episode["title"]:
            raise ParseError("小宇宙页面里没有单集标题，页面结构可能变了。")
        transcript = episode["transcript"]
        audio_url = episode["audio_url"]
        if not transcript and not audio_url:
            raise ParseError("这期节目没有公开音频，可能是付费内容或需要登录。")
        author = episode["author"] or episode["podcast"] or "未知"
        return Item(
            platform=self.platform,
            title=episode["title"],
            author=author,
            source_url=episode["url"] or url,
            content_type="audio",
            text=transcript,
            shownotes=episode["shownotes"],
            publish_date=episode["publish_date"],
            text_source="transcript" if transcript else "",
            needs_asr=not bool(transcript),
            direct_media_url=None if transcript else audio_url,
            image_referer=episode["url"] or url,
        )


def parse_episode_html(url: str, html: str) -> dict[str, Any]:
    """Pure parser used by the live page and by unit tests."""

    episode = _find_episode(_next_data(html))
    og = _og_map(html)
    title = normalize_space(str(episode.get("title") or "")) or normalize_space(og.get("title", ""))
    enclosure = episode.get("enclosure") if isinstance(episode.get("enclosure"), dict) else {}
    media = episode.get("media") if isinstance(episode.get("media"), dict) else {}
    source = media.get("source") if isinstance(media.get("source"), dict) else {}
    audio_url = (
        str(enclosure.get("url") or "").strip()
        or str(source.get("url") or "").strip()
        or og.get("audio", "").strip()
    )
    podcast = episode.get("podcast") if isinstance(episode.get("podcast"), dict) else {}
    podcast_title = normalize_space(str(podcast.get("title") or ""))
    hosts = _names(podcast.get("podcasters")) + _names(episode.get("podcasters"))
    # Preserve order while dropping duplicates.
    author_names: list[str] = []
    for name in hosts:
        if name not in author_names:
            author_names.append(name)
    shownotes_html = str(episode.get("shownotes") or episode.get("description") or "")
    shownotes = html_to_markdown(shownotes_html) or normalize_space(og.get("description", ""))
    return {
        "url": url.split("?")[0],
        "title": title,
        "audio_url": audio_url,
        "podcast": podcast_title,
        "author": "、".join(author_names),
        "publish_date": date_prefix(str(episode.get("pubDate") or "")),
        "shownotes": shownotes,
        "transcript": coerce_transcript(episode.get("transcript")),
    }


def coerce_transcript(value: Any) -> str:
    """Return transcript text. A bare ``{"mediaId": "..."}`` is not a transcript."""

    if isinstance(value, str):
        text = value.strip()
        return text if len(text) > 20 else ""
    if isinstance(value, list):
        return _join_segments(value)
    if isinstance(value, dict):
        for key in ("text", "content"):
            nested = value.get(key)
            if isinstance(nested, str) and len(nested.strip()) > 20:
                return nested.strip()
        body = value.get("body")
        if isinstance(body, list):
            return _join_segments(body)
        return ""
    return ""


def _join_segments(segments: list[Any]) -> str:
    lines: list[str] = []
    for segment in segments:
        if isinstance(segment, str):
            text = segment.strip()
        elif isinstance(segment, dict):
            text = str(segment.get("text") or segment.get("content") or "").strip()
        else:
            text = ""
        if text:
            lines.append(text)
    joined = "\n".join(lines).strip()
    return joined if len(joined) > 20 else ""


def _names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for person in value:
        if not isinstance(person, dict):
            continue
        name = normalize_space(str(person.get("nickname") or person.get("name") or ""))
        if name:
            names.append(name)
    return names


def _next_data(html: str) -> dict[str, Any]:
    match = _NEXT_RE.search(html or "")
    if not match:
        return {}
    try:
        loaded = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _find_episode(next_data: dict[str, Any]) -> dict[str, Any]:
    props = next_data.get("props") if isinstance(next_data.get("props"), dict) else {}
    page_props = props.get("pageProps") if isinstance(props.get("pageProps"), dict) else {}
    for key in ("episode", "data", "detail"):
        value = page_props.get(key)
        if isinstance(value, dict) and ("title" in value or "enclosure" in value):
            return value
    return {}


_OG_REV_RE = re.compile(
    r'<meta[^>]+content=["\'](?P<content>.*?)["\'][^>]+property=["\']og:(?P<prop>[^"\']+)["\']',
    re.IGNORECASE,
)


def _og_map(html: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for pattern in (_OG_RE, _OG_REV_RE):
        for match in pattern.finditer(html or ""):
            found.setdefault(match.group("prop"), html_lib.unescape(match.group("content")))
    return found
