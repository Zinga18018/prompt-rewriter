from __future__ import annotations

from conftest import FakeClipboard, FakeInput, FakeRewriter, FakeWindows

from prompt_rewriter.config import Settings
from prompt_rewriter.errors import InferenceError
from prompt_rewriter.windows_io import ClipboardSnapshot
from prompt_rewriter.workflow import RewriteWorkflow, WorkflowStatus


def build_workflow(
    *,
    settings: Settings,
    clipboard: FakeClipboard,
    input_driver: FakeInput,
    windows: FakeWindows,
    rewriter: FakeRewriter,
    selection_reader=None,
) -> RewriteWorkflow:
    return RewriteWorkflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=windows,
        rewriter=rewriter,
        selection_reader=selection_reader,
    )


class NoCopyInput(FakeInput):
    def copy(self) -> None:
        self.copy_calls += 1


class FakeSelectionReader:
    def __init__(
        self,
        text: str | None,
        before_return=None,
        *,
        focused_text: str | None = None,
        select_succeeds: bool = False,
    ) -> None:
        self.text = text
        self.before_return = before_return
        self.focused_text = focused_text
        self.select_succeeds = select_succeeds
        self.max_chars: list[int] = []
        self.select_calls = 0

    def read_selected_text(self, max_chars: int) -> str | None:
        self.max_chars.append(max_chars)
        if self.before_return:
            self.before_return()
        return self.text

    def read_focused_text(self, max_chars: int) -> str | None:
        self.max_chars.append(max_chars)
        return self.focused_text

    def select_focused_text(self) -> bool:
        self.select_calls += 1
        return self.select_succeeds

def test_workflow_rewrites_pastes_and_restores_clipboard(settings: Settings) -> None:
    clipboard = FakeClipboard(original_text="keep me", selected_text="  rough request  ")
    input_driver = FakeInput(clipboard)
    rewriter = FakeRewriter()
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.SUCCESS
    assert outcome.result is rewriter.result
    assert rewriter.calls == ["rough request"]
    assert input_driver.copy_calls == 1
    assert input_driver.paste_calls == 1
    assert clipboard.text == "keep me"
    assert len(clipboard.restore_calls) == 1


def test_workflow_uses_accessibility_selection_when_copy_is_ignored(
    settings: Settings,
) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = NoCopyInput(clipboard)
    selection_reader = FakeSelectionReader("  rough request from accessibility  ")
    rewriter = FakeRewriter()
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
        selection_reader=selection_reader,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.SUCCESS
    assert rewriter.calls == ["rough request from accessibility"]
    assert selection_reader.max_chars == [settings.max_input_chars + 1]
    assert input_driver.paste_calls == 1
    assert clipboard.text == "keep me"


def test_workflow_reports_no_selection_when_accessibility_has_none(
    settings: Settings,
) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = NoCopyInput(clipboard)
    rewriter = FakeRewriter()
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
        selection_reader=FakeSelectionReader(None),
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.NO_SELECTION
    assert rewriter.calls == []
    assert input_driver.paste_calls == 0
    assert clipboard.text == "keep me"


def test_workflow_rewrites_whole_focused_field_when_selection_is_hidden(
    settings: Settings,
) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = NoCopyInput(clipboard)
    rewriter = FakeRewriter()
    selection_reader = FakeSelectionReader(
        None,
        focused_text="I want to create a neat website",
    )
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
        selection_reader=selection_reader,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.SUCCESS
    assert rewriter.calls == ["I want to create a neat website"]
    assert selection_reader.select_calls == 1
    assert input_driver.select_all_calls == 1
    assert input_driver.paste_calls == 1
    assert clipboard.text == "keep me"


def test_workflow_uses_accessibility_document_selection_for_whole_field(
    settings: Settings,
) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = NoCopyInput(clipboard)
    rewriter = FakeRewriter()
    selection_reader = FakeSelectionReader(
        None,
        focused_text="I want to create a neat website",
        select_succeeds=True,
    )
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
        selection_reader=selection_reader,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.SUCCESS
    assert selection_reader.select_calls == 1
    assert input_driver.select_all_calls == 0
    assert input_driver.paste_calls == 1


def test_workflow_does_not_rewrite_its_own_structured_output(settings: Settings) -> None:
    clipboard = FakeClipboard(
        original_text="keep me",
        selected_text=(
            "Role:\nExpert\n\nContext:\nKnown context\n\nConcrete Task:\nDo the task\n\n"
            "Constraints:\nUse supplied facts\n\nOutput Format:\nReturn a short answer"
        ),
    )
    input_driver = FakeInput(clipboard)
    rewriter = FakeRewriter()
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.ALREADY_STRUCTURED
    assert rewriter.calls == []
    assert input_driver.paste_calls == 0
    assert clipboard.text == "keep me"


def test_workflow_preserves_clipboard_change_during_accessibility_fallback(
    settings: Settings,
) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = NoCopyInput(clipboard)
    rewriter = FakeRewriter()
    selection_reader = FakeSelectionReader(
        "rough request",
        before_return=lambda: clipboard.external_copy("new user copy"),
    )
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
        selection_reader=selection_reader,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.CLIPBOARD_CHANGED
    assert rewriter.calls == []
    assert input_driver.paste_calls == 0
    assert clipboard.text == "new user copy"


