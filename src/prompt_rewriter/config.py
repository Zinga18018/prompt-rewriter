from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv

from prompt_rewriter.errors import ConfigurationError

_PROVIDERS = {"gemini", "groq", "ollama"}
_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _positive_float(source: Mapping[str, str], name: str, default: float) -> float:
    raw = source.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _nonnegative_float(source: Mapping[str, str], name: str, default: float) -> float:
    raw = source.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number, got {raw!r}") from exc
    if not math.isfinite(value) or value < 0:
        raise ConfigurationError(f"{name} cannot be negative")
    return value


def _positive_int(source: Mapping[str, str], name: str, default: int) -> int:
    raw = source.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _boolean(source: Mapping[str, str], name: str, default: bool) -> bool:
    raw = source.get(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true or false, got {raw!r}")


def _nonempty_text(source: Mapping[str, str], name: str, default: str) -> str:
    value = source.get(name, default).strip()
    if not value:
        raise ConfigurationError(f"{name} cannot be empty")
    return value


def _validate_base_url(
    name: str,
    value: str,
    *,
    allowed_schemes: set[str],
    allowed_hosts: set[str] | None = None,
    loopback_only: bool = False,
    allow_path: bool = True,
) -> str:
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError(f"{name} contains an invalid port") from exc
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (port is not None and not 1 <= port <= 65_535)
        or (not allow_path and bool(parsed.path.rstrip("/")))
    ):
        raise ConfigurationError(f"{name} is not a valid provider base URL")
    if loopback_only and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ConfigurationError(f"{name} must use a loopback host")
    if allowed_hosts is not None and parsed.hostname not in allowed_hosts:
        raise ConfigurationError(f"{name} must use an official provider host")
    return value.rstrip("/")


def _provider_order(source: Mapping[str, str]) -> tuple[str, ...]:
    # Preserve the existing route unless the user explicitly opts Gemini in.
    raw = source.get("PROMPT_REWRITER_PROVIDER_ORDER", "groq,ollama")
    values = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    if not values:
        raise ConfigurationError("PROMPT_REWRITER_PROVIDER_ORDER cannot be empty")
    unknown = set(values) - _PROVIDERS
    if unknown:
        raise ConfigurationError("Unsupported providers: " + ", ".join(sorted(unknown)))
    if len(values) != len(set(values)):
        raise ConfigurationError("PROMPT_REWRITER_PROVIDER_ORDER contains duplicates")
    return values


def _gemini_model(source: Mapping[str, str]) -> str:
    model = _nonempty_text(source, "GEMINI_MODEL", "gemini-3.5-flash-lite")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model) is None:
        raise ConfigurationError("GEMINI_MODEL contains unsupported characters")
    return model


@dataclass(frozen=True, slots=True)
class Settings:
    hotkey: str
    provider_order: tuple[str, ...]
    copy_chord: str
    paste_chord: str
    copy_timeout_seconds: float
    paste_settle_seconds: float
    restore_clipboard: bool
    max_input_chars: int
    max_output_chars: int
    log_level: str
    gemini_api_key: str | None = field(repr=False)
    gemini_model: str
    gemini_timeout_seconds: float
    gemini_max_tokens: int
    gemini_base_url: str
    groq_api_key: str | None = field(repr=False)
    groq_model: str
    groq_timeout_seconds: float
    groq_max_tokens: int
    groq_base_url: str
    ollama_url: str
    ollama_model: str
    ollama_timeout_seconds: float
    ollama_max_tokens: int
    ollama_keep_alive: str

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        if environ is None:
            load_dotenv(override=False)
            source: Mapping[str, str] = os.environ
        else:
            source = environ

        log_level = source.get("PROMPT_REWRITER_LOG_LEVEL", "INFO").strip().upper()
        if log_level not in _LOG_LEVELS:
            raise ConfigurationError(
                "PROMPT_REWRITER_LOG_LEVEL must be one of " + ", ".join(sorted(_LOG_LEVELS))
            )

        gemini_key = source.get("GEMINI_API_KEY", "").strip() or None
        groq_key = source.get("GROQ_API_KEY", "").strip() or None
        ollama_url = _nonempty_text(source, "OLLAMA_URL", "http://127.0.0.1:11434")
        gemini_base_url = _nonempty_text(
            source,
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        )
        groq_base_url = _nonempty_text(source, "GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        ollama_url = _validate_base_url(
            "OLLAMA_URL",
            ollama_url,
            allowed_schemes={"http", "https"},
            loopback_only=True,
            allow_path=False,
        )
        groq_base_url = _validate_base_url(
            "GROQ_BASE_URL",
            groq_base_url,
            allowed_schemes={"https"},
            allowed_hosts={"api.groq.com"},
        )
        gemini_base_url = _validate_base_url(
            "GEMINI_BASE_URL",
            gemini_base_url,
            allowed_schemes={"https"},
            allowed_hosts={"generativelanguage.googleapis.com"},
        )
        if urlparse(gemini_base_url).path != "/v1beta":
            raise ConfigurationError("GEMINI_BASE_URL must use the official /v1beta API path")

        return cls(
            hotkey=_nonempty_text(source, "PROMPT_REWRITER_HOTKEY", "ctrl+shift+space"),
            provider_order=_provider_order(source),
            copy_chord=_nonempty_text(source, "PROMPT_REWRITER_COPY_CHORD", "ctrl+c"),
            paste_chord=_nonempty_text(source, "PROMPT_REWRITER_PASTE_CHORD", "ctrl+v"),
            copy_timeout_seconds=_positive_float(
                source, "PROMPT_REWRITER_COPY_TIMEOUT_SECONDS", 0.35
            ),
            paste_settle_seconds=_nonnegative_float(
                source, "PROMPT_REWRITER_PASTE_SETTLE_SECONDS", 0.25
            ),
            restore_clipboard=_boolean(source, "PROMPT_REWRITER_RESTORE_CLIPBOARD", True),
            max_input_chars=_positive_int(source, "PROMPT_REWRITER_MAX_INPUT_CHARS", 12_000),
            max_output_chars=_positive_int(source, "PROMPT_REWRITER_MAX_OUTPUT_CHARS", 16_000),
            log_level=log_level,
            gemini_api_key=gemini_key,
            gemini_model=_gemini_model(source),
            gemini_timeout_seconds=_positive_float(source, "GEMINI_TIMEOUT_SECONDS", 6.0),
            gemini_max_tokens=_positive_int(source, "GEMINI_MAX_TOKENS", 650),
            gemini_base_url=gemini_base_url,
            groq_api_key=groq_key,
            groq_model=_nonempty_text(source, "GROQ_MODEL", "openai/gpt-oss-20b"),
            groq_timeout_seconds=_positive_float(source, "GROQ_TIMEOUT_SECONDS", 4.0),
            groq_max_tokens=_positive_int(source, "GROQ_MAX_TOKENS", 650),
            groq_base_url=groq_base_url,
            ollama_url=ollama_url,
            ollama_model=_nonempty_text(source, "OLLAMA_MODEL", "llama3.2:3b"),
            ollama_timeout_seconds=_positive_float(source, "OLLAMA_TIMEOUT_SECONDS", 45.0),
            ollama_max_tokens=_positive_int(source, "OLLAMA_MAX_TOKENS", 650),
            ollama_keep_alive=_nonempty_text(source, "OLLAMA_KEEP_ALIVE", "10m"),
        )
