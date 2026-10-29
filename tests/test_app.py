import pytest
from textual.widgets import DataTable, Input, TabbedContent

from globus_tui.app import Confirm, GlobusTUI, TaskDetailScreen, TasksScreen
from globus_tui.backend import DemoBackend


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
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, TasksScreen)
        assert app.screen.query_one("#task-table", DataTable).row_count == 10
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, TaskDetailScreen)
        assert app.screen.err_text is None
        await pilot.press("l")
        assert app.screen.query_one(TabbedContent).active == "events"
        await pilot.press("escape", "slash")
        app.screen.query_one(Input).value = "not-a-real-task"
        await pilot.pause()
        assert app.screen.query_one("#task-table", DataTable).row_count == 0
        await pilot.press("escape", "d", "p")
        await app.workers.wait_for_complete()
        assert app.paused is True


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
