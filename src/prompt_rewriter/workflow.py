from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from prompt_rewriter.config import Settings
from prompt_rewriter.providers.base import RewriteResult
from prompt_rewriter.windows_io import (
    ClipboardPort,
    ClipboardSnapshot,
    InputPort,
    WindowContext,
    WindowPort,
)

logger = logging.getLogger(__name__)


class RewriterPort(Protocol):
    def rewrite(self, rough_text: str) -> RewriteResult: ...


class WorkflowStatus(str, Enum):
    SUCCESS = "success"
    BUSY = "busy"
    NO_SELECTION = "no_selection"
    INVALID_SELECTION = "invalid_selection"
    UNSAFE_CLIPBOARD = "unsafe_clipboard"
    CLIPBOARD_CHANGED = "clipboard_changed"
    FOCUS_CHANGED = "focus_changed"
    USER_ACTIVITY = "user_activity"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WorkflowOutcome:
    status: WorkflowStatus
    message: str
    result: RewriteResult | None = None


class RewriteWorkflow:
    def __init__(
        self,
        *,
        settings: Settings,
        clipboard: ClipboardPort,
        input_driver: InputPort,
        windows: WindowPort,
        rewriter: RewriterPort,
    ) -> None:
        self._settings = settings
        self._clipboard = clipboard
        self._input = input_driver
        self._windows = windows
        self._rewriter = rewriter
        self._run_lock = threading.Lock()

    def capture_context(self) -> WindowContext:
        return self._windows.focus_context()

    def run(self, origin_context: WindowContext | None = None) -> WorkflowOutcome:
        if not self._run_lock.acquire(blocking=False):
            return WorkflowOutcome(WorkflowStatus.BUSY, "A rewrite is already running")
        try:
            return self._run_once(origin_context)
        finally:
            self._run_lock.release()

    def _restore(
        self,
        snapshot: ClipboardSnapshot,
        expected_sequence: int | None,
        *,
        after_failure: bool = False,
    ) -> bool:
        if expected_sequence is None:
            return False
        if not after_failure and not self._settings.restore_clipboard:
            return False
        try:
            return self._clipboard.restore_if_unchanged(snapshot, expected_sequence)
        except Exception as exc:
            logger.warning("Could not restore clipboard: %s", type(exc).__name__)
            return False

    def _read_text_if_owned(self, expected_sequence: int) -> tuple[bool, str]:
        """Read only when the clipboard sequence is stable across the entire read."""
        if self._clipboard.sequence() != expected_sequence:
            return False, ""
        text = self._clipboard.read_text()
        if self._clipboard.sequence() != expected_sequence:
            return False, ""
        return True, text

    def _run_once(self, origin_context: WindowContext | None) -> WorkflowOutcome:
        snapshot: ClipboardSnapshot | None = None
        owned_sequence: int | None = None
        paste_attempted = False
        try:
            origin_window = origin_context or self._windows.focus_context()
            if self._windows.focus_context() != origin_window:
                return WorkflowOutcome(
                    WorkflowStatus.FOCUS_CHANGED,
                    "Focus changed after the hotkey; nothing was copied",
                )
            snapshot = self._clipboard.snapshot()
            if not snapshot.restorable:
                return WorkflowOutcome(
                    WorkflowStatus.UNSAFE_CLIPBOARD,
                    "Clipboard contains non-text data that cannot be restored; nothing was copied",
                )
            if self._windows.focus_context() != origin_window:
                return WorkflowOutcome(
                    WorkflowStatus.FOCUS_CHANGED,
                    "Focus changed before copy; nothing was copied",
                )

            self._input.copy()
            copied_sequence = self._clipboard.wait_for_change(
                snapshot.sequence, self._settings.copy_timeout_seconds
            )
            if copied_sequence is None:
                return WorkflowOutcome(
                    WorkflowStatus.NO_SELECTION,
                    "No new selected text was copied",
                )
            owned_sequence = copied_sequence
            selection_is_owned, copied_text = self._read_text_if_owned(owned_sequence)
            if not selection_is_owned:
                return WorkflowOutcome(
                    WorkflowStatus.CLIPBOARD_CHANGED,
                    "Clipboard changed before selection could be read; nothing was sent",
                )
            selected_text = copied_text.strip()
            if not selected_text:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.INVALID_SELECTION,
                    "The selected text was empty",
                )
            if len(selected_text) > self._settings.max_input_chars:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.INVALID_SELECTION,
                    f"Selection exceeds {self._settings.max_input_chars} characters",
                )

            if self._windows.focus_context() != origin_window:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.FOCUS_CHANGED,
                    "Focus changed before inference; nothing was sent",
                )

            input_tick = self._windows.last_input_tick()
            result = self._rewriter.rewrite(selected_text)

            if self._windows.last_input_tick() != input_tick:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.USER_ACTIVITY,
                    "Keyboard or mouse activity occurred during inference; nothing was pasted",
                )

            # The clipboard is global. Abort if the user copied something during inference.
            if self._clipboard.sequence() != owned_sequence:
                return WorkflowOutcome(
                    WorkflowStatus.CLIPBOARD_CHANGED,
                    "Clipboard changed during inference; nothing was pasted",
                )
            if self._windows.focus_context() != origin_window:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.FOCUS_CHANGED,
                    "Active window changed during inference; nothing was pasted",
                )
            if self._clipboard.sequence() != owned_sequence:
                return WorkflowOutcome(
                    WorkflowStatus.CLIPBOARD_CHANGED,
                    "Clipboard changed before result write; nothing was pasted",
                )
            if self._windows.last_input_tick() != input_tick:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.USER_ACTIVITY,
                    "Keyboard or mouse activity occurred before result write; nothing was pasted",
                )

            owned_sequence = self._clipboard.write_text(result.text)

            # Check focus again after touching the clipboard to narrow the paste race window.
            if self._windows.focus_context() != origin_window:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.FOCUS_CHANGED,
                    "Active window changed before paste; nothing was pasted",
                )

            result_is_owned, clipboard_text = self._read_text_if_owned(owned_sequence)
            if not result_is_owned or clipboard_text != result.text:
                return WorkflowOutcome(
                    WorkflowStatus.CLIPBOARD_CHANGED,
                    "Clipboard changed before paste; nothing was pasted",
                )
            if self._clipboard.sequence() != owned_sequence:
                return WorkflowOutcome(
                    WorkflowStatus.CLIPBOARD_CHANGED,
                    "Clipboard changed at paste boundary; nothing was pasted",
                )
            if self._windows.focus_context() != origin_window:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.FOCUS_CHANGED,
                    "Active window changed before paste; nothing was pasted",
                )
            if self._windows.last_input_tick() != input_tick:
                self._restore(snapshot, owned_sequence, after_failure=True)
                return WorkflowOutcome(
                    WorkflowStatus.USER_ACTIVITY,
                    "Keyboard or mouse activity occurred at paste boundary; nothing was pasted",
                )

            paste_attempted = True
            self._input.paste()
            if self._settings.paste_settle_seconds:
                time.sleep(self._settings.paste_settle_seconds)
            self._restore(snapshot, owned_sequence)
            return WorkflowOutcome(
                WorkflowStatus.SUCCESS,
                f"Paste command sent using {result.provider}/{result.model}",
                result,
            )
        except Exception as exc:
            if snapshot is not None:
                self._restore(snapshot, owned_sequence, after_failure=True)
            logger.warning("Rewrite failed safely: %s", type(exc).__name__)
            paste_detail = "paste may have occurred" if paste_attempted else "nothing was pasted"
            return WorkflowOutcome(
                WorkflowStatus.FAILED,
                f"Rewrite failed safely ({type(exc).__name__}); {paste_detail}",
            )
