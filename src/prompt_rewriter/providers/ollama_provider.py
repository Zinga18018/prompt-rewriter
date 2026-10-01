from __future__ import annotations

import time

import httpx

from prompt_rewriter.errors import InferenceError, OutputValidationError
from prompt_rewriter.prompts import (
    PROMPT_REWRITE_SCHEMA,
    SYSTEM_PROMPT,
    build_user_message,
    clean_and_validate_output,
)
from prompt_rewriter.providers.base import RewriteResult


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        *,
        url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        max_output_chars: int,
        keep_alive: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._max_tokens = max_tokens
        self._max_output_chars = max_output_chars
        self._keep_alive = keep_alive
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(2.0, timeout_seconds),
            pool=min(2.0, timeout_seconds),
        )
        # A loopback request should not be routed through a corporate/system HTTP proxy.
        self._client = client or httpx.Client(base_url=url, timeout=timeout, trust_env=False)
        self._owns_client = client is None

    def rewrite(self, rough_text: str) -> RewriteResult:
        started = time.perf_counter()
        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": build_user_message(rough_text),
            "stream": False,
            "format": PROMPT_REWRITE_SCHEMA,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_predict": self._max_tokens,
            },
        }
        try:
            response = self._client.post("/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            if data.get("done") is not True:
                raise InferenceError(self.name, "generation ended without done=true")
            cleaned = clean_and_validate_output(data.get("response"), self._max_output_chars)
        except OutputValidationError as exc:
            raise InferenceError(self.name, f"invalid model output ({exc})") from exc
        except httpx.TimeoutException as exc:
            raise InferenceError(self.name, "request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise InferenceError(
                self.name, f"API request failed (HTTP {exc.response.status_code})"
            ) from exc
        except httpx.RequestError as exc:
            raise InferenceError(self.name, f"API request failed ({type(exc).__name__})") from exc
        except (TypeError, ValueError) as exc:
            raise InferenceError(self.name, "API response shape was invalid") from exc

        return RewriteResult(
            text=cleaned,
            provider=self.name,
            model=self.model,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
