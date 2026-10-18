"""End-to-end pipeline with fake HTTP, media, ASR, and LLM."""

import json
from pathlib import Path

import pytest

from link2md.config import AppConfig
from link2md.errors import UnsupportedPlatformError
from link2md.media import MediaInfo
from link2md.models import Transcript
from link2md.pipeline import save_link

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 120


class FakeHttp:
    def __init__(self, pages=None, blobs=None, redirects=None):
        self.pages = pages or {}
        self.blobs = blobs or {}
        self.redirects = redirects or {}
        self.byte_headers = []
        self.downloads = []

    def get_text(self, url, headers=None):
        if url not in self.pages:
            raise AssertionError(f"unexpected url {url}")
        return self.pages[url]

    def get_bytes(self, url, headers=None):
        self.byte_headers.append(headers)
        return self.blobs[url]

    def download(self, url, dest, headers=None):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake-audio")
        self.downloads.append(url)
        return dest

    def resolve(self, url):
        return self.redirects.get(url, url)

    def close(self):
        return None


class FakeMedia:
    def __init__(self, info: MediaInfo):
        self.info = info
        self.downloads = 0

    def extract(self, url, *, cookiefile=None):
        return self.info

    def download_audio(self, url, dest_dir, *, cookiefile=None):
        self.downloads += 1
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / "audio.m4a"
        path.write_bytes(b"fake-audio")
        return path


class FakeAsr:
    name = "fake"

    def __init__(self):
        self.calls = []

    def ensure_available(self):
        return None

    def transcribe(self, audio_path, *, language=None):
        self.calls.append((audio_path, language))
        return Transcript(text="这是转写出来的正文。", language=language)


class FakeChat:
    def __init__(self, cleaned="整理后的正文。"):
        self.cleaned = cleaned
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return json.dumps(
            {
                "summary": "一条摘要",
                "key_points": ["要点 A"],
                "tags": ["测试"],
                "cleaned_text": self.cleaned,
            },
            ensure_ascii=False,
        )

    def close(self):
        return None


def _config(tmp_path) -> AppConfig:
    config = AppConfig()
    config.vault.path = str(tmp_path / "vault")
    config.cache_dir = str(tmp_path / "cache")
    (tmp_path / "vault").mkdir()
    return config


def test_wechat_pipeline_downloads_images_and_skips_duplicates(tmp_path):
    html = (Path(__file__).parent / "fixtures" / "wechat_article.html").read_text(encoding="utf-8")
    url = "https://mp.weixin.qq.com/s/abc?scene=1"
    http = FakeHttp(
        pages={url: html},
        blobs={"https://mmbiz.qpic.cn/demo/0?wx_fmt=png": PNG},
    )
    chat = FakeChat(cleaned="整理后的正文。\n\n![配图](https://mmbiz.qpic.cn/demo/0?wx_fmt=png)")
    config = _config(tmp_path)
    result = save_link(f"分享文章 {url}", config, http=http, chat=chat)
    assert result.status == "created"
    text = result.path.read_text(encoding="utf-8")
    assert 'platform: "wechat"' in text
    assert 'title: "示例标题"' in text
    assert 'publish_date: "2023-11-14"' in text
    assert "一条摘要" in text
    assert "- 要点 A" in text
    assert "https://mmbiz.qpic.cn" not in text
    assert "attachments/" in text
    assert http.byte_headers[0]["Referer"] == "https://mp.weixin.qq.com/"
    assert chat.calls == 1

    again = save_link(url, config, http=http, chat=chat)
    assert again.status == "skipped"
    assert again.path == result.path
    assert chat.calls == 1

    updated = save_link(url, config, http=http, chat=chat, update=True)
    assert updated.status == "updated"
    assert updated.path == result.path
    notes = list((tmp_path / "vault" / "link2md").glob("*.md"))
    assert len(notes) == 1


