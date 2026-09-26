from __future__ import annotations


class PromptRewriterError(RuntimeError):
    """Base class for expected application failures."""


class ConfigurationError(PromptRewriterError):
    """Raised when environment configuration is invalid."""


class ClipboardError(PromptRewriterError):
    """Raised when the Windows clipboard cannot be read or written safely."""


class DesktopIntegrationError(PromptRewriterError):
    """Raised when Windows hooks or process guards cannot be initialized."""


class OutputValidationError(PromptRewriterError):
    """Raised when a model response is not a paste-ready structured prompt."""


class InferenceError(PromptRewriterError):
    """A provider failure whose message is safe to log."""

    def __init__(self, provider: str, detail: str) -> None:
        self.provider = provider
        self.detail = detail
        super().__init__(f"{provider}: {detail}")


class AllProvidersFailed(PromptRewriterError):
    """Raised after every configured provider fails once."""

    def __init__(self, failures: tuple[InferenceError, ...]) -> None:
        self.failures = failures
        summary = "; ".join(str(failure) for failure in failures)
        super().__init__(f"All inference providers failed: {summary}")
