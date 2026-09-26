from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RewriteResult:
    text: str
    provider: str
    model: str
    latency_ms: int


class RewriteProvider(Protocol):
    name: str
    model: str

    def rewrite(self, rough_text: str) -> RewriteResult: ...

    def close(self) -> None: ...
