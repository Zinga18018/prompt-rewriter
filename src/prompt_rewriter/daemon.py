from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import keyboard

from prompt_rewriter.errors import DesktopIntegrationError
from prompt_rewriter.windows_io import WindowContext
from prompt_rewriter.workflow import RewriteWorkflow, WorkflowStatus

logger = logging.getLogger(__name__)


class HotkeyDaemon:
    def __init__(self, hotkey: str, workflow: RewriteWorkflow) -> None:
        self._hotkey = hotkey
        self._workflow = workflow
        self._dispatch_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="prompt-rewriter")
        self._stop_event = threading.Event()

    def _on_hotkey(self) -> None:
        # The keyboard hook callback must return immediately; inference runs off-hook.
        if not self._dispatch_lock.acquire(blocking=False):
            logger.info("Ignoring hotkey because a rewrite is already running")
            return
        try:
            origin_context = self._workflow.capture_context()
            self._executor.submit(self._execute, origin_context)
        except Exception as exc:
            self._dispatch_lock.release()
            logger.warning("Could not schedule rewrite: %s", type(exc).__name__)

    def _execute(self, origin_context: WindowContext) -> None:
        try:
            if not self._wait_for_hotkey_release():
                logger.warning("Hotkey remained pressed; rewrite cancelled")
                return
            outcome = self._workflow.run(origin_context)
            log = logger.info if outcome.status == WorkflowStatus.SUCCESS else logger.warning
            log("%s", outcome.message)
        finally:
            self._dispatch_lock.release()

    def _wait_for_hotkey_release(self, timeout_seconds: float = 1.5) -> bool:
        """Avoid turning synthetic Ctrl+C into Ctrl+Shift+C through modifier bleed."""
        try:
            parsed = keyboard.parse_hotkey(self._hotkey)
            scan_codes = {
                scan_code
                for step in parsed
                for key_alternatives in step
                for scan_code in key_alternatives
            }
        except (ValueError, TypeError):
            logger.warning("Could not parse hotkey for release detection")
            return False

        deadline = time.monotonic() + timeout_seconds
        while any(keyboard.is_pressed(scan_code) for scan_code in scan_codes):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return True

    def run_forever(self) -> None:
        try:
            registration = keyboard.add_hotkey(
                self._hotkey,
                self._on_hotkey,
                # Do not let the target app interpret the chord and alter the selection.
                suppress=True,
                trigger_on_release=False,
            )
        except (KeyError, ValueError, OSError, RuntimeError) as exc:
            raise DesktopIntegrationError(
                f"Could not register global hotkey {self._hotkey!r}"
            ) from exc
        logger.info("Prompt Rewriter is ready. Select text and press %s", self._hotkey)
        logger.info("Press Ctrl+C in this terminal to stop")
        try:
            while not self._stop_event.wait(0.5):
                pass
        except KeyboardInterrupt:
            logger.info("Stopping Prompt Rewriter")
        finally:
            try:
                keyboard.remove_hotkey(registration)
            except (KeyError, ValueError, OSError, RuntimeError):
                logger.warning("Could not remove the global hotkey cleanly")
            self._executor.shutdown(wait=True, cancel_futures=True)
