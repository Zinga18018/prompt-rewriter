from __future__ import annotations

import httpx

from prompt_rewriter.config import Settings


def _extract_model_ids(
    payload: object,
    *,
    collection_key: str,
    id_keys: tuple[str, ...],
) -> set[str]:
    if not isinstance(payload, dict):
        raise ValueError("response is not an object")
    items = payload.get(collection_key)
    if not isinstance(items, list):
        raise ValueError("model collection is not a list")

    model_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("model entry is not an object")
        identifier = next(
            (item[key] for key in id_keys if isinstance(item.get(key), str)),
            None,
        )
        if identifier is None:
            raise ValueError("model entry has no string identifier")
        model_ids.add(identifier)
    return model_ids


def _check_groq(settings: Settings) -> tuple[bool, str]:
    if not settings.groq_api_key:
        return False, "not configured (GROQ_API_KEY is missing)"
    try:
        response = httpx.get(
            f"{settings.groq_base_url}/models",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            timeout=min(settings.groq_timeout_seconds, 5.0),
        )
        response.raise_for_status()
        model_ids = _extract_model_ids(response.json(), collection_key="data", id_keys=("id",))
    except httpx.HTTPStatusError as exc:
        return False, f"authentication/API check failed (HTTP {exc.response.status_code})"
    except (httpx.RequestError, TypeError, ValueError) as exc:
        return False, f"API check failed ({type(exc).__name__})"
    if settings.groq_model not in model_ids:
        return False, f"connected, but model {settings.groq_model!r} was not listed"
    return True, f"connected; model {settings.groq_model!r} is available"


def _check_gemini(settings: Settings) -> tuple[bool, str]:
    if not settings.gemini_api_key:
        return False, "not configured (GEMINI_API_KEY is missing)"
    try:
        response = httpx.get(
            f"{settings.gemini_base_url}/models/{settings.gemini_model}",
            headers={"x-goog-api-key": settings.gemini_api_key},
            timeout=min(settings.gemini_timeout_seconds, 5.0),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response is not an object")
        expected_name = f"models/{settings.gemini_model}"
        if payload.get("name") != expected_name:
            raise ValueError("response returned a different model")
        methods = payload.get("supportedGenerationMethods")
        if isinstance(methods, list) and "generateContent" not in methods:
            return False, f"connected, but model {settings.gemini_model!r} cannot generate content"
    except httpx.HTTPStatusError as exc:
        return False, f"authentication/API check failed (HTTP {exc.response.status_code})"
    except (httpx.RequestError, TypeError, ValueError) as exc:
        return False, f"API check failed ({type(exc).__name__})"
    return True, f"connected; model {settings.gemini_model!r} is available"


def _check_ollama(settings: Settings) -> tuple[bool, str]:
    try:
        with httpx.Client(timeout=2.0, trust_env=False) as client:
            response = client.get(f"{settings.ollama_url}/api/tags")
        response.raise_for_status()
        names = _extract_model_ids(
            response.json(), collection_key="models", id_keys=("name", "model")
        )
    except httpx.HTTPStatusError as exc:
        return False, f"server check failed (HTTP {exc.response.status_code})"
    except (httpx.RequestError, TypeError, ValueError) as exc:
        return False, f"server check failed ({type(exc).__name__})"
    if settings.ollama_model not in names:
        return False, f"server is running, but {settings.ollama_model!r} is not installed"
    return True, f"connected; model {settings.ollama_model!r} is installed"


def run_diagnostics(settings: Settings) -> int:
    checkers = {"gemini": _check_gemini, "groq": _check_groq, "ollama": _check_ollama}
    checks = {name: checkers[name](settings) for name in settings.provider_order}
    print(f"Hotkey: {settings.hotkey}")
    print(f"Provider order: {', '.join(settings.provider_order)}")
    for name in settings.provider_order:
        healthy, detail = checks[name]
        marker = "OK" if healthy else "NOT READY"
        print(f"{name}: {marker} - {detail}")
    return 0 if any(checks[name][0] for name in settings.provider_order) else 1