def test_workflow_restores_clipboard_when_inference_fails(settings: Settings) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = FakeInput(clipboard)
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=FakeRewriter(error=InferenceError("fake", "timed out")),
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.FAILED
    assert outcome.result is None
    assert input_driver.paste_calls == 0
    assert clipboard.text == "keep me"
    assert len(clipboard.restore_calls) == 1


def test_workflow_refuses_non_text_clipboard_before_copy(settings: Settings) -> None:
    class NonTextClipboard(FakeClipboard):
        def snapshot(self) -> ClipboardSnapshot:
            return ClipboardSnapshot(text=None, sequence=self.sequence(), restorable=False)

    clipboard = NonTextClipboard()
    input_driver = FakeInput(clipboard)
    rewriter = FakeRewriter()
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.UNSAFE_CLIPBOARD
    assert input_driver.copy_calls == 0
    assert rewriter.calls == []


def test_workflow_aborts_and_restores_when_focus_changes(settings: Settings) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = FakeInput(clipboard)
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99, 99, 99, 99, 100)),
        rewriter=FakeRewriter(),
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.FOCUS_CHANGED
    assert input_driver.paste_calls == 0
    assert clipboard.text == "keep me"
    assert len(clipboard.restore_calls) == 1


def test_workflow_restores_rewrite_if_focus_changes_just_before_paste(
    settings: Settings,
) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = FakeInput(clipboard)
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99, 99, 99, 99, 99, 99, 100)),
        rewriter=FakeRewriter(),
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.FOCUS_CHANGED
    assert outcome.message == "Active window changed before paste; nothing was pasted"
    assert input_driver.paste_calls == 0
    assert clipboard.text == "keep me"
    assert len(clipboard.restore_calls) == 1


def test_workflow_preserves_external_clipboard_change_during_inference(
    settings: Settings,
) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = FakeInput(clipboard)
    rewriter = FakeRewriter(before_return=lambda: clipboard.external_copy("new user copy"))
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.CLIPBOARD_CHANGED
    assert input_driver.paste_calls == 0
    assert clipboard.text == "new user copy"
    assert clipboard.restore_calls == []


def test_workflow_allows_activity_that_ends_during_inference(
    settings: Settings,
) -> None:
    class MutableInputWindows(FakeWindows):
        def __init__(self) -> None:
            super().__init__((99,))
            self.input_tick = 10

        def last_input_tick(self) -> int:
            return self.input_tick

    clipboard = FakeClipboard(original_text="keep me")
    input_driver = FakeInput(clipboard)
    windows = MutableInputWindows()
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=windows,
        rewriter=FakeRewriter(before_return=lambda: setattr(windows, "input_tick", 11)),
        selection_reader=FakeSelectionReader("rough idea"),
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.SUCCESS
    assert input_driver.paste_calls == 1
    assert clipboard.text == "keep me"


def test_workflow_cancels_when_target_text_changes_during_inference(
    settings: Settings,
) -> None:
    class MutableInputWindows(FakeWindows):
        def __init__(self) -> None:
            super().__init__((99,))
            self.input_tick = 10

        def last_input_tick(self) -> int:
            return self.input_tick

    clipboard = FakeClipboard(original_text="keep me")
    input_driver = FakeInput(clipboard)
    windows = MutableInputWindows()
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=windows,
        rewriter=FakeRewriter(before_return=lambda: setattr(windows, "input_tick", 11)),
        selection_reader=FakeSelectionReader("changed request"),
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.USER_ACTIVITY
    assert outcome.message == "Target text changed during inference; nothing was pasted"
    assert input_driver.paste_calls == 0
    assert clipboard.text == "keep me"


def test_workflow_cancels_user_input_at_final_paste_boundary(
    settings: Settings,
) -> None:
    clipboard = FakeClipboard(original_text="keep me")
    input_driver = FakeInput(clipboard)
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,), input_ticks=(10, 10, 10, 11)),
        rewriter=FakeRewriter(),
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.USER_ACTIVITY
    assert input_driver.paste_calls == 0
    assert clipboard.text == "keep me"


def test_workflow_does_not_send_clipboard_value_that_races_with_initial_read(
    settings: Settings,
) -> None:
    class RaceOnReadClipboard(FakeClipboard):
        def read_text(self) -> str:
            self.external_copy("PRIVATE EXTERNAL COPY")
            return self.text

    clipboard = RaceOnReadClipboard()
    input_driver = FakeInput(clipboard)
    rewriter = FakeRewriter()
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=rewriter,
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.CLIPBOARD_CHANGED
    assert rewriter.calls == []
    assert input_driver.paste_calls == 0
    assert clipboard.text == "PRIVATE EXTERNAL COPY"


def test_workflow_does_not_paste_clipboard_value_that_races_with_result_write(
    settings: Settings,
) -> None:
    class RaceAfterWriteClipboard(FakeClipboard):
        def write_text(self, text: str) -> int:
            written_sequence = super().write_text(text)
            if text.startswith("Role:"):
                self.external_copy("EXTERNAL CLIPBOARD VALUE")
            return written_sequence

    clipboard = RaceAfterWriteClipboard()
    input_driver = FakeInput(clipboard)
    workflow = build_workflow(
        settings=settings,
        clipboard=clipboard,
        input_driver=input_driver,
        windows=FakeWindows((99,)),
        rewriter=FakeRewriter(),
    )

    outcome = workflow.run()

    assert outcome.status is WorkflowStatus.CLIPBOARD_CHANGED
    assert input_driver.paste_calls == 0
    assert clipboard.text == "EXTERNAL CLIPBOARD VALUE"
