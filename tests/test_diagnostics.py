from __future__ import annotations

import pytest

from prompt_rewriter.config import Settings
from prompt_rewriter.diagnostics import _check_gemini, _extract_model_ids


def test_extract_model_ids_accepts_expected_provider_shapes() -> None:
    assert _extract_model_ids(
        {"data": [{"id": "model-a"}]},
        collection_key="data",
        id_keys=("id",),
    ) == {"model-a"}
    assert _extract_model_ids(
        {"models": [{"name": "model-b"}]},
        collection_key="models",
        id_keys=("name", "model"),
    ) == {"model-b"}


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"data": "not-a-list"},
        {"data": ["not-an-object"]},
        {"data": [{"id": 123}]},
    ],
)
def test_extract_model_ids_rejects_malformed_api_payloads(payload: object) -> None:
    with pytest.raises(ValueError):
        _extract_model_ids(payload, collection_key="data", id_keys=("id",))


def test_check_gemini_uses_header_without_putting_key_in_url(monkeypatch) -> None:
    settings = Settings.from_env(
        {
            "PROMPT_REWRITER_PROVIDER_ORDER": "gemini",
            "GEMINI_API_KEY": "not-used-by-fake",
        }
    )
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return {
                "name": "models/gemini-3.5-flash-lite",
                "supportedGenerationMethods": ["generateContent"],
            }

    def fake_get(url, *, headers, timeout):
        captured.update(url=url, headers=headers, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr("prompt_rewriter.diagnostics.httpx.get", fake_get)

    assert _check_gemini(settings) == (
        True,
        "connected; model 'gemini-3.5-flash-lite' is available",
    )
    assert captured["headers"] == {"x-goog-api-key": "not-used-by-fake"}
    assert "not-used-by-fake" not in str(captured["url"])
