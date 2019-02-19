class HoneyBadgerMPCError(Exception):
    """Base exception class."""


class ConfigurationError(HoneyBadgerMPCError):
    """Raise for configuration errors."""


class BroadcastError(HoneyBadgerMPCError):
    """Base class for broadcast errors."""


class RedundantMessageError(BroadcastError):
    """Raised when a rdundant message is received."""


class AbandonedNodeError(HoneyBadgerMPCError):
    """Raised when a node does not have enough peer to carry on a distirbuted task."""
