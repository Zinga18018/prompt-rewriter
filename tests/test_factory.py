from __future__ import annotations

import pytest

from prompt_rewriter.config import Settings
from prompt_rewriter.errors import ConfigurationError
from prompt_rewriter.factory import build_router


def test_factory_includes_gemini_only_when_explicitly_configured() -> None:
    settings = Settings.from_env(
        {
            "PROMPT_REWRITER_PROVIDER_ORDER": "gemini,ollama",
            "GEMINI_API_KEY": "not-used-by-test",
        }
    )

    router = build_router(settings)
    try:
        assert router.provider_names == ("gemini", "ollama")
    finally:
        router.close()


def test_factory_skips_unconfigured_gemini_and_keeps_fallback() -> None:
    settings = Settings.from_env(
        {
            "PROMPT_REWRITER_PROVIDER_ORDER": "gemini,ollama",
        }
    )

    router = build_router(settings)
    try:
        assert router.provider_names == ("ollama",)
    finally:
        router.close()


def test_factory_rejects_gemini_only_without_a_key() -> None:
    settings = Settings.from_env({"PROMPT_REWRITER_PROVIDER_ORDER": "gemini"})

    with pytest.raises(ConfigurationError, match="No usable provider"):
        build_router(settings)
