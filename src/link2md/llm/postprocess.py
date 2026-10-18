"""Clean a transcript and build a summary. Long text is chunked, then reduced."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol

from link2md.errors import Link2mdError
from link2md.log import get_logger

_PROTECTED_RE = re.compile(r"```.*?```|!\[[^\]]*\]\([^)]+\)", re.DOTALL)

_SYSTEM_FULL = """你是中文笔记整理助手。只输出一个 JSON 对象，不要写解释，不要使用 Markdown 代码块。
字段：
- summary：字符串，150 字以内的摘要
- key_points：字符串数组，3 到 7 条
- tags：字符串数组，3 到 6 个短标签，不要带 #
- cleaned_text：字符串，整理后的全文
规则：
- 原文已是通顺文章时，只做分段和明显错字修正
- 原文是口播转写时，补标点、分段，删掉反复的口头禅
- 不要编造原文没有的事实，不要删掉主要信息
- 原样保留 [[IMG_n]] 和 [[CODE_n]] 占位符
"""

_SYSTEM_CLEAN = """你是中文笔记整理助手。只输出 JSON：{"cleaned_text":"..."}。
补标点、分段，删掉反复的口头禅。不要写摘要，不要编造。原样保留 [[IMG_n]] 和 [[CODE_n]] 占位符。"""

_SYSTEM_SUMMARY = """你是中文笔记整理助手。只输出 JSON：{"summary":"","key_points":[],"tags":[]}。
summary 控制在 150 字以内，key_points 为 3 到 7 条，tags 为 3 到 6 个不带 # 的短标签。不要编造。"""


