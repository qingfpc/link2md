"""Platform registry.

Order matters: specific parsers first, generic web fallback last.
Douyin and Xiaohongshu are recognized so they fail with a clear v2 message
instead of being scraped as ordinary web pages. Cookie paths for those
platforms already exist on ``CookiesConfig``.
"""

from __future__ import annotations

import re

from link2md.errors import UnsupportedPlatformError
from link2md.parsers.base import Parser
from link2md.parsers.bilibili import BilibiliParser
from link2md.parsers.generic import GenericParser
from link2md.parsers.wechat import WechatParser
from link2md.parsers.xiaoyuzhou import XiaoyuzhouParser
from link2md.urls import hostname

# v2: insert DouyinParser / XiaohongshuParser into PARSERS and delete the
# matching entry here. Implementations should read config.cookies.douyin and
# config.cookies.xiaohongshu (Netscape cookie files).
_RESERVED: list[tuple[str, str, re.Pattern[str]]] = [
    ("douyin", "抖音", re.compile(r"(^|\.)(douyin\.com|iesdouyin\.com)$")),
    ("xiaohongshu", "小红书", re.compile(r"(^|\.)(xiaohongshu\.com|xhslink\.com)$")),
]


def builtin_parsers() -> list[Parser]:
    return [BilibiliParser(), XiaoyuzhouParser(), WechatParser(), GenericParser()]


def match_platform(url: str, parsers: list[Parser] | None = None) -> str:
    """Return the platform id, or raise if the host is reserved for v2."""

    reserved = reserved_platform(url)
    if reserved is not None:
        key, label = reserved
        raise UnsupportedPlatformError(
            f"{label}计划在 v2 支持，需要 Cookie 管理。"
            f"可以先在配置里填写 cookies.{key}，当前版本还不会抓取该平台。"
        )
    for parser in parsers or builtin_parsers():
        if parser.match(url):
            return parser.platform
    return "web"


def get_parser(url: str, parsers: list[Parser] | None = None) -> Parser:
    platform = match_platform(url, parsers)
    for parser in parsers or builtin_parsers():
        if parser.platform == platform and parser.match(url):
            return parser
    raise UnsupportedPlatformError(f"没有找到平台 {platform} 的解析器。")


def reserved_platform(url: str) -> tuple[str, str] | None:
    host = hostname(url)
    for key, label, pattern in _RESERVED:
        if pattern.search(host):
            return key, label
    return None
