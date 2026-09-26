from __future__ import annotations

import ctypes
from ctypes import wintypes

from prompt_rewriter.errors import DesktopIntegrationError

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Local\PromptRewriter-8A98D879-672F-4F55-A7C9-95460AF5418A"


class WindowsSingleInstance:
    """Prevent two background listeners from racing over the same clipboard."""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        self._kernel32 = kernel32
        self._handle = kernel32.CreateMutexW(None, False, name)
        if not self._handle:
            raise DesktopIntegrationError("Could not create the single-instance guard")
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(self._handle)
            self._handle = None
            raise DesktopIntegrationError("Prompt Rewriter is already running")

    def close(self) -> None:
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> WindowsSingleInstance:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
