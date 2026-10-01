from __future__ import annotations

import time
from typing import Any

import httpx

from prompt_rewriter.errors import InferenceError, OutputValidationError
from prompt_rewriter.prompts import (
    PROMPT_REWRITE_SCHEMA,
    SYSTEM_PROMPT,
    build_user_message,
    clean_and_validate_output,
)
from prompt_rewriter.providers.base import RewriteResult


class GeminiProvider:
    """Low-latency, stateless Gemini Interactions client with structured output."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        max_output_chars: int,
        base_url: str,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._max_output_chars = max_output_chars
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(2.0, timeout_seconds),
            pool=min(2.0, timeout_seconds),
        )
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout)
        self._owns_client = client is None

    @staticmethod
    def _response_text(data: Any) -> str:
        if not isinstance(data, dict):
            raise ValueError("response is not an object")
        if data.get("error") is not None:
            raise InferenceError("gemini", "interaction returned a provider error")
        status = data.get("status")
        if status != "completed":
            safe_status = status if isinstance(status, str) else "unknown"
            raise InferenceError("gemini", f"interaction did not complete ({safe_status})")
        steps = data.get("steps")
        if not isinstance(steps, list):
            raise ValueError("interaction steps are not a list")
        for step in steps:
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            content = step.get("content")
            if not isinstance(content, list):
                continue
            text_parts = [
                item["text"]
                for item in content
                if isinstance(item, dict)
                and item.get("type") == "text"
                and isinstance(item.get("text"), str)
            ]
            if text_parts:
                return "".join(text_parts)
        raise ValueError("interaction has no model text output")

    def rewrite(self, rough_text: str) -> RewriteResult:
        started = time.perf_counter()
        payload = {
            "model": self.model,
            "input": build_user_message(rough_text),
            "system_instruction": SYSTEM_PROMPT,
            # Interactions are stored by default unless this is explicitly false.
            "store": False,
            "generation_config": {
                "max_output_tokens": self._max_tokens,
                "thinking_level": "minimal",
            },
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": PROMPT_REWRITE_SCHEMA,
            },
        }
        try:
            response = self._client.post(
                "/interactions",
                headers={"x-goog-api-key": self._api_key},
                json=payload,
            )
            response.raise_for_status()
            raw_output = self._response_text(response.json())
            cleaned = clean_and_validate_output(raw_output, self._max_output_chars)
        except OutputValidationError as exc:
            raise InferenceError(self.name, f"invalid model output ({exc})") from exc
        except httpx.TimeoutException as exc:
            raise InferenceError(self.name, "request timed out") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                detail = f"authentication/API access failed (HTTP {status})"
            elif status == 429:
                detail = "rate limit exceeded (HTTP 429)"
            else:
                detail = f"API request failed (HTTP {status})"
            raise InferenceError(self.name, detail) from exc
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
