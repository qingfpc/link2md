"""WeChat Official Account articles (mp.weixin.qq.com).

A MicroMessenger user agent is required; without it WeChat sometimes returns a
shell page. Body lives in ``#js_content``. Images use lazy ``data-src`` on
``mmbiz.qpic.cn`` (``wx_fmt`` query gives the type). Publish time is a unix
``create_time`` / ``var ct = "..."`` value. ``#publish_time`` is often empty
until client-side JS runs, so it is only a fallback.

Images are downloaded later with ``Referer: https://mp.weixin.qq.com/`` because
the CDN checks the referer when the note is opened outside WeChat.
"""

from __future__ import annotations

import re

from link2md.errors import ParseError
from link2md.html_to_md import html_to_markdown, make_soup, meta_content, normalize_space, unix_to_date
from link2md.models import Item
from link2md.parsers.base import ParseContext
from link2md.urls import hostname

WECHAT_REFERER = "https://mp.weixin.qq.com/"
WECHAT_UA = (
    "Mozilla/5.0 (Linux; Android 12; Mobile) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36 "
    "MicroMessenger/8.0.43 NetType/WIFI Language/zh_CN"
)

_TIME_PATTERNS = (
    r'var ct\s*=\s*"(\d{10})"',
    r'ori_create_time["\']?\s*[:=]\s*["\']?(\d{10})',
    r'create_time["\']?\s*[:=]\s*["\']?(\d{10})',
)


class WechatParser:
    platform = "wechat"

    def match(self, url: str) -> bool:
        return hostname(url) == "mp.weixin.qq.com"

    def parse(self, url: str, ctx: ParseContext) -> Item:
        html = ctx.http.get_text(
            url,
            headers={"User-Agent": WECHAT_UA, "Referer": WECHAT_REFERER},
        )
        parsed = parse_wechat_html(url, html)
        if not parsed["text"].strip():
            raise ParseError(
                "微信页面里没有正文。链接可能失效，或触发了验证页。请换一条从微信里复制的文章链接。"
            )
        return Item(
            platform=self.platform,
            title=parsed["title"],
            author=parsed["author"],
            source_url=url,
            content_type="article",
            text=parsed["text"],
            publish_date=parsed["publish_date"],
            text_source="article",
            image_referer=WECHAT_REFERER,
        )


def parse_wechat_html(url: str, html: str) -> dict[str, str | None]:
    if _looks_blocked(html):
        raise ParseError("微信返回了验证页或环境异常提示。请稍后再试，或换一条文章链接。")
    soup = make_soup(html)
    title = normalize_space(_text(soup, "#activity-name")) or meta_content(soup, prop="og:title") or "未命名文章"
    author = (
        normalize_space(_text(soup, "#js_name"))
        or _nickname(html)
        or meta_content(soup, prop="og:article:author")
        or "未知"
    )
    content = soup.select_one("#js_content")
    markdown = ""
    if content is not None:
        for tag in content.select("script, style, svg, iframe"):
            tag.decompose()
        for image in content.find_all("img"):
            src = (image.get("data-src") or image.get("src") or "").strip()
            if src.startswith("//"):
                src = "https:" + src
            if not src.startswith("http"):
                image.decompose()
                continue
            alt = image.get("alt") or ""
            image.attrs = {"src": src, "alt": alt}
        markdown = html_to_markdown(str(content))
    return {
        "url": url,
        "title": title,
        "author": author,
        "publish_date": _publish_date(html, soup),
        "text": markdown,
    }


def _publish_date(html: str, soup) -> str | None:
    for pattern in _TIME_PATTERNS:
        match = re.search(pattern, html)
        if match:
            return unix_to_date(int(match.group(1)))
    text = normalize_space(_text(soup, "#publish_time"))
    return text or None


def _nickname(html: str) -> str:
    match = re.search(r'var nickname\s*=\s*htmlDecode\("([^"]*)"\)', html)
    if not match:
        return ""
    return normalize_space(match.group(1))


def _text(soup, selector: str) -> str:
    node = soup.select_one(selector)
    if node is None:
        return ""
    return node.get_text(" ", strip=True)


def _looks_blocked(html: str) -> bool:
    sample = html or ""
    if "环境异常" in sample or "访问过于频繁" in sample:
        return True
    return False
