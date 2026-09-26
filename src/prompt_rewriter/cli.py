from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from prompt_rewriter import __version__
from prompt_rewriter.config import Settings
from prompt_rewriter.daemon import HotkeyDaemon
from prompt_rewriter.diagnostics import run_diagnostics
from prompt_rewriter.errors import PromptRewriterError
from prompt_rewriter.factory import build_router
from prompt_rewriter.logging_config import configure_logging
from prompt_rewriter.single_instance import WindowsSingleInstance
from prompt_rewriter.windows_io import (
    WindowsClipboard,
    WindowsKeyboard,
    WindowsWindowTracker,
    validate_keyboard_chord,
)
from prompt_rewriter.workflow import RewriteWorkflow

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt-rewriter",
        description="Rewrite selected text into a structured AI prompt.",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--rewrite",
        metavar="TEXT",
        help="rewrite TEXT directly without using the clipboard or global hotkey",
    )
    actions.add_argument(
        "--doctor",
        action="store_true",
        help="check provider configuration and connectivity",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    router = None
    try:
        settings = Settings.from_env()
        configure_logging(settings.log_level)
        if args.doctor:
            return run_diagnostics(settings)

        router = build_router(settings)
        if args.rewrite is not None:
            rough_text = args.rewrite.strip()
            if not rough_text:
                raise PromptRewriterError("--rewrite text cannot be empty")
            if len(rough_text) > settings.max_input_chars:
                raise PromptRewriterError(
                    f"--rewrite text exceeds {settings.max_input_chars} characters"
                )
            result = router.rewrite(rough_text)
            print(result.text)
            return 0

        if sys.platform != "win32":
            raise PromptRewriterError("The global-hotkey mode currently supports Windows only")
        validate_keyboard_chord("PROMPT_REWRITER_HOTKEY", settings.hotkey)
        validate_keyboard_chord("PROMPT_REWRITER_COPY_CHORD", settings.copy_chord)
        validate_keyboard_chord("PROMPT_REWRITER_PASTE_CHORD", settings.paste_chord)
        workflow = RewriteWorkflow(
            settings=settings,
            clipboard=WindowsClipboard(),
            input_driver=WindowsKeyboard(settings.copy_chord, settings.paste_chord),
            windows=WindowsWindowTracker(),
            rewriter=router,
        )
        with WindowsSingleInstance():
            HotkeyDaemon(settings.hotkey, workflow).run_forever()
        return 0
    except PromptRewriterError as exc:
        logger.error("%s", exc)
        return 1
    finally:
        if router is not None:
            router.close()


if __name__ == "__main__":
    raise SystemExit(main())
