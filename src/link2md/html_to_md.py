"""HTML helpers shared by the article parsers."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from markdownify import markdownify as _markdownify


def html_to_markdown(html: str) -> str:
    if not html or not html.strip():
        return ""
    rendered = _markdownify(html, heading_style="ATX", bullets="-")
    return collapse_blank(rendered)


def collapse_blank(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html or "", "lxml")


def meta_content(soup: BeautifulSoup, *, prop: str | None = None, name: str | None = None) -> str:
    tag = None
    if prop:
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", property=prop)
    elif name:
        tag = soup.find("meta", attrs={"name": name})
    if tag is None:
        return ""
    return normalize_space(tag.get("content") or "")


def unix_to_date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat()


def date_prefix(value: str | None) -> str | None:
    """Keep a YYYY-MM-DD prefix when the source gives a datetime string."""

    if not value:
        return None
    text = value.strip()
    match = re.search(r"(\d{4})[-/](\d{2})[-/](\d{2})", text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None
