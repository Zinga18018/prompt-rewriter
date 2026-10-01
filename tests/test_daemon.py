from __future__ import annotations

import prompt_rewriter.daemon as daemon_module
from prompt_rewriter.daemon import HotkeyDaemon


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def daemon_without_executor(hotkey: str = "f8") -> HotkeyDaemon:
    daemon = object.__new__(HotkeyDaemon)
    daemon._hotkey = hotkey
    return daemon


def install_fake_keyboard(monkeypatch, states: list[bool]) -> None:
    remaining = iter(states)
    monkeypatch.setattr(daemon_module.keyboard, "parse_hotkey", lambda _hotkey: (((42,),),))
    monkeypatch.setattr(
        daemon_module.keyboard,
        "is_pressed",
        lambda _scan_code: next(remaining, states[-1]),
    )


def install_fake_clock(monkeypatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(daemon_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(daemon_module.time, "sleep", clock.sleep)
    return clock


def test_hotkey_release_must_remain_stable_before_work_starts(monkeypatch) -> None:
    clock = install_fake_clock(monkeypatch)
    install_fake_keyboard(monkeypatch, [False])

    released = daemon_without_executor()._wait_for_hotkey_release(
        timeout_seconds=0.2,
        stable_release_seconds=0.05,
        poll_seconds=0.01,
    )

    assert released is True
    assert clock.now >= 0.05


def test_hotkey_pressed_again_resets_release_interval(monkeypatch) -> None:
    clock = install_fake_clock(monkeypatch)
    install_fake_keyboard(monkeypatch, [False, False, True, False])

    released = daemon_without_executor()._wait_for_hotkey_release(
        timeout_seconds=0.2,
        stable_release_seconds=0.05,
        poll_seconds=0.01,
    )

    assert released is True
    assert clock.now >= 0.08


def test_hotkey_release_times_out_while_key_remains_pressed(monkeypatch) -> None:
    clock = install_fake_clock(monkeypatch)
    install_fake_keyboard(monkeypatch, [True])

    released = daemon_without_executor()._wait_for_hotkey_release(
        timeout_seconds=0.05,
        stable_release_seconds=0.02,
        poll_seconds=0.01,
    )

    assert released is False
    assert clock.now >= 0.05


def test_daemon_registers_hotkey_on_release(monkeypatch) -> None:
    registrations: list[tuple[str, dict[str, bool]]] = []
    removals: list[object] = []

    def add_hotkey(hotkey, _callback, **options):
        registrations.append((hotkey, options))
        return "registration"

    monkeypatch.setattr(daemon_module.keyboard, "add_hotkey", add_hotkey)
    monkeypatch.setattr(daemon_module.keyboard, "remove_hotkey", removals.append)
    daemon = HotkeyDaemon("ctrl+shift+space", object())
    daemon._stop_event.set()

    daemon.run_forever()

    assert registrations == [
        ("ctrl+shift+space", {"suppress": True, "trigger_on_release": True})
    ]
    assert removals == ["registration"]
