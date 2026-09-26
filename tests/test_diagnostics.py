from __future__ import annotations

import pytest

from prompt_rewriter.diagnostics import _extract_model_ids


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
