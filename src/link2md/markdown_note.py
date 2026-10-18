"""Render a note with YAML front matter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Note:
    title: str
    platform: str
    author: str
    source_url: str
    saved_at: datetime
    content_type: str
    text_source: str
    body: str
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    publish_date: str | None = None
    shownotes: str = ""
    llm_status: str = "ok"


def render_note(note: Note) -> str:
    lines = ["---"]
    lines.append(f"title: {_yaml_str(note.title)}")
    lines.append(f"platform: {_yaml_str(note.platform)}")
    lines.append(f"author: {_yaml_str(note.author)}")
    lines.append(f"source_url: {_yaml_str(note.source_url)}")
    if note.publish_date:
        lines.append(f"publish_date: {_yaml_str(note.publish_date)}")
    lines.append(f"saved_at: {_yaml_str(_iso(note.saved_at))}")
    if note.tags:
        lines.append("tags:")
        for tag in note.tags:
            lines.append(f"  - {_yaml_str(tag)}")
    else:
        lines.append("tags: []")
    lines.append(f"content_type: {_yaml_str(note.content_type)}")
    if note.text_source:
        lines.append(f"text_source: {_yaml_str(note.text_source)}")
    lines.append("---")
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append(_summary_text(note))
    lines.append("")
    lines.append("## 要点")
    lines.append("")
    if note.key_points:
        for point in note.key_points:
            lines.append(f"- {' '.join(point.split())}")
    else:
        lines.append("（无）")
    if note.shownotes.strip():
        lines.append("")
        lines.append("## 节目介绍")
        lines.append("")
        lines.append(note.shownotes.strip())
    lines.append("")
    lines.append("## 正文")
    lines.append("")
    lines.append(note.body.strip() or "（没有正文）")
    lines.append("")
    return "\n".join(lines)


def _summary_text(note: Note) -> str:
    if note.summary.strip():
        return note.summary.strip()
    if note.llm_status == "skipped":
        return "（未调用模型，以下是原文。）"
    if note.llm_status == "failed":
        return "（摘要生成失败，以下是原文。）"
    return "（模型没有返回摘要。）"


def _yaml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.isoformat(timespec="seconds")
