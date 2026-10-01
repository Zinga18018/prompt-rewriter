from __future__ import annotations

import time
from typing import Any

from groq import Groq, GroqError

from prompt_rewriter.errors import InferenceError, OutputValidationError
from prompt_rewriter.prompts import (
    PROMPT_REWRITE_SCHEMA,
    SYSTEM_PROMPT,
    build_user_message,
    clean_and_validate_output,
)
from prompt_rewriter.providers.base import RewriteResult


class GroqProvider:
    name = "groq"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        max_output_chars: int,
        base_url: str,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self._max_tokens = max_tokens
        self._max_output_chars = max_output_chars
        self._client = client or Groq(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=0,
        )

    def rewrite(self, rough_text: str) -> RewriteResult:
        started = time.perf_counter()
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(rough_text)},
            ],
            "temperature": 0,
            "max_completion_tokens": self._max_tokens,
            "stream": False,
        }
        if self.model.startswith("openai/gpt-oss-"):
            request["reasoning_effort"] = "low"
            request["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "prompt_rewrite",
                    "strict": True,
                    "schema": PROMPT_REWRITE_SCHEMA,
                },
            }
        else:
            # Legacy/enterprise overrides may only support JSON Object Mode.
            request["response_format"] = {"type": "json_object"}

        try:
            completion = self._client.chat.completions.create(**request)
            raw_output = completion.choices[0].message.content
            cleaned = clean_and_validate_output(raw_output, self._max_output_chars)
        except OutputValidationError as exc:
            raise InferenceError(self.name, f"invalid model output ({exc})") from exc
        except GroqError as exc:
            status = getattr(exc, "status_code", None)
            detail = f"API request failed ({type(exc).__name__}"
            if status is not None:
                detail += f", HTTP {status}"
            detail += ")"
            raise InferenceError(self.name, detail) from exc
        except (AttributeError, IndexError, TypeError) as exc:
            raise InferenceError(self.name, "API response shape was invalid") from exc

        return RewriteResult(
            text=cleaned,
            provider=self.name,
            model=self.model,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
