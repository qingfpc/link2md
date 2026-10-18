"""Generic article fallback: trafilatura, then a simple main-content heuristic."""

from __future__ import annotations

from bs4 import BeautifulSoup

from link2md.errors import ParseError
from link2md.html_to_md import (
    collapse_blank,
    date_prefix,
    html_to_markdown,
    make_soup,
    meta_content,
    normalize_space,
)
from link2md.log import get_logger
from link2md.models import Item
from link2md.parsers.base import ParseContext


_MIN_CHARS = 20


class GenericParser:
    platform = "web"

    def match(self, url: str) -> bool:
        return True

    def parse(self, url: str, ctx: ParseContext) -> Item:
        html = ctx.http.get_text(url)
        parsed = parse_generic_html(url, html)
        if not parsed["text"].strip():
            raise ParseError("没有从网页里提取到正文。这个链接可能不是文章，或页面需要登录。")
        return Item(
            platform=self.platform,
            title=parsed["title"] or "未命名文章",
            author=parsed["author"] or "未知",
            source_url=url,
            content_type="article",
            text=parsed["text"],
            publish_date=parsed["publish_date"],
            text_source="article",
            image_referer=url,
        )


def parse_generic_html(url: str, html: str) -> dict[str, str | None]:
    soup = make_soup(html)
    title = (
        meta_content(soup, prop="og:title")
        or normalize_space(_title_text(soup))
        or "未命名文章"
    )
    author = meta_content(soup, name="author") or meta_content(soup, prop="article:author") or "未知"
    published = (
        meta_content(soup, prop="article:published_time")
        or meta_content(soup, name="pubdate")
        or meta_content(soup, prop="og:article:published_time")
    )
    text = _trafilatura_markdown(html, url)
    if len(text) < _MIN_CHARS:
        get_logger().info("trafilatura 没有抽出足够正文，改用页面结构兜底。")
        text = fallback_markdown(soup)
    return {
        "title": title,
        "author": author,
        "publish_date": date_prefix(published),
        "text": collapse_blank(text),
    }


def fallback_markdown(soup: BeautifulSoup) -> str:
    for tag in soup.select("script, style, noscript, nav, footer, header, form"):
        tag.decompose()
    best = None
    best_score = 0
    for node in soup.select("article, main, [role=main], #content, .post, .article, .entry"):
        score = _text_score(node)
        if score > best_score:
            best = node
            best_score = score
    if best is None or best_score < _MIN_CHARS:
        for node in soup.find_all(["article", "div", "section"]):
            score = _text_score(node)
            if score > best_score:
                best = node
                best_score = score
    if best is None or best_score < _MIN_CHARS:
        return ""
    return html_to_markdown(str(best))


def _trafilatura_markdown(html: str, url: str) -> str:
    try:
        import trafilatura
    except ImportError:
        get_logger().warning("未安装 trafilatura，直接使用兜底提取。")
        return ""
    extracted = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_images=True,
        include_links=True,
        include_formatting=True,
    )
    return collapse_blank(extracted or "")


def _title_text(soup: BeautifulSoup) -> str:
    if soup.title and soup.title.string:
        return str(soup.title.string)
    return ""


def _text_score(node) -> int:
    paragraphs = node.find_all("p")
    if paragraphs:
        return sum(len(paragraph.get_text(strip=True)) for paragraph in paragraphs)
    return len(node.get_text(" ", strip=True))
