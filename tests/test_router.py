from __future__ import annotations

from dataclasses import dataclass

import pytest

from prompt_rewriter.errors import AllProvidersFailed, InferenceError
from prompt_rewriter.providers.base import RewriteResult
from prompt_rewriter.providers.router import FallbackRouter


@dataclass
class FakeProvider:
    name: str
    model: str
    result: RewriteResult | None = None
    error: Exception | None = None
    rewrite_calls: int = 0
    close_calls: int = 0

    def rewrite(self, rough_text: str) -> RewriteResult:
        assert rough_text == "rough"
        self.rewrite_calls += 1
        if self.error:
            raise self.error
        if self.result is None:
            raise AssertionError("FakeProvider requires a result or error")
        return self.result

    def close(self) -> None:
        self.close_calls += 1


def test_router_falls_back_after_expected_provider_failure() -> None:
    first = FakeProvider(
        name="groq",
        model="cloud-model",
        error=InferenceError("groq", "timed out"),
    )
    expected = RewriteResult("rewritten", "ollama", "local-model", 25)
    second = FakeProvider(name="ollama", model="local-model", result=expected)

    router = FallbackRouter((first, second))

    assert router.provider_names == ("groq", "ollama")
    assert router.rewrite("rough") == expected
    assert first.rewrite_calls == 1
    assert second.rewrite_calls == 1


def test_router_converts_unexpected_error_and_raises_when_all_providers_fail() -> None:
    first = FakeProvider(name="groq", model="cloud-model", error=RuntimeError("secret"))
    second_error = InferenceError("ollama", "service unavailable")
    second = FakeProvider(name="ollama", model="local-model", error=second_error)

    with pytest.raises(AllProvidersFailed) as raised:
        FallbackRouter((first, second)).rewrite("rough")

    failures = raised.value.failures
    assert len(failures) == 2
    assert failures[0].provider == "groq"
    assert failures[0].detail == "unexpected provider error (RuntimeError)"
    assert failures[1] is second_error
    assert "secret" not in str(raised.value)


def test_router_requires_at_least_one_provider() -> None:
    with pytest.raises(ValueError, match="at least one provider"):
        FallbackRouter(())
