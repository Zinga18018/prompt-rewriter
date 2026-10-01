from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import suppress

import pytest

from prompt_rewriter.config import Settings
from prompt_rewriter.providers.base import RewriteResult
from prompt_rewriter.windows_io import ClipboardSnapshot, WindowContext


@pytest.fixture
def settings() -> Settings:
    """Fast, deterministic settings for workflow unit tests."""
    return Settings.from_env(
        {
            "PROMPT_REWRITER_PROVIDER_ORDER": "groq,ollama",
            "PROMPT_REWRITER_COPY_TIMEOUT_SECONDS": "0.01",
            "PROMPT_REWRITER_PASTE_SETTLE_SECONDS": "0",
            "PROMPT_REWRITER_RESTORE_CLIPBOARD": "true",
        }
    )


class FakeClipboard:
    """In-memory clipboard with Windows-like sequence-number behavior."""

    def __init__(self, *, original_text: str = "before", selected_text: str = "rough idea"):
        self.text = original_text
        self.selected_text = selected_text
        self._sequence = 10
        self.restore_calls: list[tuple[ClipboardSnapshot, int]] = []

    def snapshot(self) -> ClipboardSnapshot:
        return ClipboardSnapshot(text=self.text, sequence=self._sequence)

    def sequence(self) -> int:
        return self._sequence

    def wait_for_change(self, previous_sequence: int, timeout_seconds: float) -> int | None:
        del timeout_seconds
        return self._sequence if self._sequence != previous_sequence else None

    def read_text(self) -> str:
        return self.text

    def write_text(self, text: str) -> int:
        self.text = text
        self._sequence += 1
        return self._sequence

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool:
        self.restore_calls.append((snapshot, expected_sequence))
        if self._sequence != expected_sequence:
            return False
        self.write_text(snapshot.text or "")
        return True

    def copy_selection(self) -> None:
        self.write_text(self.selected_text)

    def external_copy(self, text: str) -> None:
        self.write_text(text)


class FakeInput:
    def __init__(self, clipboard: FakeClipboard):
        self._clipboard = clipboard
        self.copy_calls = 0
        self.select_all_calls = 0
        self.paste_calls = 0

    def copy(self) -> None:
        self.copy_calls += 1
        self._clipboard.copy_selection()

    def select_all(self) -> None:
        self.select_all_calls += 1

    def paste(self) -> None:
        self.paste_calls += 1


class FakeWindows:
    def __init__(
        self,
        handles: Iterable[int] = (100,),
        input_ticks: Iterable[int] = (1,),
    ):
        self._handles = iter(handles)
        self._last_handle: int | None = None
        self._input_ticks = iter(input_ticks)
        self._last_input_tick: int | None = None

    def focus_context(self) -> WindowContext:
        with suppress(StopIteration):
            self._last_handle = next(self._handles)
        if self._last_handle is None:
            raise AssertionError("FakeWindows requires at least one handle")
        return WindowContext(
            foreground=self._last_handle,
            active=self._last_handle,
            focused=self._last_handle,
            caret=self._last_handle,
            caret_rect=(0, 0, 0, 0),
        )

    def last_input_tick(self) -> int:
        with suppress(StopIteration):
            self._last_input_tick = next(self._input_ticks)
        if self._last_input_tick is None:
            raise AssertionError("FakeWindows requires at least one input tick")
        return self._last_input_tick


class FakeRewriter:
    def __init__(
        self,
        *,
        result: RewriteResult | None = None,
        error: Exception | None = None,
        before_return: Callable[[], None] | None = None,
    ):
        self.result = result or RewriteResult(
            text=(
                "Role:\nExpert\n"
                "Context:\nA rough request\n"
                "Concrete Task:\nRewrite it\n"
                "Constraints:\nBe concise\n"
                "Output Format:\nPlain text"
            ),
            provider="fake",
            model="fake-model",
            latency_ms=1,
        )
        self.error = error
        self.before_return = before_return
        self.calls: list[str] = []

    def rewrite(self, rough_text: str) -> RewriteResult:
        self.calls.append(rough_text)
        if self.before_return:
            self.before_return()
        if self.error:
            raise self.error
        return self.result
