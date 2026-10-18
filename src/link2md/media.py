"""yt-dlp wrapper.

Bilibili pages from a datacenter IP often answer HTTP 412 until a logged-in
cookie file is supplied. Subtitle language ``ai-zh`` is Bilibili's AI caption
and, as of yt-dlp 2026.08, lives in ``subtitles`` rather than
``automatic_captions``. This module only normalizes that payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from link2md.errors import MediaError


@dataclass
class MediaInfo:
    id: str
    title: str
    uploader: str
    upload_date: str | None
    webpage_url: str
    description: str
    duration: float | None = None
    subtitles: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    automatic_captions: dict[str, list[dict[str, Any]]] = field(default_factory=dict)


class YtDlpBackend:
    def extract(self, url: str, *, cookiefile: str | None = None) -> MediaInfo:
        ydl_module = _import_yt_dlp()
        options: dict[str, Any] = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "noprogress": True,
            "logger": _SilentLogger(),
        }
        if cookiefile:
            options["cookiefile"] = cookiefile
        try:
            with ydl_module.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise MediaError(explain_ytdlp_error(exc)) from exc
        return media_info_from_dict(_flatten_playlist(info))

    def download_audio(self, url: str, dest_dir: Path, *, cookiefile: str | None = None) -> Path:
        ydl_module = _import_yt_dlp()
        dest_dir.mkdir(parents=True, exist_ok=True)
        options: dict[str, Any] = {
            "format": "bestaudio/best",
            "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "noprogress": True,
            "restrictfilenames": True,
            "logger": _SilentLogger(),
        }
        if cookiefile:
            options["cookiefile"] = cookiefile
        try:
            with ydl_module.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                info = _flatten_playlist(info)
                prepared = Path(ydl.prepare_filename(info))
        except Exception as exc:
            raise MediaError(explain_ytdlp_error(exc)) from exc
        if prepared.is_file():
            return prepared
        matches = sorted(dest_dir.glob(f"{info.get('id', '')}.*"))
        files = [path for path in matches if path.is_file()]
        if files:
            return files[0]
        raise MediaError("音频下载结束，但没有在缓存目录里找到文件。")


def media_info_from_dict(info: dict[str, Any]) -> MediaInfo:
    upload = info.get("upload_date") or ""
    publish = None
    if isinstance(upload, str) and len(upload) == 8 and upload.isdigit():
        publish = f"{upload[0:4]}-{upload[4:6]}-{upload[6:8]}"
    return MediaInfo(
        id=str(info.get("id") or ""),
        title=str(info.get("title") or "").strip(),
        uploader=str(info.get("uploader") or info.get("channel") or info.get("creator") or "").strip(),
        upload_date=publish,
        webpage_url=str(info.get("webpage_url") or info.get("original_url") or ""),
        description=str(info.get("description") or "").strip(),
        duration=_as_float(info.get("duration")),
        subtitles=dict(info.get("subtitles") or {}),
        automatic_captions=dict(info.get("automatic_captions") or {}),
    )


def explain_ytdlp_error(exc: Exception) -> str:
    message = str(exc)
    if "412" in message:
        return (
            "B 站返回 HTTP 412，当前网络被风控拦截。"
            "把浏览器登录态导出为 Netscape cookies.txt，填到配置 cookies.bilibili 后再试。"
        )
    lowered = message.lower()
    if "login" in lowered or "cookie" in lowered or "subtitle" in lowered and "logged" in lowered:
        return f"抓取媒体失败，可能需要登录 Cookie（cookies.bilibili）。详情：{message}"
    return f"抓取媒体失败：{message}"


def _flatten_playlist(info: dict[str, Any]) -> dict[str, Any]:
    if info.get("_type") != "playlist":
        return info
    entries = [entry for entry in info.get("entries") or [] if entry]
    if not entries:
        raise MediaError("播放列表是空的，没有可保存的条目。")
    return entries[0]


class _SilentLogger:
    """Swallow yt-dlp's own stderr. Callers raise MediaError with a Chinese message."""

    def debug(self, msg: str, *args: object, **kwargs: object) -> None:
        return None

    def info(self, msg: str, *args: object, **kwargs: object) -> None:
        return None

    def warning(self, msg: str, *args: object, **kwargs: object) -> None:
        return None

    def error(self, msg: str, *args: object, **kwargs: object) -> None:
        return None


def _import_yt_dlp() -> Any:
    try:
        import yt_dlp
    except ImportError as exc:
        raise MediaError("没有安装 yt-dlp。请重新安装 link2md。") from exc
    return yt_dlp


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
