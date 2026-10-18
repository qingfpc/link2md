"""Load YAML config from the user config dir, then apply environment overrides.

API keys are read from the environment named by ``api_key_env``. A literal
``api_key`` field is accepted for local experiments, but ``link2md doctor``
warns about it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml
from platformdirs import user_cache_dir, user_config_dir

from link2md.errors import ConfigError

ASR_BACKENDS = ("faster-whisper", "dashscope")
DUPLICATE_POLICIES = ("skip", "update")


@dataclass
class VaultConfig:
    path: str = ""
    notes_dir: str = "link2md"
    attachments_dir: str = "link2md/attachments"


@dataclass
class FasterWhisperConfig:
    model: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"


@dataclass
class DashScopeConfig:
    # paraformer-v2 file transcription needs a public URL. Local files use the
    # realtime model, which accepts a filesystem path via Recognition.call.
    model: str = "paraformer-realtime-v2"
    api_key_env: str = "DASHSCOPE_API_KEY"
    api_key: str = ""
    base_websocket_api_url: str = ""
    chunk_seconds: int = 600


@dataclass
class AsrConfig:
    backend: str = "faster-whisper"
    language: str = "zh"
    faster_whisper: FasterWhisperConfig = field(default_factory=FasterWhisperConfig)
    dashscope: DashScopeConfig = field(default_factory=DashScopeConfig)


@dataclass
class LlmConfig:
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-flash"
    api_key_env: str = "DEEPSEEK_API_KEY"
    api_key: str = ""
    chunk_chars: int = 8000
    temperature: float = 0.2
    json_mode: bool = True


@dataclass
class CookiesConfig:
    """Netscape cookie files. Douyin / Xiaohongshu are reserved for v2."""

    bilibili: str = ""
    douyin: str = ""
    xiaohongshu: str = ""


@dataclass
class AppConfig:
    vault: VaultConfig = field(default_factory=VaultConfig)
    asr: AsrConfig = field(default_factory=AsrConfig)
    llm: LlmConfig = field(default_factory=LlmConfig)
    cookies: CookiesConfig = field(default_factory=CookiesConfig)
    cache_dir: str = ""
    duplicate_policy: str = "skip"
    http_timeout: float = 30.0
    log_level: str = "INFO"
    config_path: str = ""
    # Snapshot of the environment used for API keys. Filled by load_config.
    env: dict[str, str] = field(default_factory=dict)

    def vault_root(self) -> Path:
        return Path(self.vault.path).expanduser()

    def cache_path(self) -> Path:
        if self.cache_dir.strip():
            return Path(self.cache_dir).expanduser()
        return Path(user_cache_dir("link2md"))

    def llm_api_key(self) -> str:
        if self.llm.api_key.strip():
            return self.llm.api_key.strip()
        return str(self.env.get(self.llm.api_key_env, "")).strip()

    def dashscope_api_key(self) -> str:
        if self.asr.dashscope.api_key.strip():
            return self.asr.dashscope.api_key.strip()
        return str(self.env.get(self.asr.dashscope.api_key_env, "")).strip()

    def cookie_file(self, key: str | None) -> str | None:
        if not key:
            return None
        raw = getattr(self.cookies, key, "") or ""
        raw = str(raw).strip()
        if not raw:
            return None
        path = Path(raw).expanduser()
        if not path.is_file():
            raise ConfigError(f"Cookie 文件不存在：{path}")
        return str(path)


def default_config_path() -> Path:
    return Path(user_config_dir("link2md")) / "config.yaml"


def example_config_text() -> str:
    path = Path(__file__).with_name("resources") / "config.example.yaml"
    return path.read_text(encoding="utf-8")


def load_config(
    path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    require_file: bool = False,
) -> AppConfig:
    env = os.environ if environ is None else environ
    config_path, must_exist = _resolve_path(path, env, require_file)
    config = AppConfig()
    if config_path.is_file():
        _merge(config, _read_yaml(config_path))
        config.config_path = str(config_path)
    elif must_exist:
        raise ConfigError(f"找不到配置文件：{config_path}")
    _apply_env(config, env)
    config.env = {str(key): str(value) for key, value in env.items()}
    _validate(config)
    return config


def _resolve_path(
    path: str | Path | None,
    env: Mapping[str, str],
    require_file: bool,
) -> tuple[Path, bool]:
    """Return ``(path, must_exist)``.

    An explicit path argument and ``LINK2MD_CONFIG`` must exist. The default
    user-config location is optional so the CLI still runs before ``init``.
    """

    if path is not None:
        return Path(path).expanduser(), True
    env_path = env.get("LINK2MD_CONFIG")
    if env_path:
        return Path(env_path).expanduser(), True
    return default_config_path(), require_file


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"读取配置失败：{path}（{exc}）") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"配置文件不是合法的 YAML：{path}（{exc}）") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"配置文件的顶层必须是键值映射：{path}")
    return loaded


def _merge(target: Any, data: Mapping[str, Any]) -> None:
    if not isinstance(data, Mapping):
        raise ConfigError("配置里有一段应该是键值映射，但读到了其他类型。")
    known = {item.name for item in fields(target)}
    for key, value in data.items():
        if key not in known or key in {"config_path", "env"}:
            continue
        current = getattr(target, key)
        if is_dataclass(current) and isinstance(value, Mapping):
            _merge(current, value)
        else:
            setattr(target, key, value)


def _apply_env(config: AppConfig, env: Mapping[str, str]) -> None:
    vault = env.get("LINK2MD_VAULT")
    if vault:
        config.vault.path = vault
    backend = env.get("LINK2MD_ASR_BACKEND")
    if backend:
        config.asr.backend = backend.strip()
    policy = env.get("LINK2MD_DUPLICATE_POLICY")
    if policy:
        config.duplicate_policy = policy.strip()


def _validate(config: AppConfig) -> None:
    if config.asr.backend not in ASR_BACKENDS:
        names = "、".join(ASR_BACKENDS)
        raise ConfigError(f"未知的 ASR 后端：{config.asr.backend}。可选：{names}")
    if config.duplicate_policy not in DUPLICATE_POLICIES:
        names = "、".join(DUPLICATE_POLICIES)
        raise ConfigError(f"未知的 duplicate_policy：{config.duplicate_policy}。可选：{names}")
    if int(config.llm.chunk_chars) <= 0:
        raise ConfigError("llm.chunk_chars 必须大于 0。")
    if int(config.asr.dashscope.chunk_seconds) <= 0:
        raise ConfigError("asr.dashscope.chunk_seconds 必须大于 0。")
    config.llm.chunk_chars = int(config.llm.chunk_chars)
    config.asr.dashscope.chunk_seconds = int(config.asr.dashscope.chunk_seconds)
    config.http_timeout = float(config.http_timeout)
    config.llm.temperature = float(config.llm.temperature)
