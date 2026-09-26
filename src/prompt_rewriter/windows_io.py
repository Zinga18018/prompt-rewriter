from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Protocol

import keyboard
import pyperclip

from prompt_rewriter.errors import ClipboardError, ConfigurationError

CF_UNICODETEXT = 13


@dataclass(frozen=True, slots=True)
class ClipboardSnapshot:
    text: str | None
    sequence: int
    restorable: bool = True


@dataclass(frozen=True, slots=True)
class WindowContext:
    foreground: int
    active: int
    focused: int
    caret: int
    caret_rect: tuple[int, int, int, int]


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class ClipboardPort(Protocol):
    def snapshot(self) -> ClipboardSnapshot: ...

    def sequence(self) -> int: ...

    def wait_for_change(self, previous_sequence: int, timeout_seconds: float) -> int | None: ...

    def read_text(self) -> str: ...

    def write_text(self, text: str) -> int: ...

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool: ...


class InputPort(Protocol):
    def copy(self) -> None: ...

    def paste(self) -> None: ...


class WindowPort(Protocol):
    def focus_context(self) -> WindowContext: ...

    def last_input_tick(self) -> int: ...


class WindowsClipboard:
    """Plain-text clipboard access with retry and sequence-based race protection."""

    def __init__(self, retry_seconds: float = 0.5, retry_interval: float = 0.02) -> None:
        if sys.platform != "win32":
            raise ConfigurationError(
                "The basic global-hotkey build currently supports Windows only"
            )
        self._user32 = ctypes.windll.user32
        self._retry_seconds = retry_seconds
        self._retry_interval = retry_interval

    def sequence(self) -> int:
        return int(self._user32.GetClipboardSequenceNumber())

    def _has_unicode_text(self) -> bool:
        return bool(self._user32.IsClipboardFormatAvailable(CF_UNICODETEXT))

    def snapshot(self) -> ClipboardSnapshot:
        deadline = time.monotonic() + self._retry_seconds
        while True:
            before = self.sequence()
            has_text = self._has_unicode_text()
            format_count = int(self._user32.CountClipboardFormats())
            text = self.read_text() if has_text else None
            after = self.sequence()
            if before == after:
                return ClipboardSnapshot(
                    text=text,
                    sequence=after,
                    # pyperclip cannot restore an image/file-only clipboard.
                    restorable=has_text or format_count == 0,
                )
            if time.monotonic() >= deadline:
                raise ClipboardError("clipboard kept changing while it was being captured")
            time.sleep(self._retry_interval)

    def read_text(self) -> str:
        deadline = time.monotonic() + self._retry_seconds
        last_error: Exception | None = None
        while True:
            try:
                value = pyperclip.paste()
                return value if isinstance(value, str) else str(value)
            except (pyperclip.PyperclipException, OSError) as exc:
                last_error = exc
                if time.monotonic() >= deadline:
                    raise ClipboardError("could not read the clipboard") from last_error
                time.sleep(self._retry_interval)

    def write_text(self, text: str) -> int:
        deadline = time.monotonic() + self._retry_seconds
        last_error: Exception | None = None
        while True:
            try:
                pyperclip.copy(text)
                return self.sequence()
            except (pyperclip.PyperclipException, OSError) as exc:
                last_error = exc
                if time.monotonic() >= deadline:
                    raise ClipboardError("could not write to the clipboard") from last_error
                time.sleep(self._retry_interval)

    def wait_for_change(self, previous_sequence: int, timeout_seconds: float) -> int | None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            current = self.sequence()
            if current != previous_sequence:
                return current
            time.sleep(self._retry_interval)
        return None

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool:
        # Never overwrite a clipboard value copied by the user while inference was running.
        if self.sequence() != expected_sequence:
            return False
        self.write_text(snapshot.text or "")
        return True


class WindowsKeyboard:
    def __init__(self, copy_chord: str, paste_chord: str) -> None:
        self._copy_chord = copy_chord
        self._paste_chord = paste_chord

    def copy(self) -> None:
        keyboard.press_and_release(self._copy_chord)

    def paste(self) -> None:
        keyboard.press_and_release(self._paste_chord)


def validate_keyboard_chord(name: str, chord: str) -> None:
    try:
        parsed = keyboard.parse_hotkey(chord)
    except (KeyError, ValueError, TypeError) as exc:
        raise ConfigurationError(f"{name} is not a valid keyboard chord: {chord!r}") from exc
    if not parsed:
        raise ConfigurationError(f"{name} is not a valid keyboard chord: {chord!r}")


class WindowsWindowTracker:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise ConfigurationError(
                "The basic global-hotkey build currently supports Windows only"
            )
        self._user32 = ctypes.windll.user32
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self._user32.GetGUIThreadInfo.argtypes = [
            wintypes.DWORD,
            ctypes.POINTER(_GuiThreadInfo),
        ]
        self._user32.GetGUIThreadInfo.restype = wintypes.BOOL
        self._user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
        self._user32.GetLastInputInfo.restype = wintypes.BOOL

    def focus_context(self) -> WindowContext:
        foreground = int(self._user32.GetForegroundWindow() or 0)
        thread_id = self._user32.GetWindowThreadProcessId(foreground, None)
        info = _GuiThreadInfo(cbSize=ctypes.sizeof(_GuiThreadInfo))
        if not thread_id or not self._user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            return WindowContext(foreground, 0, 0, 0, (0, 0, 0, 0))
        return WindowContext(
            foreground=foreground,
            active=int(info.hwndActive or 0),
            focused=int(info.hwndFocus or 0),
            caret=int(info.hwndCaret or 0),
            caret_rect=(
                info.rcCaret.left,
                info.rcCaret.top,
                info.rcCaret.right,
                info.rcCaret.bottom,
            ),
        )

    def last_input_tick(self) -> int:
        info = _LastInputInfo(cbSize=ctypes.sizeof(_LastInputInfo))
        if not self._user32.GetLastInputInfo(ctypes.byref(info)):
            raise OSError("GetLastInputInfo failed")
        return int(info.dwTime)
