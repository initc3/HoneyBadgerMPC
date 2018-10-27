class HoneyBadgerMPCError(Exception):
    """Base exception class."""


class ConfigurationError(HoneyBadgerMPCError):
    """Raise for configuration errors."""
