"""Chunking and post-processing with a fake chat client."""

import json

import pytest

from link2md.errors import Link2mdError
from link2md.llm.postprocess import chunk_text, mask_protected, parse_json_object, postprocess, unmask


class FakeChat:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        return self.responder(messages)


def test_chunk_text_packs_paragraphs_and_keeps_placeholders():
    text = "甲" * 30 + "\n\n" + "乙" * 30 + "\n\n" + "丙" * 10
    chunks = chunk_text(text, 70)
    assert len(chunks) == 2
    assert chunks[0].startswith("甲")
    assert "丙" in chunks[1]

    huge = "甲" * 50 + " [[IMG_0]] " + "乙" * 50
    assert chunk_text(huge, 40) == [huge]


def test_mask_roundtrip():
    raw = "前文 ![图](https://example.com/a.png) 后文\n\n```python\nprint(1)\n```"
    masked, slots = mask_protected(raw)
    assert "https://example.com" not in masked
    assert "print(1)" not in masked
    assert unmask(masked, slots) == raw


def test_parse_json_object_accepts_fence():
    payload = parse_json_object('```json\n{"summary":"好"}\n```')
    assert payload["summary"] == "好"


def test_short_text_is_one_call():
    def responder(messages):
        assert "标题：示例" in messages[-1]["content"]
        return json.dumps(
            {
                "summary": "摘要",
                "key_points": ["一", "二"],
                "tags": ["#标签", "标签", "另一个"],
                "cleaned_text": "整理后的正文。",
            },
            ensure_ascii=False,
        )

    chat = FakeChat(responder)
    result = postprocess("原始正文。", chat=chat, chunk_chars=1000, meta="标题：示例")
    assert chat.calls and len(chat.calls) == 1
    assert result.summary == "摘要"
    assert result.key_points == ["一", "二"]
    assert result.tags == ["标签", "另一个"]
    assert result.cleaned_text == "整理后的正文。"


def test_long_text_is_chunked_then_summarized():
    paragraphs = [f"第{i}段" + "内容" * 30 for i in range(4)]
    text = "\n\n".join(paragraphs)

    def responder(messages):
        system = messages[0]["content"]
        if "cleaned_text" in system and "summary" not in system:
            return json.dumps({"cleaned_text": messages[-1]["content"]}, ensure_ascii=False)
        return json.dumps(
            {"summary": "总摘要", "key_points": ["要点"], "tags": ["标签"]},
            ensure_ascii=False,
        )

    chat = FakeChat(responder)
    result = postprocess(text, chat=chat, chunk_chars=80, meta="标题：长文")
    assert len(chat.calls) > 2
    assert "第0段" in result.cleaned_text
    assert "第3段" in result.cleaned_text
    assert result.summary == "总摘要"


def test_dropped_image_token_keeps_original_chunk():
    raw = "文字 " + "很" * 80 + " ![图](https://example.com/a.png)"

    def responder(messages):
        return json.dumps(
            {
                "summary": "摘要",
                "key_points": ["一"],
                "tags": ["标签"],
                "cleaned_text": "模型把图片弄丢了，只留下很短的话。",
            },
            ensure_ascii=False,
        )

    result = postprocess(raw, chat=FakeChat(responder), chunk_chars=5000, meta="")
    assert "https://example.com/a.png" in result.cleaned_text


def test_invalid_json_raises():
    chat = FakeChat(lambda messages: "不是 JSON")
    with pytest.raises(Link2mdError):
        postprocess("正文", chat=chat, chunk_chars=100, meta="")
