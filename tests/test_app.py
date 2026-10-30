import pytest
from textual.widgets import DataTable, Input, TabbedContent

from globus_tui.app import (Confirm, GlobusTUI, HelpScreen, ShortcutGuide,
                            TaskDetailScreen, TasksScreen, TextPrompt)
from globus_tui.backend import DemoBackend


def assert_guide(app, context):
    guide = app.screen.query_one(ShortcutGuide)
    assert guide.guide_text == ShortcutGuide.CONTEXT[context]
    assert guide.visible and guide.display
    assert guide.region.bottom == app.size.height
    assert guide.region.width == app.size.width


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(80, 24), (160, 48)])
async def test_dashboard_activity_detail_and_search(size):
    backend = DemoBackend()
    app = GlobusTUI(backend, interval=30)
    async with app.run_test(size=size) as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.screen.err_text is None
        assert app.screen.query_one("#active-table", DataTable).row_count == 2
        assert_guide(app, "dashboard")
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, TasksScreen)
        assert app.screen.query_one("#task-table", DataTable).row_count == 10
        assert_guide(app, "tasks")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, TaskDetailScreen)
        assert app.screen.err_text is None
        assert_guide(app, "detail")
        await pilot.press("l")
        assert app.screen.query_one(TabbedContent).active == "events"
        assert_guide(app, "detail")
        await pilot.press("escape", "slash")
        app.screen.query_one(Input).value = "not-a-real-task"
        await pilot.pause()
        assert app.screen.query_one("#task-table", DataTable).row_count == 0
        assert_guide(app, "search")
        await pilot.press("escape", "d", "p")
        await app.workers.wait_for_complete()
        assert app.paused is True


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [(80, 24), (160, 48)])
async def test_guide_remains_visible_in_dialogs_and_when_scrolling(size):
    backend = DemoBackend()
    app = GlobusTUI(backend)
    async with app.run_test(size=size) as pilot:
        await app.workers.wait_for_complete()
        app.screen.query_one("#dash-body").scroll_end(animate=False)
        await pilot.pause()
        assert_guide(app, "dashboard")
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        assert_guide(app, "help")
        await pilot.press("escape")
        app.push_screen(TextPrompt("Edit label", "Example transfer"))
        await pilot.pause()
        assert_guide(app, "label")
        await pilot.press("escape")
        app.confirm_cancel(backend._active)
        await pilot.pause()
        assert_guide(app, "confirm")
        await pilot.press("n")
        assert backend._active["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_cancel_requires_confirmation_and_no_keeps_task_running():
    backend = DemoBackend()
    task = backend._active
    app = GlobusTUI(backend)
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        app.confirm_cancel(task)
        await pilot.pause()
        assert isinstance(app.screen, Confirm)
        await pilot.press("n")
        assert backend.get_task(task["task_id"])["status"] == "ACTIVE"
