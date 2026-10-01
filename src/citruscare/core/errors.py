"""Exceptions raised by the CitrusCare SDK."""


class CitrusCareError(Exception):
    """Base class for SDK errors."""


class ConfigurationError(CitrusCareError, ValueError):
    """The SDK configuration is invalid or incomplete."""


class ProviderError(CitrusCareError):
    """A provider request or response failed."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "LLM_PROVIDER_ERROR",
        retryable: bool = False,
        status_code: int | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.provider_name = provider_name
        self.model_name = model_name


class ToolExecutionError(CitrusCareError):
    """A tool call was invalid or its handler failed."""


class StepLimitExceeded(CitrusCareError):
    """The agent requested more model turns than the configured limit."""


class AuditError(CitrusCareError):
    """An audit event could not be recorded."""
