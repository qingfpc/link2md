"""Logging setup. User-visible messages are Chinese; logger names stay English."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER_NAME = "link2md"


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


class _StderrHandler(logging.StreamHandler):
    """Write to the current ``sys.stderr``.

    ``StreamHandler()`` captures the stream object at construction time. A test
    runner (or a redirect) may close that object later; resolving it on emit
    keeps logs on the live stderr.
    """

    def __init__(self) -> None:
        super().__init__(stream=None)

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> logging.Logger:
    logger = get_logger()
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter("%(levelname)s %(message)s")
    stream = _StderrHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(file_handler)
    return logger
