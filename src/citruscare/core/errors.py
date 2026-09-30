"""Exceptions raised by the CitrusCare SDK."""


class CitrusCareError(Exception):
    """Base class for SDK errors."""


class ConfigurationError(CitrusCareError, ValueError):
    """The SDK configuration is invalid or incomplete."""


class ProviderError(CitrusCareError):
    """A provider request or response failed."""


class ToolExecutionError(CitrusCareError):
    """A tool call was invalid or its handler failed."""


class StepLimitExceeded(CitrusCareError):
    """The agent requested more model turns than the configured limit."""


class AuditError(CitrusCareError):
    """An audit event could not be recorded."""
