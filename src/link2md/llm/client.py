"""OpenAI-compatible chat client. DeepSeek is the default base URL and model."""

from __future__ import annotations

from typing import Any

import httpx

from link2md.errors import Link2mdError


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.2,
        json_mode: bool = True,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.json_mode = json_mode
        self._client = httpx.Client(timeout=timeout, transport=transport, trust_env=True)

    def close(self) -> None:
        self._client.close()

    def complete(self, messages: list[dict[str, str]]) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": False,
        }
        use_json = self.json_mode
        last_error: Exception | None = None
        for attempt in range(2):
            body = dict(payload)
            if use_json:
                body["response_format"] = {"type": "json_object"}
            try:
                response = self._client.post(
                    chat_completions_url(self.base_url),
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                continue
            if response.status_code == 400 and use_json:
                # Some compatible gateways reject response_format. Retry once without it.
                use_json = False
                continue
            if response.status_code in {429, 500, 502, 503} and attempt == 0:
                last_error = Link2mdError(f"模型接口暂时失败：HTTP {response.status_code}")
                continue
            if response.status_code in {401, 403}:
                raise Link2mdError("模型接口拒绝了 API Key（HTTP %s）。请检查 DEEPSEEK_API_KEY。" % response.status_code)
            if response.status_code >= 400:
                raise Link2mdError(f"模型接口返回 HTTP {response.status_code}：{_short(response.text)}")
            return _message_text(response.json())
        raise Link2mdError(f"调用模型失败：{last_error}")


def chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _message_text(payload: Any) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise Link2mdError("模型响应里没有 choices[0].message.content。") from exc
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict):
                texts.append(str(part.get("text") or ""))
            else:
                texts.append(str(part))
        content = "".join(texts)
    text = str(content or "").strip()
    if not text:
        raise Link2mdError("模型返回了空内容。")
    return text


def _short(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:180]