def test_bilibili_subtitle_skips_asr(tmp_path):
    info = MediaInfo(
        id="BV1",
        title="视频标题",
        uploader="UP",
        upload_date="2024-02-03",
        webpage_url="https://www.bilibili.com/video/BV1?spm_id_from=1",
        description="视频简介",
        subtitles={"ai-zh": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\n字幕正文\n"}]},
    )
    media = FakeMedia(info)
    asr = FakeAsr()
    chat = FakeChat(cleaned="字幕正文")
    result = save_link(
        "https://b23.tv/abc",
        _config(tmp_path),
        http=FakeHttp(redirects={"https://b23.tv/abc": "https://www.bilibili.com/video/BV1"}),
        media=media,
        transcriber=asr,
        chat=chat,
    )
    text = result.path.read_text(encoding="utf-8")
    assert 'platform: "bilibili"' in text
    assert 'content_type: "video"' in text
    assert 'text_source: "subtitle:ai-zh"' in text
    assert "字幕正文" in text
    assert "## 节目介绍" in text
    assert asr.calls == []
    assert media.downloads == 0
    assert 'source_url: "https://www.bilibili.com/video/BV1"' in text


def test_bilibili_without_subtitle_transcribes(tmp_path):
    info = MediaInfo(
        id="BV2",
        title="无字幕",
        uploader="UP",
        upload_date=None,
        webpage_url="https://www.bilibili.com/video/BV2",
        description="",
    )
    media = FakeMedia(info)
    asr = FakeAsr()
    result = save_link(
        "https://www.bilibili.com/video/BV2",
        _config(tmp_path),
        http=FakeHttp(),
        media=media,
        transcriber=asr,
        chat=FakeChat(cleaned="这是转写出来的正文。"),
    )
    assert media.downloads == 1
    assert len(asr.calls) == 1
    assert asr.calls[0][1] == "zh"
    text = result.path.read_text(encoding="utf-8")
    assert 'text_source: "asr:fake"' in text
    assert "这是转写出来的正文。" in text
    assert "publish_date:" not in text


def test_xiaoyuzhou_downloads_audio_and_keeps_shownotes(tmp_path):
    html = (Path(__file__).parent / "fixtures" / "xiaoyuzhou_episode.html").read_text(encoding="utf-8")
    url = "https://www.xiaoyuzhoufm.com/episode/abc123"
    http = FakeHttp(pages={url: html})
    asr = FakeAsr()
    result = save_link(
        url,
        _config(tmp_path),
        http=http,
        transcriber=asr,
        chat=FakeChat(cleaned="这是转写出来的正文。"),
    )
    assert http.downloads == ["https://media.xyzcdn.net/from-json.m4a"]
    assert len(asr.calls) == 1
    text = result.path.read_text(encoding="utf-8")
    assert 'platform: "xiaoyuzhou"' in text
    assert 'content_type: "audio"' in text
    assert 'author: "主播甲"' in text
    assert "## 节目介绍" in text
    assert "节目介绍正文" in text


def test_missing_llm_key_still_saves(tmp_path):
    html = (Path(__file__).parent / "fixtures" / "wechat_article.html").read_text(encoding="utf-8")
    url = "https://mp.weixin.qq.com/s/abc"
    result = save_link(
        url,
        _config(tmp_path),
        http=FakeHttp(pages={url: html}, blobs={"https://mmbiz.qpic.cn/demo/0?wx_fmt=png": PNG}),
        no_llm=False,
    )
    text = result.path.read_text(encoding="utf-8")
    assert "（未调用模型，以下是原文。）" in text
    assert "第一段正文" in text


def test_llm_failure_keeps_original(tmp_path):
    html = (Path(__file__).parent / "fixtures" / "wechat_article.html").read_text(encoding="utf-8")
    url = "https://mp.weixin.qq.com/s/abc"

    class Boom:
        def complete(self, messages):
            raise RuntimeError("boom")

        def close(self):
            return None

    result = save_link(
        url,
        _config(tmp_path),
        http=FakeHttp(pages={url: html}, blobs={"https://mmbiz.qpic.cn/demo/0?wx_fmt=png": PNG}),
        chat=Boom(),
    )
    text = result.path.read_text(encoding="utf-8")
    assert "（摘要生成失败，以下是原文。）" in text
    assert "第一段正文" in text


def test_douyin_is_rejected():
    with pytest.raises(UnsupportedPlatformError, match="抖音"):
        save_link("https://v.douyin.com/abc/", _config_unwritten(), http=FakeHttp())


def _config_unwritten() -> AppConfig:
    config = AppConfig()
    config.vault.path = "/tmp/link2md-should-not-be-created"
    return config


def test_index_survives_and_scan_finds_note(tmp_path):
    html = (Path(__file__).parent / "fixtures" / "wechat_article.html").read_text(encoding="utf-8")
    url = "https://mp.weixin.qq.com/s/abc"
    config = _config(tmp_path)
    save_link(url, config, http=FakeHttp(pages={url: html}, blobs={"https://mmbiz.qpic.cn/demo/0?wx_fmt=png": PNG}), no_llm=True)
    index = tmp_path / "vault" / "link2md" / ".link2md-index.json"
    assert index.is_file()
    index.unlink()
    again = save_link(url, config, http=FakeHttp(), no_llm=True)
    assert again.status == "skipped"
