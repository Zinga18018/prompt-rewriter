from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Protocol

import keyboard
import pyperclip

from prompt_rewriter.errors import ClipboardError, ConfigurationError, DesktopIntegrationError

CF_UNICODETEXT = 13
_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_VK_CONTROL = 0x11
_NATIVE_CHORDS = {
    "ctrl+a": (_VK_CONTROL, ord("A")),
    "ctrl+c": (_VK_CONTROL, ord("C")),
    "ctrl+v": (_VK_CONTROL, ord("V")),
}


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


class _KeyboardInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class _MouseInput(ctypes.Structure):
    # INPUT contains a union. Even for keyboard events, the union must be large
    # enough for MOUSEINPUT or Windows rejects cbSize with ERROR_INVALID_PARAMETER.
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _InputValue(ctypes.Union):
    _fields_ = [
        ("ki", _KeyboardInput),
        ("mi", _MouseInput),
        ("hi", _HardwareInput),
    ]


class _Input(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", _InputValue)]


class ClipboardPort(Protocol):
    def snapshot(self) -> ClipboardSnapshot: ...

    def sequence(self) -> int: ...

    def wait_for_change(self, previous_sequence: int, timeout_seconds: float) -> int | None: ...

    def read_text(self) -> str: ...

    def write_text(self, text: str) -> int: ...

    def restore_if_unchanged(self, snapshot: ClipboardSnapshot, expected_sequence: int) -> bool: ...


class InputPort(Protocol):
    def copy(self) -> None: ...

    def select_all(self) -> None: ...

    def paste(self) -> None: ...


class SelectionPort(Protocol):
    def read_selected_text(self, max_chars: int) -> str | None: ...

    def read_focused_text(self, max_chars: int) -> str | None: ...

    def select_focused_text(self) -> bool: ...


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
    """Inject copy/paste with modern Win32 SendInput for broad app support."""

    def __init__(
        self,
        copy_chord: str,
        paste_chord: str,
        *,
        user32: object | None = None,
        key_hold_seconds: float = 0.03,
    ) -> None:
        self._copy_chord = copy_chord
        self._paste_chord = paste_chord
        self._user32 = user32 or ctypes.windll.user32
        self._key_hold_seconds = key_hold_seconds
        if user32 is None:
            self._user32.SendInput.argtypes = [
                wintypes.UINT,
                ctypes.POINTER(_Input),
                ctypes.c_int,
            ]
            self._user32.SendInput.restype = wintypes.UINT

    @staticmethod
    def _event(virtual_key: int, flags: int = 0) -> _Input:
        event = _Input()
        event.type = _INPUT_KEYBOARD
        event.ki.wVk = virtual_key
        event.ki.wScan = 0
        event.ki.dwFlags = flags
        event.ki.time = 0
        event.ki.dwExtraInfo = 0
        return event

    def _emit(self, virtual_keys: tuple[int, ...], *, key_up: bool) -> bool:
        ordered = tuple(reversed(virtual_keys)) if key_up else virtual_keys
        flags = _KEYEVENTF_KEYUP if key_up else 0
        events = (_Input * len(ordered))(
            *(self._event(virtual_key, flags) for virtual_key in ordered)
        )
        sent = int(self._user32.SendInput(len(events), events, ctypes.sizeof(_Input)))
        return sent == len(events)

    @staticmethod
    def _normalize_chord(chord: str) -> str:
        return "".join(chord.lower().split()).replace("control+", "ctrl+")

    def _send(self, chord: str) -> None:
        virtual_keys = _NATIVE_CHORDS.get(self._normalize_chord(chord))
        if virtual_keys is None:
            # Preserve configurable nonstandard chords, while defaults use the
            # more compatible SendInput path below.
            keyboard.press_and_release(chord)
            return

        pressed = self._emit(virtual_keys, key_up=False)
        try:
            if pressed:
                time.sleep(self._key_hold_seconds)
        finally:
            released = self._emit(virtual_keys, key_up=True)
        if not pressed or not released:
            raise DesktopIntegrationError("Windows SendInput could not inject the shortcut")

    def copy(self) -> None:
        self._send(self._copy_chord)

    def select_all(self) -> None:
        self._send("ctrl+a")

    def paste(self) -> None:
        self._send(self._paste_chord)


class WindowsUIASelection:
    """Read a focused selection when a custom editor refuses synthetic copy.

    UI Automation is a fallback only. The normal clipboard path remains first
    because it is faster and supports more traditional Win32 controls.
    """

    def __init__(self, *, auto_module: Any | None = None, max_ancestors: int = 8) -> None:
        self._auto_module = auto_module
        self._max_ancestors = max_ancestors

    def _auto(self) -> Any:
        if self._auto_module is None:
            import uiautomation as auto

            self._auto_module = auto
        return self._auto_module

    def read_selected_text(self, max_chars: int) -> str | None:
        auto = self._auto()
        try:
            with auto.UIAutomationInitializerInThread():
                control = auto.GetFocusedControl()
                for _ in range(self._max_ancestors):
                    if control is None:
                        break
                    if bool(control.IsPassword):
                        return None

                    pattern = control.GetPattern(auto.PatternId.TextPattern)
                    if pattern is not None:
                        parts: list[str] = []
                        remaining = max_chars
                        for text_range in pattern.GetSelection():
                            if remaining <= 0:
                                break
                            part = text_range.GetText(remaining)
                            parts.append(part)
                            remaining -= len(part)
                        selected = "\n".join(parts)
                        if selected:
                            return selected

                    control = control.GetParentControl()
        except Exception:
            # Accessibility support varies by application. Failure here simply
            # returns to the existing safe "no selection" outcome.
            return None
        return None

    def read_focused_text(self, max_chars: int) -> str | None:
        """Read the whole focused editable value when selection ranges are hidden."""
        auto = self._auto()
        try:
            with auto.UIAutomationInitializerInThread():
                control = auto.GetFocusedControl()
                for _ in range(self._max_ancestors):
                    if control is None:
                        break
                    if bool(control.IsPassword):
                        return None

                    pattern = control.GetPattern(auto.PatternId.ValuePattern)
                    if pattern is not None and not pattern.IsReadOnly:
                        value = pattern.Value
                        # Chromium may expose placeholder/name text as Value even
                        # when the composer is visually empty. Never send that UI
                        # label to a model as if the user had typed it.
                        name = str(getattr(control, "Name", "") or "").strip()
                        if value and (not name or value.strip() != name):
                            return value[:max_chars]

                    control = control.GetParentControl()
        except Exception:
            return None
        return None

    def select_focused_text(self) -> bool:
        """Select the focused editor's document before a normal clipboard paste."""
        auto = self._auto()
        try:
            with auto.UIAutomationInitializerInThread():
                control = auto.GetFocusedControl()
                for _ in range(self._max_ancestors):
                    if control is None:
                        break
                    if bool(control.IsPassword):
                        return False

                    pattern = control.GetPattern(auto.PatternId.TextPattern)
                    if pattern is not None:
                        return bool(pattern.DocumentRange.Select(waitTime=0))

                    control = control.GetParentControl()
        except Exception:
            return False
        return False

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
