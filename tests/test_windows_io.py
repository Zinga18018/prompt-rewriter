from __future__ import annotations

import ctypes

import pytest

import prompt_rewriter.windows_io as windows_io
from prompt_rewriter.errors import DesktopIntegrationError
from prompt_rewriter.windows_io import WindowsKeyboard, WindowsUIASelection


class FakeUser32:
    def __init__(self, *, fail_call: int | None = None) -> None:
        self.calls: list[list[tuple[int, int]]] = []
        self._fail_call = fail_call

    def SendInput(self, count, events, _size):  # noqa: N802 - mirrors the Win32 API
        self.calls.append(
            [(int(events[index].ki.wVk), int(events[index].ki.dwFlags)) for index in range(count)]
        )
        if self._fail_call == len(self.calls):
            return 0
        return count


class FakeInitializer:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class FakeTextRange:
    def __init__(self, text: str) -> None:
        self.text = text
        self.select_calls = 0

    def GetText(self, max_chars: int):  # noqa: N802 - mirrors the UIA API
        return self.text[:max_chars]

    def Select(self, waitTime: float = 0):  # noqa: N802 - mirrors the UIA API
        del waitTime
        self.select_calls += 1
        return True


class FakeTextPattern:
    def __init__(self, *parts: str) -> None:
        self.parts = parts

    def GetSelection(self):  # noqa: N802 - mirrors the UIA API
        return [FakeTextRange(part) for part in self.parts]

    @property
    def DocumentRange(self):  # noqa: N802 - mirrors the UIA API
        return FakeTextRange("".join(self.parts))


class FakeValuePattern:
    def __init__(self, value: str, *, read_only: bool = False) -> None:
        self.Value = value
        self.IsReadOnly = read_only
        self.values_set: list[str] = []

    def SetValue(self, value: str, waitTime: float = 0):  # noqa: N802 - mirrors UIA
        del waitTime
        self.values_set.append(value)
        self.Value = value
        return True


class FakeControl:
    def __init__(
        self,
        *,
        pattern=None,
        value_pattern=None,
        parent=None,
        is_password: bool = False,
        name: str = "",
    ) -> None:
        self.pattern = pattern
        self.value_pattern = value_pattern
        self.parent = parent
        self.IsPassword = is_password
        self.Name = name

    def GetPattern(self, pattern_id):  # noqa: N802 - mirrors the UIA API
        if pattern_id == FakeAutomation.PatternId.ValuePattern:
            return self.value_pattern
        return self.pattern

    def GetParentControl(self):  # noqa: N802 - mirrors the UIA API
        return self.parent


class FakeAutomation:
    class PatternId:
        TextPattern = 10014
        ValuePattern = 10002

    UIAutomationInitializerInThread = FakeInitializer

    def __init__(self, focused_control) -> None:
        self.focused_control = focused_control

    def GetFocusedControl(self):  # noqa: N802 - mirrors the UIA API
        return self.focused_control


def test_win32_input_structure_has_native_windows_size() -> None:
    expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28

    assert ctypes.sizeof(windows_io._Input) == expected_size


def test_windows_keyboard_uses_sendinput_for_copy_select_all_and_paste(monkeypatch) -> None:
    fake = FakeUser32()
    monkeypatch.setattr(windows_io.time, "sleep", lambda _seconds: None)
    keyboard = WindowsKeyboard("ctrl+c", "ctrl+v", user32=fake)

    keyboard.copy()
    keyboard.select_all()
    keyboard.paste()

    assert fake.calls == [
        [(0x11, 0), (ord("C"), 0)],
        [(ord("C"), 2), (0x11, 2)],
        [(0x11, 0), (ord("A"), 0)],
        [(ord("A"), 2), (0x11, 2)],
        [(0x11, 0), (ord("V"), 0)],
        [(ord("V"), 2), (0x11, 2)],
    ]


def test_windows_keyboard_releases_keys_when_sendinput_press_fails(monkeypatch) -> None:
    fake = FakeUser32(fail_call=1)
    monkeypatch.setattr(windows_io.time, "sleep", lambda _seconds: None)
    keyboard = WindowsKeyboard("ctrl+c", "ctrl+v", user32=fake)

    with pytest.raises(DesktopIntegrationError, match="SendInput"):
        keyboard.copy()

    assert fake.calls[-1] == [(ord("C"), 2), (0x11, 2)]


def test_windows_keyboard_keeps_keyboard_fallback_for_custom_chord(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(windows_io.keyboard, "press_and_release", calls.append)
    keyboard = WindowsKeyboard("alt+insert", "shift+insert", user32=FakeUser32())

    keyboard.copy()
    keyboard.paste()

    assert calls == ["alt+insert", "shift+insert"]


def test_uia_selection_reads_selected_text_from_parent_pattern() -> None:
    parent = FakeControl(pattern=FakeTextPattern("selected", "text"))
    child = FakeControl(parent=parent)
    reader = WindowsUIASelection(auto_module=FakeAutomation(child))

    selected = reader.read_selected_text(100)

    assert selected == "selected\ntext"


def test_uia_selection_refuses_password_control() -> None:
    password = FakeControl(pattern=FakeTextPattern("secret"), is_password=True)
    reader = WindowsUIASelection(auto_module=FakeAutomation(password))

    assert reader.read_selected_text(100) is None


def test_uia_selection_reads_whole_editable_value() -> None:
    value_pattern = FakeValuePattern("I want to create a neat website")
    control = FakeControl(value_pattern=value_pattern)
    reader = WindowsUIASelection(auto_module=FakeAutomation(control))

    captured = reader.read_focused_text(100)

    assert captured == "I want to create a neat website"


def test_uia_selection_rejects_chromium_placeholder_value() -> None:
    value_pattern = FakeValuePattern("\nWork with ChatGPT")
    control = FakeControl(value_pattern=value_pattern, name="Work with ChatGPT")
    reader = WindowsUIASelection(auto_module=FakeAutomation(control))

    assert reader.read_focused_text(100) is None


def test_uia_selection_selects_focused_document_range() -> None:
    text_pattern = FakeTextPattern("whole field")
    control = FakeControl(pattern=text_pattern)
    reader = WindowsUIASelection(auto_module=FakeAutomation(control))

    assert reader.select_focused_text() is True
