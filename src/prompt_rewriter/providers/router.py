from __future__ import annotations

import logging

from prompt_rewriter.errors import AllProvidersFailed, InferenceError
from prompt_rewriter.providers.base import RewriteProvider, RewriteResult

logger = logging.getLogger(__name__)


class FallbackRouter:
    """Try each provider once, in configured order, with no hidden retries."""

    def __init__(self, providers: tuple[RewriteProvider, ...]) -> None:
        if not providers:
            raise ValueError("FallbackRouter requires at least one provider")
        self._providers = providers

    @property
    def provider_names(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self._providers)

    def rewrite(self, rough_text: str) -> RewriteResult:
        failures: list[InferenceError] = []
        for provider in self._providers:
            try:
                result = provider.rewrite(rough_text)
            except InferenceError as exc:
                failures.append(exc)
                logger.warning("Provider %s failed: %s", provider.name, exc.detail)
                continue
            except Exception as exc:  # Defensive boundary: still allow the fallback provider.
                failure = InferenceError(
                    provider.name, f"unexpected provider error ({type(exc).__name__})"
                )
                failures.append(failure)
                logger.exception("Unexpected provider error from %s", provider.name)
                continue

            logger.info(
                "Rewrite completed with %s/%s in %d ms",
                result.provider,
                result.model,
                result.latency_ms,
            )
            return result
        raise AllProvidersFailed(tuple(failures))

    def close(self) -> None:
        for provider in self._providers:
            try:
                provider.close()
            except Exception:
                logger.exception("Failed to close provider %s", provider.name)