class ChatClient(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


@dataclass
class LlmResult:
    cleaned_text: str
    summary: str = ""
    key_points: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    status: str = "ok"


def postprocess(
    text: str,
    *,
    chat: ChatClient,
    chunk_chars: int,
    meta: str = "",
) -> LlmResult:
    """Return cleaned text plus summary fields.

    A short note is one request. Longer notes are cleaned per chunk, then
    summarized. If the model drops protected image/code tokens or shrinks a
    chunk too far, that chunk stays as the original text.
    """

    original = text or ""
    if not original.strip():
        return LlmResult(cleaned_text=original, status="ok")

    masked, slots = mask_protected(original)
    chunks = chunk_text(masked, chunk_chars)
    if len(chunks) <= 1:
        payload = _complete_json(
            chat,
            [
                {"role": "system", "content": _SYSTEM_FULL},
                {"role": "user", "content": _user_payload(meta, masked)},
            ],
        )
        cleaned = _accept_cleaned(masked, str(payload.get("cleaned_text") or ""), slots)
        return LlmResult(
            cleaned_text=unmask(cleaned, slots),
            summary=str(payload.get("summary") or "").strip(),
            key_points=as_str_list(payload.get("key_points")),
            tags=as_str_list(payload.get("tags")),
            status="ok",
        )

    cleaned_chunks: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        get_logger().info("正在整理第 %s/%s 段正文", index, len(chunks))
        payload = _complete_json(
            chat,
            [
                {"role": "system", "content": _SYSTEM_CLEAN},
                {"role": "user", "content": chunk},
            ],
        )
        cleaned_chunks.append(_accept_cleaned(chunk, str(payload.get("cleaned_text") or ""), slots))
    cleaned_masked = "\n\n".join(cleaned_chunks)
    summary_payload = _summarize(chat, cleaned_masked, meta=meta, chunk_chars=chunk_chars)
    return LlmResult(
        cleaned_text=unmask(cleaned_masked, slots),
        summary=str(summary_payload.get("summary") or "").strip(),
        key_points=as_str_list(summary_payload.get("key_points")),
        tags=as_str_list(summary_payload.get("tags")),
        status="ok",
    )


def chunk_text(text: str, size: int) -> list[str]:
    """Split on blank lines. Oversized pieces that hold a placeholder stay intact."""

    if size <= 0:
        raise ValueError("chunk size must be positive")
    stripped = text.strip()
    if not stripped:
        return []
    if len(stripped) <= size:
        return [stripped]

    parts: list[str] = []
    buffer: list[str] = []
    buffer_len = 0
    for paragraph in re.split(r"\n{2,}", stripped):
        if not paragraph:
            continue
        if len(paragraph) > size:
            if buffer:
                parts.append("\n\n".join(buffer))
                buffer = []
                buffer_len = 0
            if "[[" in paragraph:
                parts.append(paragraph)
            else:
                for start in range(0, len(paragraph), size):
                    parts.append(paragraph[start : start + size])
            continue
        extra = len(paragraph) + (2 if buffer else 0)
        if buffer and buffer_len + extra > size:
            parts.append("\n\n".join(buffer))
            buffer = [paragraph]
            buffer_len = len(paragraph)
        else:
            buffer.append(paragraph)
            buffer_len += extra
    if buffer:
        parts.append("\n\n".join(buffer))
    return parts


def mask_protected(text: str) -> tuple[str, dict[str, str]]:
    slots: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        kind = "CODE" if match.group(0).startswith("```") else "IMG"
        token = f"[[{kind}_{len(slots)}]]"
        slots[token] = match.group(0)
        return token

    return _PROTECTED_RE.sub(replace, text), slots


def unmask(text: str, slots: dict[str, str]) -> str:
    for token, raw in slots.items():
        text = text.replace(token, raw)
    return text


def parse_json_object(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise Link2mdError("模型没有返回 JSON。")
        try:
            loaded = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise Link2mdError("模型返回的 JSON 无法解析。") from exc
    if not isinstance(loaded, dict):
        raise Link2mdError("模型返回的 JSON 不是对象。")
    return loaded


def as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        pieces = re.split(r"[,，、\n]", value)
    elif isinstance(value, list):
        pieces = [str(item) for item in value]
    else:
        return []
    result: list[str] = []
    for piece in pieces:
        item = piece.strip().lstrip("#").strip()
        if item and item not in result:
            result.append(item)
    return result[:8]


def _summarize(chat: ChatClient, text: str, *, meta: str, chunk_chars: int) -> dict:
    pieces = chunk_text(text, chunk_chars)
    if len(pieces) <= 1:
        return _complete_json(
            chat,
            [
                {"role": "system", "content": _SYSTEM_SUMMARY},
                {"role": "user", "content": _user_payload(meta, text)},
            ],
        )
    partials = []
    for index, piece in enumerate(pieces, start=1):
        get_logger().info("正在摘要第 %s/%s 段", index, len(pieces))
        partials.append(
            _complete_json(
                chat,
                [
                    {"role": "system", "content": _SYSTEM_SUMMARY},
                    {"role": "user", "content": piece},
                ],
            )
        )
    merged_input = {
        "meta": meta,
        "partials": [
            {
                "summary": item.get("summary", ""),
                "key_points": item.get("key_points", []),
                "tags": item.get("tags", []),
            }
            for item in partials
        ],
    }
    return _complete_json(
        chat,
        [
            {"role": "system", "content": _SYSTEM_SUMMARY},
            {
                "role": "user",
                "content": "把下面几段摘要合并成一份总摘要，不要编造新事实。\n"
                + json.dumps(merged_input, ensure_ascii=False),
            },
        ],
    )


def _complete_json(chat: ChatClient, messages: list[dict[str, str]]) -> dict:
    return parse_json_object(chat.complete(messages))


def _user_payload(meta: str, text: str) -> str:
    header = meta.strip()
    if header:
        return f"{header}\n\n正文：\n{text}"
    return text


def _accept_cleaned(original: str, cleaned: str, slots: dict[str, str]) -> str:
    candidate = cleaned.strip()
    if not candidate:
        return original
    for token in slots:
        if token in original and token not in candidate:
            get_logger().warning("模型改动了图片或代码占位符，这一段保留原文。")
            return original
    if len(original) > 200 and len(candidate) < len(original) * 0.4:
        get_logger().warning("模型返回的正文明显短于原文，这一段保留原文。")
        return original
    return candidate
