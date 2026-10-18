"""LLM post-processing. The default provider is DeepSeek's OpenAI-compatible API."""

from link2md.config import AppConfig
from link2md.llm.client import OpenAICompatibleClient
from link2md.llm.postprocess import LlmResult, postprocess

__all__ = ["LlmResult", "OpenAICompatibleClient", "create_chat_client", "postprocess"]


def create_chat_client(config: AppConfig) -> OpenAICompatibleClient | None:
    """Return a client, or None when no API key is configured.

    Any OpenAI-compatible endpoint works: set ``llm.base_url``, ``llm.model``,
    and ``llm.api_key_env``. ``llm.provider`` is a label stored for humans.
    """

    api_key = config.llm_api_key()
    if not api_key:
        return None
    return OpenAICompatibleClient(
        api_key=api_key,
        base_url=config.llm.base_url,
        model=config.llm.model,
        temperature=config.llm.temperature,
        json_mode=bool(config.llm.json_mode),
    )
