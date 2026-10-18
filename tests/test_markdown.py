"""Markdown rendering, filenames, and image link rewriting. No network."""

from datetime import datetime, timezone

from link2md.filenames import safe_filename
from link2md.images import ImageLocalizer
from link2md.markdown_note import Note, render_note


def _note(**kwargs) -> Note:
    base = dict(
        title='他说 "你好"',
        platform="wechat",
        author="作者",
        source_url="https://mp.weixin.qq.com/s/abc",
        saved_at=datetime(2026, 10, 18, 14, 55, tzinfo=timezone.utc),
        content_type="article",
        text_source="article",
        body="正文第一段。\n\n![图](https://mmbiz.qpic.cn/a?wx_fmt=png)",
        summary="这是摘要",
        key_points=["要点一", "要点二"],
        tags=["公众号", "示例"],
        publish_date="2024-01-02",
        shownotes="",
        llm_status="ok",
    )
    base.update(kwargs)
    return Note(**base)


def test_render_front_matter_and_sections():
    text = render_note(_note())
    assert text.startswith("---\n")
    assert 'title: "他说 \\"你好\\""' in text
    assert 'platform: "wechat"' in text
    assert 'author: "作者"' in text
    assert 'source_url: "https://mp.weixin.qq.com/s/abc"' in text
    assert 'publish_date: "2024-01-02"' in text
    assert 'saved_at: "2026-10-18T14:55:00+00:00"' in text
    assert 'content_type: "article"' in text
    assert 'text_source: "article"' in text
    assert '  - "公众号"' in text
    assert '  - "示例"' in text
    assert "## 摘要" in text
    assert "这是摘要" in text
    assert "## 要点" in text
    assert "- 要点一" in text
    assert "## 正文" in text
    assert "正文第一段。" in text
    assert "## 节目介绍" not in text


def test_render_omits_unknown_publish_date_and_empty_tags():
    text = render_note(
        _note(
            publish_date=None,
            tags=[],
            summary="",
            key_points=[],
            llm_status="skipped",
            shownotes="这期节目聊了什么。",
        )
    )
    assert "publish_date:" not in text
    assert "tags: []" in text
    assert "（未调用模型，以下是原文。）" in text
    assert "（无）" in text
    assert "## 节目介绍" in text
    assert "这期节目聊了什么。" in text


def test_render_failed_llm_placeholder():
    text = render_note(_note(summary="", llm_status="failed", key_points=[]))
    assert "（摘要生成失败，以下是原文。）" in text


def test_safe_filename_strips_invalid_characters_and_is_stable():
    url = "https://www.bilibili.com/video/BV1"
    first = safe_filename('a/b:c*?"<>|', url)
    second = safe_filename("a b c", url)
    assert "/" not in first
    assert ":" not in first
    assert first.endswith(".md")
    assert first == safe_filename('a/b:c*?"<>|', url)
    # Slashes and punctuation collapse to the same readable title.
    assert first == second
    assert first != safe_filename("另一篇", url)
    empty = safe_filename("   ", url)
    assert empty.startswith("未命名-")


class _Bytes:
    def __init__(self, payload: bytes, headers_out: list):
        self.payload = payload
        self.headers_out = headers_out

    def get_bytes(self, url, headers=None):
        self.headers_out.append((url, headers))
        return self.payload


def test_image_links_are_rewritten_next_to_the_note(tmp_path):
    note_dir = tmp_path / "link2md"
    note_dir.mkdir()
    dest = tmp_path / "link2md" / "attachments" / "note"
    seen = []
    payload = b"\x89PNG\r\n\x1a\n" + b"x" * 120
    http = _Bytes(payload, seen)
    localizer = ImageLocalizer(
        dest,
        note_dir,
        http,
        referer="https://mp.weixin.qq.com/",
    )
    markdown = "段落。\n\n![配图](https://mmbiz.qpic.cn/demo/0?wx_fmt=png)\n"
    rewritten = localizer.rewrite(markdown)
    assert "https://mmbiz.qpic.cn" not in rewritten
    assert rewritten.count("![配图](attachments/") == 1
    assert seen[0][1]["Referer"] == "https://mp.weixin.qq.com/"
    files = list(dest.glob("img-001-*.png"))
    assert len(files) == 1
    assert files[0].read_bytes() == payload
    # The same remote URL is downloaded once.
    again = localizer.rewrite(markdown)
    assert again == rewritten
    assert len(seen) == 1
