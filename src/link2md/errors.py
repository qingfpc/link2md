"""User-facing errors. Messages are written in Chinese."""


class Link2mdError(Exception):
    """Expected failure that should be shown to the user as-is."""


class ConfigError(Link2mdError):
    """Invalid or incomplete configuration."""


class UnsupportedPlatformError(Link2mdError):
    """Platform is recognized but not implemented in this version."""


class ParseError(Link2mdError):
    """The page or media item could not be turned into note content."""


class MediaError(Link2mdError):
    """Downloading or reading audio/video failed."""
