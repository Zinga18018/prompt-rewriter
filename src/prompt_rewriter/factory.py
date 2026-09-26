from __future__ import annotations

import logging

from prompt_rewriter.config import Settings
from prompt_rewriter.errors import ConfigurationError
from prompt_rewriter.providers.groq_provider import GroqProvider
from prompt_rewriter.providers.ollama_provider import OllamaProvider
from prompt_rewriter.providers.router import FallbackRouter

logger = logging.getLogger(__name__)


def build_router(settings: Settings) -> FallbackRouter:
    providers = []
    for provider_name in settings.provider_order:
        if provider_name == "groq":
            if not settings.groq_api_key:
                logger.info("Skipping Groq because GROQ_API_KEY is not configured")
                continue
            providers.append(
                GroqProvider(
                    api_key=settings.groq_api_key,
                    model=settings.groq_model,
                    timeout_seconds=settings.groq_timeout_seconds,
                    max_tokens=settings.groq_max_tokens,
                    max_output_chars=settings.max_output_chars,
                    base_url=settings.groq_base_url,
                )
            )
        elif provider_name == "ollama":
            providers.append(
                OllamaProvider(
                    url=settings.ollama_url,
                    model=settings.ollama_model,
                    timeout_seconds=settings.ollama_timeout_seconds,
                    max_tokens=settings.ollama_max_tokens,
                    max_output_chars=settings.max_output_chars,
                    keep_alive=settings.ollama_keep_alive,
                )
            )

    if not providers:
        raise ConfigurationError(
            "No usable provider is configured. Add GROQ_API_KEY or include ollama in "
            "PROMPT_REWRITER_PROVIDER_ORDER."
        )
    return FallbackRouter(tuple(providers))
