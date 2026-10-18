"""Config loading stays offline and never calls the network."""

from pathlib import Path

import pytest

from link2md.config import example_config_text, load_config
from link2md.errors import ConfigError


def test_missing_default_file_uses_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr("link2md.config.default_config_path", lambda: tmp_path / "missing.yaml")
    config = load_config(environ={})
    assert config.vault.path == ""
    assert config.vault.notes_dir == "link2md"
    assert config.vault.attachments_dir == "link2md/attachments"
    assert config.asr.backend == "faster-whisper"
    assert config.asr.dashscope.model == "paraformer-realtime-v2"
    assert config.llm.provider == "deepseek"
    assert config.llm.model == "deepseek-flash"
    assert config.llm.base_url == "https://api.deepseek.com"
    assert config.cookies.bilibili == ""
    assert config.cookies.douyin == ""
    assert config.cookies.xiaohongshu == ""
    assert config.duplicate_policy == "skip"
    assert config.llm_api_key() == ""


def test_yaml_and_env_overrides(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        """
vault:
  path: /from/file
  notes_dir: notes
asr:
  backend: dashscope
llm:
  api_key_env: MY_LLM_KEY
  chunk_chars: 1000
cookies:
  bilibili: /tmp/bili.txt
  douyin: /tmp/douyin.txt
  xiaohongshu: ""
unknown_top_level: ignore-me
duplicate_policy: update
""",
        encoding="utf-8",
    )
    config = load_config(
        path,
        environ={
            "LINK2MD_VAULT": "/from/env",
            "LINK2MD_ASR_BACKEND": "faster-whisper",
            "MY_LLM_KEY": "sk-test",
            "DASHSCOPE_API_KEY": "dash-test",
        },
    )
    assert config.vault.path == "/from/env"
    assert config.vault.notes_dir == "notes"
    assert config.asr.backend == "faster-whisper"
    assert config.duplicate_policy == "update"
    assert config.llm.chunk_chars == 1000
    assert config.llm_api_key() == "sk-test"
    assert config.dashscope_api_key() == "dash-test"
    assert config.cookies.douyin == "/tmp/douyin.txt"
    assert not hasattr(config, "unknown_top_level")


def test_api_key_in_file_is_accepted(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("llm:\n  api_key: from-file\n", encoding="utf-8")
    config = load_config(path, environ={})
    assert config.llm_api_key() == "from-file"


def test_link2md_config_env(monkeypatch, tmp_path):
    path = tmp_path / "elsewhere.yaml"
    path.write_text("vault:\n  path: /via/envfile\n", encoding="utf-8")
    config = load_config(environ={"LINK2MD_CONFIG": str(path)})
    assert config.vault.path == "/via/envfile"
    assert config.config_path == str(path)


def test_explicit_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="找不到配置文件"):
        load_config(tmp_path / "nope.yaml", environ={})


def test_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("vault: [\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_config(path, environ={})


def test_invalid_backend(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("asr:\n  backend: whisper.cpp\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="ASR"):
        load_config(path, environ={})


def test_example_config_loads(tmp_path):
    text = example_config_text()
    root_copy = Path(__file__).resolve().parents[1] / "config.example.yaml"
    assert root_copy.read_text(encoding="utf-8") == text
    assert "cookies:" in text
    assert "douyin:" in text
    assert "xiaohongshu:" in text
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    config = load_config(path, environ={})
    assert config.asr.backend == "faster-whisper"
    assert config.llm.provider == "deepseek"
    assert config.cookies.bilibili == ""
    assert config.cookies.douyin == ""
    assert config.cookies.xiaohongshu == ""
