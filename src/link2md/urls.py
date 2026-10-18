"""Pull a URL out of pasted share text and build a stable canonical form."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from link2md.errors import Link2mdError

_URL_RE = re.compile(r"https?://[^\s<>\"'`，。；、】》]+", re.IGNORECASE)
_BARE_RE = re.compile(
    r"(?:mp\.weixin\.qq\.com|www\.bilibili\.com|m\.bilibili\.com|"
    r"b23\.tv|www\.xiaoyuzhoufm\.com|xiaoyuzhoufm\.com)/\S+",
    re.IGNORECASE,
)
_TRAILING = ".,);]】》"

# Query keys that change between shares but point at the same item.
_TRACKING = {
    "spm_id_from",
    "vd_source",
    "share_source",
    "share_medium",
    "share_plat",
    "share_session_id",
    "share_tag",
    "unique_k",
    "timestamp",
    "from",
    "seid",
    "nwr_flag",
    "scene",
    "chksm",
    "ascene",
    "devicetype",
    "version",
    "lang",
    "nettype",
    "fontscale",
    "wx_header",
    "pass_ticket",
    "s",
}

SHORT_HOSTS = {"b23.tv", "www.b23.tv", "b23.wtf", "bili2233.cn"}


def hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def extract_url(text: str) -> str:
    """Return the first URL inside ``text``.

    Share sheets often wrap the URL with a title, Chinese punctuation, HTML
    entities (``&amp;``), or shell backslashes (``\\&``).
    """

    raw = (text or "").strip()
    if not raw:
        raise Link2mdError("没有在输入里找到链接。请粘贴分享文案，或直接传入 URL。")

    cleaned = re.sub(r"\\+([:/&?=#%])", r"\1", raw)
    cleaned = html.unescape(cleaned)
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1].strip()

    match = _URL_RE.search(cleaned)
    if match:
        return match.group(0).rstrip(_TRAILING)

    bare = _BARE_RE.search(cleaned)
    if bare:
        return ("https://" + bare.group(0)).rstrip(_TRAILING)

    raise Link2mdError("没有在输入里找到链接。请粘贴包含 http(s) 地址的分享文案，或直接传入 URL。")


def canonical_url(url: str) -> str:
    """Strip fragments and tracking parameters so the same item maps to one key."""

    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if not host:
        return url.strip()

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in _TRACKING and not key.lower().startswith("utm_")
    ]

    if host.endswith("bilibili.com"):
        query_pairs = [(key, value) for key, value in query_pairs if key == "p"]
    elif host in SHORT_HOSTS or host.endswith("b23.tv"):
        query_pairs = []
    elif host.endswith("xiaoyuzhoufm.com"):
        query_pairs = []
    elif host == "mp.weixin.qq.com":
        path = parts.path or ""
        if path.startswith("/s/"):
            query_pairs = []
        else:
            keep = {"__biz", "mid", "idx", "sn"}
            query_pairs = [(key, value) for key, value in query_pairs if key in keep]

    if host == "bilibili.com" or host.endswith(".bilibili.com"):
        host = "www.bilibili.com"
    elif host.endswith("xiaoyuzhoufm.com"):
        host = "www.xiaoyuzhoufm.com"

    path = parts.path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    scheme = "https" if parts.scheme in {"http", "https"} else (parts.scheme or "https")
    return urlunsplit((scheme, host, path, urlencode(query_pairs), ""))
