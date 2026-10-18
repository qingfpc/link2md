"""Small HTTP wrapper around httpx so parsers can be tested with a fake client."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import httpx

from link2md.errors import ParseError

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class HttpxClient:
    def __init__(self, timeout: float = 30.0, user_agent: str = DEFAULT_UA) -> None:
        self.user_agent = user_agent
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept-Language": "zh-CN,zh;q=0.9"},
            trust_env=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpxClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_text(self, url: str, headers: Mapping[str, str] | None = None) -> str:
        try:
            response = self._client.get(url, headers=dict(headers or {}))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ParseError(f"请求页面失败：{url}（{exc}）") from exc
        return response.text

    def get_bytes(self, url: str, headers: Mapping[str, str] | None = None) -> bytes:
        try:
            response = self._client.get(url, headers=dict(headers or {}))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ParseError(f"下载失败：{url}（{exc}）") from exc
        return response.content

    def download(self, url: str, dest: Path, headers: Mapping[str, str] | None = None) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._client.stream("GET", url, headers=dict(headers or {})) as response:
                response.raise_for_status()
                with dest.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        handle.write(chunk)
        except httpx.HTTPError as exc:
            raise ParseError(f"下载文件失败：{url}（{exc}）") from exc
        return dest

    def resolve(self, url: str) -> str:
        """Follow redirects and return the final URL without reading the body."""

        try:
            with self._client.stream("GET", url) as response:
                response.raise_for_status()
                return str(response.url)
        except httpx.HTTPError as exc:
            raise ParseError(f"展开短链失败：{url}（{exc}）") from exc
