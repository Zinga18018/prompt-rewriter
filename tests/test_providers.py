from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx

from prompt_rewriter.providers.groq_provider import GroqProvider
from prompt_rewriter.providers.ollama_provider import OllamaProvider

EXPECTED_OUTPUT = """Role:
Senior engineer

Context:
Desktop text needs rewriting.

Concrete Task:
Create a clear prompt.

Constraints:
Do not invent facts.

Output Format:
Use five plain-text sections."""

STRUCTURED_RESPONSE = json.dumps(
    {
        "role": "Senior engineer",
        "context": "Desktop text needs rewriting.",
        "concrete_task": "Create a clear prompt.",
        "constraints": "Do not invent facts.",
        "output_format": "Use five plain-text sections.",
    }
)


class FakeGroqCompletions:
    def __init__(self) -> None:
        self.request: dict[str, Any] | None = None

    def create(self, **request: Any) -> SimpleNamespace:
        self.request = request
        message = SimpleNamespace(content=STRUCTURED_RESPONSE)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeGroqClient:
    def __init__(self) -> None:
        self.completions = FakeGroqCompletions()
        self.chat = SimpleNamespace(completions=self.completions)


def test_groq_provider_builds_latency_bounded_structured_request() -> None:
    client = FakeGroqClient()
    provider = GroqProvider(
        api_key="not-used-by-fake",
        model="openai/gpt-oss-20b",
        timeout_seconds=4.0,
        max_tokens=650,
        max_output_chars=2_000,
        base_url="https://api.groq.com/openai/v1",
        client=client,
    )

    result = provider.rewrite("make this better")

    assert result.text == EXPECTED_OUTPUT
    assert result.provider == "groq"
    assert client.completions.request is not None
    assert client.completions.request["stream"] is False
    assert client.completions.request["max_completion_tokens"] == 650
    assert client.completions.request["reasoning_effort"] == "low"
    assert client.completions.request["response_format"]["type"] == "json_schema"
    assert client.completions.request["response_format"]["json_schema"]["strict"] is True
    assert client.completions.request["messages"][0]["role"] == "system"


def test_groq_legacy_model_override_uses_json_object_mode() -> None:
    client = FakeGroqClient()
    provider = GroqProvider(
        api_key="not-used-by-fake",
        model="llama-3.1-8b-instant",
        timeout_seconds=4.0,
        max_tokens=650,
        max_output_chars=2_000,
        base_url="https://api.groq.com/openai/v1",
        client=client,
    )

    provider.rewrite("make this better")

    assert client.completions.request is not None
    assert client.completions.request["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in client.completions.request


def test_ollama_provider_uses_nonstreaming_generate_contract() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"response": STRUCTURED_RESPONSE, "done": True})

    client = httpx.Client(
        base_url="http://localhost:11434",
        transport=httpx.MockTransport(handler),
    )
    provider = OllamaProvider(
        url="http://localhost:11434",
        model="llama3.2:3b",
        timeout_seconds=45.0,
        max_tokens=650,
        max_output_chars=2_000,
        keep_alive="10m",
        client=client,
    )

    result = provider.rewrite("make this better")

    assert result.text == EXPECTED_OUTPUT
    assert result.provider == "ollama"
    assert captured["model"] == "llama3.2:3b"
    assert captured["stream"] is False
    assert captured["format"]["additionalProperties"] is False
    assert captured["keep_alive"] == "10m"
    assert captured["options"] == {"temperature": 0.1, "num_predict": 650}
