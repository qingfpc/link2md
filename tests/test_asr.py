"""ASR factory and availability checks. Models and cloud APIs are not called."""

import sys

from link2md.asr import create_transcriber
from link2md.asr.dashscope import DashScopeTranscriber
from link2md.asr.faster_whisper import FasterWhisperTranscriber
from link2md.config import AppConfig
from link2md.errors import ConfigError


def test_importing_asr_does_not_import_optional_backends():
    sys.modules.pop("faster_whisper", None)
    sys.modules.pop("dashscope", None)
    import link2md.asr  # noqa: F401

    assert "faster_whisper" not in sys.modules
    assert "dashscope" not in sys.modules


def test_faster_whisper_reports_missing_extra():
    def broken():
        raise ConfigError('本地转写需要可选依赖：pip install "link2md[asr]"')

    transcriber = FasterWhisperTranscriber(importer=broken)
    try:
        transcriber.ensure_available()
    except ConfigError as exc:
        assert "link2md[asr]" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_dashscope_requires_api_key():
    transcriber = DashScopeTranscriber(api_key="", importer=lambda: object())
    try:
        transcriber.ensure_available()
    except ConfigError as exc:
        assert "DASHSCOPE_API_KEY" in str(exc)
    else:
        raise AssertionError("expected ConfigError")


def test_unknown_backend():
    config = AppConfig()
    config.asr.backend = "other"
    try:
        create_transcriber(config)
    except ConfigError as exc:
        assert "other" in str(exc)
    else:
        raise AssertionError("expected ConfigError")
