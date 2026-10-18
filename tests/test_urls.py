"""URL extraction and platform routing. No network."""

import pytest

from link2md.errors import Link2mdError, UnsupportedPlatformError
from link2md.parsers.registry import match_platform
from link2md.urls import canonical_url, extract_url


def _platform(text: str) -> str:
    return match_platform(extract_url(text))


@pytest.mark.parametrize(
    ("text", "url"),
    [
        ("https://www.bilibili.com/video/BV1xx411c7mD", "https://www.bilibili.com/video/BV1xx411c7mD"),
        ("看看这个 https://b23.tv/abc123，点击观看", "https://b23.tv/abc123"),
        ("<https://mp.weixin.qq.com/s/abcDEF>", "https://mp.weixin.qq.com/s/abcDEF"),
        ("mp.weixin.qq.com/s/bareToken", "https://mp.weixin.qq.com/s/bareToken"),
        (
            "https://mp.weixin.qq.com/s?__biz=abc&amp;mid=1&amp;idx=2&amp;sn=ff",
            "https://mp.weixin.qq.com/s?__biz=abc&mid=1&idx=2&sn=ff",
        ),
        ("先有 https://example.com/a 再有 https://example.com/b", "https://example.com/a"),
    ],
)
def test_extract_url(text, url):
    assert extract_url(text) == url


def test_extract_url_strips_shell_backslash():
    assert extract_url(r"https://mp.weixin.qq.com/s/abc\&foo=1") == "https://mp.weixin.qq.com/s/abc&foo=1"


def test_extract_url_rejects_empty():
    with pytest.raises(Link2mdError, match="没有在输入里找到链接"):
        extract_url("今天没有链接")


@pytest.mark.parametrize(
    ("text", "platform"),
    [
        ("https://www.bilibili.com/video/BV1xx411c7mD/", "bilibili"),
        ("https://m.bilibili.com/video/BV1xx411c7mD", "bilibili"),
        ("【视频】https://b23.tv/xyz 复制打开", "bilibili"),
        ("https://b23.wtf/xyz", "bilibili"),
        ("https://www.xiaoyuzhoufm.com/episode/67164e0d0d2f24f289c01c1e?s=1", "xiaoyuzhou"),
        ("https://xiaoyuzhoufm.com/episode/abc", "xiaoyuzhou"),
        ("https://mp.weixin.qq.com/s/qAjJnqLSzZUKBT1_huFWig", "wechat"),
        ("https://example.com/posts/1", "web"),
        ("https://blog.example.org/2024/hello", "web"),
    ],
)
def test_route_platform(text, platform):
    assert _platform(text) == platform


@pytest.mark.parametrize(
    "text",
    [
        "https://v.douyin.com/iXXXX/",
        "https://www.douyin.com/video/123",
        "https://www.iesdouyin.com/share/video/1",
        "https://www.xiaohongshu.com/explore/abc",
        "http://xhslink.com/a/abc",
    ],
)
def test_reserved_platforms_are_explicit(text):
    with pytest.raises(UnsupportedPlatformError, match="v2"):
        _platform(text)


def test_canonical_url_strips_tracking_and_normalizes_host():
    url = "https://m.bilibili.com/video/BV1xx411c7mD/?spm_id_from=333.1&p=2#reply"
    assert canonical_url(url) == "https://www.bilibili.com/video/BV1xx411c7mD?p=2"


def test_canonical_wechat_short_path_drops_query():
    url = "https://mp.weixin.qq.com/s/abc?scene=1&nwr_flag=1#wechat_redirect"
    assert canonical_url(url) == "https://mp.weixin.qq.com/s/abc"


def test_canonical_wechat_legacy_query_keeps_identity_fields():
    raw = extract_url("https://mp.weixin.qq.com/s?__biz=abc&amp;mid=1&amp;idx=2&amp;sn=ff&amp;scene=9")
    assert canonical_url(raw) == "https://mp.weixin.qq.com/s?__biz=abc&mid=1&idx=2&sn=ff"


def test_canonical_xiaoyuzhou_drops_share_query():
    url = "https://xiaoyuzhoufm.com/episode/abc/?s=share"
    assert canonical_url(url) == "https://www.xiaoyuzhoufm.com/episode/abc"
