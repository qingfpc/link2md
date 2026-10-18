"""Offline parser tests. HTTP and yt-dlp are faked or fed fixtures."""

from pathlib import Path

from link2md.config import AppConfig
from link2md.media import MediaInfo, explain_ytdlp_error
from link2md.parsers.base import ParseContext
from link2md.parsers.bilibili import BilibiliParser
from link2md.html_to_md import make_soup
from link2md.parsers.generic import fallback_markdown, parse_generic_html
from link2md.parsers.wechat import parse_wechat_html
from link2md.parsers.xiaoyuzhou import parse_episode_html
from link2md.subtitles import select_subtitle_track, subtitle_to_text

FIXTURES = Path(__file__).parent / "fixtures"


def test_wechat_fixture_extracts_title_author_date_and_images():
    html = (FIXTURES / "wechat_article.html").read_text(encoding="utf-8")
    parsed = parse_wechat_html("https://mp.weixin.qq.com/s/abc", html)
    assert parsed["title"] == "示例标题"
    assert parsed["author"] == "示例公众号"
    assert parsed["publish_date"] == "2023-11-14"
    assert "第一段正文" in parsed["text"]
    assert "第二段" in parsed["text"]
    assert "https://mmbiz.qpic.cn/demo/0?wx_fmt=png" in parsed["text"]


def test_xiaoyuzhou_fixture_prefers_enclosure_and_ignores_media_id_transcript():
    html = (FIXTURES / "xiaoyuzhou_episode.html").read_text(encoding="utf-8")
    parsed = parse_episode_html("https://www.xiaoyuzhoufm.com/episode/abc123?s=1", html)
    assert parsed["title"] == "单集标题"
    assert parsed["audio_url"] == "https://media.xyzcdn.net/from-json.m4a"
    assert parsed["author"] == "主播甲"
    assert parsed["podcast"] == "科学星球"
    assert parsed["publish_date"] == "2024-10-21"
    assert "节目介绍正文" in parsed["shownotes"]
    assert parsed["transcript"] == ""


def test_xiaoyuzhou_og_audio_fallback_and_real_transcript():
    html = """
    <html><head>
      <meta content="https://media.xyzcdn.net/og-only.m4a" property="og:audio" />
      <meta content="只有 OG" property="og:title" />
    </head><body></body></html>
    """
    parsed = parse_episode_html("https://www.xiaoyuzhoufm.com/episode/x", html)
    assert parsed["audio_url"] == "https://media.xyzcdn.net/og-only.m4a"
    assert parsed["title"] == "只有 OG"
    long_text = "这是官方转写。" * 10
    html_with_text = html.replace(
        "</body>",
        '<script id="__NEXT_DATA__" type="application/json">'
        '{"props":{"pageProps":{"episode":{"title":"有转写","transcript":"%s"}}}}'
        "</script></body>" % long_text,
    )
    parsed = parse_episode_html("https://www.xiaoyuzhoufm.com/episode/x", html_with_text)
    assert parsed["transcript"] == long_text


def test_generic_article_extraction():
    html = """
    <html><head>
      <title>页面标题</title>
      <meta property="og:title" content="OG 标题" />
      <meta name="author" content="作者乙" />
      <meta property="article:published_time" content="2024-05-01T08:00:00Z" />
    </head><body>
      <article>
        <p>这是一段足够长的正文，用来确认提取器能拿到主要段落，而不是导航栏里的短文字。后面再补一句，让长度明显超过提取器的下限，避免被当成导航或版权声明丢掉。</p>
        <p>第二段继续说明同一件事，保证正文信号足够强。</p>
      </article>
    </body></html>
    """
    parsed = parse_generic_html("https://example.com/post", html)
    assert parsed["title"] == "OG 标题"
    assert parsed["author"] == "作者乙"
    assert parsed["publish_date"] == "2024-05-01"
    assert "足够长的正文" in parsed["text"]


def test_fallback_markdown_uses_article_when_trafilatura_is_not_used():
    html = """
    <html><body>
      <nav><p>首页</p></nav>
      <div class="post"><p>兜底提取应该拿到这篇帖子的正文，而不是导航里的短链接文字。这里把段落写长一点。</p></div>
    </body></html>
    """
    text = fallback_markdown(make_soup(html))
    assert "兜底提取应该拿到这篇帖子的正文" in text
    assert "首页" not in text


def test_subtitle_language_preference_and_formats():
    subtitles = {
        "danmaku": [{"ext": "xml", "url": "https://comment.bilibili.com/1.xml"}],
        "ai-zh": [{"ext": "json", "data": '{"body":[{"from":0,"to":1,"content":"人工智能字幕"}]}'}],
        "zh-Hans": [
            {"ext": "xml", "url": "https://example.invalid/a.xml"},
            {"ext": "srt", "data": "1\n00:00:01,000 --> 00:00:02,000\n人工字幕\n"},
        ],
    }
    lang, track = select_subtitle_track(subtitles, {"en": [{"ext": "vtt", "data": "WEBVTT"}]})
    assert lang == "zh-Hans"
    assert track["ext"] == "srt"
    assert subtitle_to_text(track["data"], "srt") == "人工字幕"

    lang, track = select_subtitle_track({"ai-zh": subtitles["ai-zh"]}, {})
    assert lang == "ai-zh"
    assert subtitle_to_text(track["data"], "json") == "人工智能字幕"


def test_bilibili_parser_uses_subtitle_and_does_not_ask_for_asr():
    info = MediaInfo(
        id="BV1",
        title="视频标题",
        uploader="UP 主",
        upload_date="2024-02-03",
        webpage_url="https://www.bilibili.com/video/BV1",
        description="简介正文",
        subtitles={"ai-zh": [{"ext": "srt", "data": "1\n00:00:00,000 --> 00:00:01,000\n你好世界\n"}]},
    )

    class Media:
        def extract(self, url, *, cookiefile=None):
            assert cookiefile is None
            return info

        def download_audio(self, url, dest_dir, *, cookiefile=None):
            raise AssertionError("有字幕时不应该下载音频")

    item = BilibiliParser().parse(
        "https://b23.tv/abc",
        ParseContext(config=AppConfig(), http=None, media=Media(), cache_dir=Path(".")),
    )
    assert item.platform == "bilibili"
    assert item.needs_asr is False
    assert item.text_source == "subtitle:ai-zh"
    assert "你好世界" in item.text
    assert item.author == "UP 主"
    assert item.publish_date == "2024-02-03"
    assert item.shownotes == "简介正文"
    assert item.cookie_key == "bilibili"


def test_ytdlp_412_message_mentions_cookie():
    message = explain_ytdlp_error(RuntimeError("HTTP Error 412: Precondition Failed"))
    assert "412" in message
    assert "cookies.bilibili" in message
