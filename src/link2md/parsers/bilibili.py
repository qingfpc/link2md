"""Bilibili videos via yt-dlp.

Prefer an existing subtitle, including AI captions (``ai-zh``). When none is
available the item is marked ``needs_asr`` and the pipeline downloads audio.
"""

from __future__ import annotations

from link2md.errors import ParseError
from link2md.html_to_md import normalize_space
from link2md.log import get_logger
from link2md.models import Item
from link2md.parsers.base import ParseContext
from link2md.subtitles import select_subtitle_track, subtitle_to_text
from link2md.urls import hostname

_BILI_HOSTS = {"b23.tv", "www.b23.tv", "b23.wtf", "bili2233.cn"}


class BilibiliParser:
    platform = "bilibili"

    def match(self, url: str) -> bool:
        host = hostname(url)
        return host in _BILI_HOSTS or host.endswith(".bilibili.com") or host == "bilibili.com"

    def parse(self, url: str, ctx: ParseContext) -> Item:
        cookiefile = ctx.config.cookie_file("bilibili")
        info = ctx.media.extract(url, cookiefile=cookiefile)
        title = normalize_space(info.title) or "未命名视频"
        author = normalize_space(info.uploader) or "未知"
        source = info.webpage_url or url
        description = (info.description or "").strip()
        shownotes = "" if not description or description == title else description

        text = ""
        text_source = ""
        needs_asr = True
        selected = select_subtitle_track(info.subtitles, info.automatic_captions)
        if selected is not None:
            lang, track = selected
            try:
                payload = _load_track(track, ctx)
                text = subtitle_to_text(payload, str(track.get("ext") or ""))
            except Exception as exc:
                get_logger().warning("字幕下载失败，改为转写音频：%s", exc)
                text = ""
            if text.strip():
                needs_asr = False
                text_source = f"subtitle:{lang}"
                get_logger().info("使用字幕：%s", lang)
            else:
                get_logger().info("选中的字幕是空的，改为转写音频。")
        else:
            get_logger().info("没有可用字幕（含 AI 字幕），将下载音频并转写。")

        if needs_asr and not cookiefile:
            get_logger().info(
                "若视频实际有字幕但列表为空，多半是未登录。可配置 cookies.bilibili 后重试。"
            )

        return Item(
            platform=self.platform,
            title=title,
            author=author,
            source_url=source,
            content_type="video",
            text=text,
            shownotes=shownotes,
            publish_date=info.upload_date,
            text_source=text_source,
            needs_asr=needs_asr,
            media_page_url=source,
            image_referer="https://www.bilibili.com/",
            cookie_key="bilibili",
        )


def _load_track(track: dict, ctx: ParseContext) -> str:
    data = track.get("data")
    if isinstance(data, str) and data.strip():
        return data
    subtitle_url = track.get("url")
    if not subtitle_url:
        raise ParseError("字幕轨没有内容，也没有下载地址。")
    if str(subtitle_url).startswith("//"):
        subtitle_url = "https:" + str(subtitle_url)
    return ctx.http.get_text(str(subtitle_url), headers={"Referer": "https://www.bilibili.com/"})
