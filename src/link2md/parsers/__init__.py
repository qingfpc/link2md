"""Pluggable platform parsers."""

from link2md.parsers.registry import builtin_parsers, get_parser, match_platform

__all__ = ["builtin_parsers", "get_parser", "match_platform"]
