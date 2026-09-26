from __future__ import annotations

import pytest

from prompt_rewriter.config import Settings
from prompt_rewriter.errors import ConfigurationError


def test_settings_from_env_parses_and_normalizes_values() -> None:
    settings = Settings.from_env(
        {
            "PROMPT_REWRITER_HOTKEY": "alt+space",
            "PROMPT_REWRITER_PROVIDER_ORDER": " Ollama, Groq ",
            "PROMPT_REWRITER_COPY_TIMEOUT_SECONDS": "2.5",
            "PROMPT_REWRITER_PASTE_SETTLE_SECONDS": "0",
            "PROMPT_REWRITER_RESTORE_CLIPBOARD": "off",
            "PROMPT_REWRITER_MAX_INPUT_CHARS": "321",
            "PROMPT_REWRITER_MAX_OUTPUT_CHARS": "654",
            "PROMPT_REWRITER_LOG_LEVEL": "debug",
            "GROQ_API_KEY": "  secret  ",
            "GROQ_BASE_URL": "https://api.groq.com/openai/v1/",
            "OLLAMA_URL": "http://127.0.0.1:11434/",
        }
    )

    assert settings.hotkey == "alt+space"
    assert settings.provider_order == ("ollama", "groq")
    assert settings.copy_timeout_seconds == 2.5
    assert settings.paste_settle_seconds == 0
    assert settings.restore_clipboard is False
    assert settings.max_input_chars == 321
    assert settings.max_output_chars == 654
    assert settings.log_level == "DEBUG"
    assert settings.groq_api_key == "secret"
    assert settings.groq_base_url == "https://api.groq.com/openai/v1"
    assert settings.ollama_url == "http://127.0.0.1:11434"


@pytest.mark.parametrize(
    ("environment", "message"),
    [
        ({"PROMPT_REWRITER_PROVIDER_ORDER": ""}, "cannot be empty"),
        ({"PROMPT_REWRITER_PROVIDER_ORDER": "groq,other"}, "Unsupported providers"),
        ({"PROMPT_REWRITER_PROVIDER_ORDER": "groq,groq"}, "contains duplicates"),
        ({"PROMPT_REWRITER_COPY_TIMEOUT_SECONDS": "0"}, "greater than zero"),
        ({"PROMPT_REWRITER_COPY_TIMEOUT_SECONDS": "nan"}, "greater than zero"),
        ({"PROMPT_REWRITER_COPY_TIMEOUT_SECONDS": "inf"}, "greater than zero"),
        ({"PROMPT_REWRITER_PASTE_SETTLE_SECONDS": "-1"}, "cannot be negative"),
        ({"PROMPT_REWRITER_PASTE_SETTLE_SECONDS": "nan"}, "cannot be negative"),
        ({"PROMPT_REWRITER_MAX_INPUT_CHARS": "1.5"}, "must be an integer"),
        ({"PROMPT_REWRITER_RESTORE_CLIPBOARD": "maybe"}, "must be true or false"),
        ({"PROMPT_REWRITER_LOG_LEVEL": "TRACE"}, "must be one of"),
        ({"OLLAMA_URL": "http://remote.example:11434"}, "must use a loopback"),
        ({"OLLAMA_URL": "http://localhost:11434/api/generate"}, "not a valid"),
        ({"OLLAMA_URL": "http://localhost:notaport"}, "invalid port"),
        ({"OLLAMA_URL": "http://user@localhost:11434"}, "not a valid"),
        ({"OLLAMA_URL": "http://localhost:11434?x=1"}, "not a valid"),
        ({"GROQ_BASE_URL": "http://api.groq.com/v1"}, "not a valid"),
        ({"GROQ_BASE_URL": "https://groq.test/v1"}, "official provider host"),
        ({"GROQ_BASE_URL": "https://groq.test:notaport/v1"}, "invalid port"),
    ],
)
def test_settings_from_env_rejects_invalid_values(
    environment: dict[str, str], message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        Settings.from_env(environment)
