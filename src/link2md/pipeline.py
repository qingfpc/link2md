"""Turn one pasted link into a Markdown note in the Obsidian vault."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from link2md.config import AppConfig
from link2md.errors import ParseError
from link2md.filenames import safe_filename
from link2md.http import HttpxClient
from link2md.images import ImageLocalizer
from link2md.log import get_logger
from link2md.markdown_note import Note, render_note
from link2md.media import YtDlpBackend
from link2md.models import Item, SaveResult
from link2md.parsers.base import ParseContext
from link2md.parsers.registry import get_parser
from link2md.urls import SHORT_HOSTS, canonical_url, extract_url, hostname
from link2md.vault import Vault

_AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac", ".mp4", ".opus"}


def save_link(
    text: str,
    config: AppConfig,
    *,
    no_llm: bool = False,
    update: bool = False,
    http: HttpxClient | None = None,
    media: YtDlpBackend | None = None,
    transcriber=None,
    chat=None,
) -> SaveResult:
    """Save ``text`` (a URL or a share blurb) into the vault.

    Network, ASR, and LLM collaborators can be injected. When omitted, the
    real clients are built from ``config``.
    """

    logger = get_logger()
    owns_http = http is None
    if http is None:
        http = HttpxClient(timeout=config.http_timeout)
    if media is None:
        media = YtDlpBackend()
    try:
        raw_url = extract_url(text)
        url = _expand_short(raw_url, http)
        early_key = canonical_url(url)
        vault = Vault(config)
        policy = "update" if update else config.duplicate_policy
        if policy == "skip":
            existing = vault.find(early_key)
            if existing is not None:
                logger.info("这个链接已经保存过：%s", existing)
                return SaveResult(path=existing, status="skipped", canonical_url=early_key)

        ctx = ParseContext(config=config, http=http, media=media, cache_dir=config.cache_path())
        parser = get_parser(url)
        logger.info("识别为 %s：%s", parser.platform, url)
        item = parser.parse(url, ctx)
        canonical = canonical_url(item.source_url or url)
        existing = vault.find(canonical) or vault.find(early_key)
        if existing is not None and policy == "skip":
            logger.info("这个链接已经保存过：%s", existing)
            return SaveResult(
                path=existing,
                status="skipped",
                title=item.title,
                canonical_url=canonical,
            )

        if item.needs_asr:
            item = _transcribe(item, config, ctx, transcriber)

        if not item.text.strip() and not item.shownotes.strip():
            raise ParseError("没有提取到可用正文。")

        llm_result = _run_llm(item, config, no_llm=no_llm, chat=chat)
        note_path = existing or (vault.notes_dir / safe_filename(item.title, canonical))
        localizer = ImageLocalizer(
            vault.attachment_dir(note_path),
            note_path.parent,
            http,
            referer=item.image_referer,
        )
        body = localizer.rewrite(llm_result.cleaned_text)
        shownotes = localizer.rewrite(item.shownotes)
        note = Note(
            title=item.title or "未命名",
            platform=item.platform,
            author=item.author or "未知",
            source_url=canonical,
            saved_at=datetime.now().astimezone(),
            content_type=item.content_type,
            text_source=item.text_source,
            body=body,
            summary=llm_result.summary,
            key_points=llm_result.key_points,
            tags=llm_result.tags,
            publish_date=item.publish_date,
            shownotes=shownotes,
            llm_status=llm_result.status,
        )
        path = vault.write(
            canonical=canonical,
            title=note.title,
            markdown=render_note(note),
            existing=existing if policy == "update" else None,
        )
        status = "updated" if existing is not None and policy == "update" else "created"
        # ``existing`` with policy update overwrites. When policy is skip we
        # already returned. A missing file with a stale index still creates.
        if existing is not None and policy == "update":
            status = "updated"
        logger.info("笔记已写入：%s", path)
        return SaveResult(path=path, status=status, title=note.title, canonical_url=canonical)
    finally:
        if owns_http:
            http.close()


def _expand_short(url: str, http: HttpxClient) -> str:
    host = hostname(url)
    if host not in SHORT_HOSTS and not host.endswith("b23.tv"):
        return url
    try:
        resolved = http.resolve(url)
    except Exception as exc:
        get_logger().warning("短链没有展开（%s），继续使用原链接。", exc)
        return url
    get_logger().info("短链展开为：%s", resolved)
    return resolved


def _transcribe(item: Item, config: AppConfig, ctx: ParseContext, transcriber) -> Item:
    if transcriber is None:
        from link2md.asr import create_transcriber

        transcriber = create_transcriber(config, work_dir=ctx.cache_dir / "asr")
    transcriber.ensure_available()
    audio = _fetch_audio(item, ctx)
    language = config.asr.language.strip() or None
    get_logger().info("开始转写（%s）", getattr(transcriber, "name", config.asr.backend))
    transcript = transcriber.transcribe(audio, language=language)
    text = (transcript.text or "").strip()
    if not text:
        raise ParseError("转写结果是空的。")
    item.text = text
    item.text_source = f"asr:{getattr(transcriber, 'name', config.asr.backend)}"
    item.needs_asr = False
    return item


def _fetch_audio(item: Item, ctx: ParseContext) -> Path:
    dest_dir = ctx.cache_dir / "audio"
    dest_dir.mkdir(parents=True, exist_ok=True)
    if item.direct_media_url:
        digest = hashlib.sha1(item.direct_media_url.encode("utf-8")).hexdigest()[:16]
        dest = dest_dir / f"{digest}{_suffix(item.direct_media_url)}"
        if dest.is_file() and dest.stat().st_size > 0:
            get_logger().info("使用已缓存的音频：%s", dest.name)
            return dest
        headers = {"Referer": item.image_referer} if item.image_referer else None
        get_logger().info("正在下载音频")
        return ctx.http.download(item.direct_media_url, dest, headers=headers)
    if item.media_page_url:
        get_logger().info("正在通过 yt-dlp 下载音频")
        cookie = ctx.config.cookie_file(item.cookie_key)
        return ctx.media.download_audio(item.media_page_url, dest_dir, cookiefile=cookie)
    raise ParseError("需要转写，但没有音频地址。")


def _run_llm(item: Item, config: AppConfig, *, no_llm: bool, chat):
    from link2md.llm import LlmResult, create_chat_client, postprocess

    if not item.text.strip():
        return LlmResult(cleaned_text=item.text, status="skipped")
    if no_llm:
        get_logger().info("已跳过模型整理。")
        return LlmResult(cleaned_text=item.text, status="skipped")
    client = chat
    owns_client = False
    if client is None:
        client = create_chat_client(config)
        owns_client = client is not None
    if client is None:
        get_logger().warning("未配置 %s，已跳过摘要和整理。", config.llm.api_key_env)
        return LlmResult(cleaned_text=item.text, status="skipped")
    meta = f"标题：{item.title}\n作者：{item.author}\n平台：{item.platform}"
    try:
        return postprocess(item.text, chat=client, chunk_chars=config.llm.chunk_chars, meta=meta)
    except Exception as exc:
        get_logger().warning("模型整理失败，笔记仍会保存原文：%s", exc)
        return LlmResult(cleaned_text=item.text, status="failed")
    finally:
        if owns_client:
            client.close()


def _suffix(url: str) -> str:
    suffix = Path(urlsplit(url).path).suffix.lower()
    if suffix in _AUDIO_SUFFIXES:
        return suffix
    return ".m4a"
