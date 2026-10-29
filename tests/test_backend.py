import json
import subprocess
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from globus_tui.backend import CLIBackend, DemoBackend, make_backend


def response(document):
    return subprocess.CompletedProcess([], 0, json.dumps(document), "")


def test_cli_uses_existing_session_and_preserves_total():
    backend = CLIBackend(executable="/opt/bin/globus")
    since = datetime(2026, 10, 22, tzinfo=timezone.utc)
    with patch("globus_tui.backend.subprocess.run", return_value=response({"DATA": [], "total": 1920})) as run:
        assert backend.count_tasks(("SUCCEEDED",), since) == 1920
        args, kwargs = run.call_args
        assert args[0][:5] == ["/opt/bin/globus", "api", "transfer", "GET", "/task_list"]
        assert "filter=type:TRANSFER,DELETE/status:SUCCEEDED/request_time:2026-10-22T00:00:00+00:00," in args[0]
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert "shell" not in kwargs
        assert kwargs["timeout"] == 20


def test_empty_filters_do_not_query_all_tasks():
    backend = CLIBackend(executable="globus")
    with patch.object(backend, "_run") as run:
        assert backend.list_tasks(types=()) == []
        assert backend.list_tasks(statuses=()) == []
        assert backend.count_tasks(()) == 0
        run.assert_not_called()


def test_task_and_events_use_json_without_shell():
    backend = CLIBackend(executable="globus")
    tid = "00000000-0000-0000-0000-000000000001"
    with patch.object(backend, "_run", return_value={"task_id": tid}) as run:
        assert backend.get_task(tid)["task_id"] == tid
        run.assert_called_once_with("task", "show", tid)
    with patch.object(backend, "_run", return_value={"DATA": [{"code": "PROGRESS"}]}) as run:
        assert backend.events(tid)[0]["code"] == "PROGRESS"
        run.assert_called_once_with("task", "event-list", tid, "--limit", "200")


def test_label_is_one_literal_argument():
    backend = CLIBackend(executable="globus")
    tid = "00000000-0000-0000-0000-000000000001"
    label = "a label; $(no-command) [text]"
    with patch.object(backend, "_run") as run:
        backend.set_label(tid, label)
        run.assert_called_once_with("task", "update", tid, "--label", label)


@pytest.mark.parametrize("result,message", [
    (subprocess.CompletedProcess([], 1, "", "Please run globus login"), "globus login"),
    (subprocess.CompletedProcess([], 0, "not json", ""), "invalid JSON"),
    (response([]), "unexpected response"),
])
def test_cli_errors_are_actionable(result, message):
    with patch("globus_tui.backend.subprocess.run", return_value=result):
        with pytest.raises(RuntimeError, match=message):
            CLIBackend(executable="globus").login_required()


def test_timeout_does_not_hang_ui_worker():
    with patch("globus_tui.backend.subprocess.run", side_effect=subprocess.TimeoutExpired("globus", 20)):
        with pytest.raises(RuntimeError, match="timed out"):
            CLIBackend(executable="globus").list_tasks()


def test_event_error_is_visible_in_event_log():
    with patch.object(CLIBackend, "_run", side_effect=RuntimeError("history unavailable")):
        events = CLIBackend(executable="globus").events("00000000-0000-0000-0000-000000000001")
        assert events[0]["is_error"] is True
        assert "history unavailable" in events[0]["details"]


def test_cli_logout_does_not_revoke_shared_session():
    with patch("globus_tui.backend.subprocess.run") as run:
        with pytest.raises(RuntimeError, match="shared"):
            CLIBackend(executable="globus").logout()
        run.assert_not_called()


def test_auto_uses_cli_and_demo_never_uses_credentials(monkeypatch):
    monkeypatch.delenv("GLOBUS_TUI_CLIENT_ID", raising=False)
    with patch("globus_tui.backend.load_config", return_value={}), patch("globus_tui.backend.shutil.which", return_value="/bin/globus"):
        assert isinstance(make_backend(), CLIBackend)
        assert isinstance(make_backend(demo=True), DemoBackend)
        with patch("globus_tui.backend.GlobusBackend") as sdk:
            make_backend(client_id="custom-native-client")
            sdk.assert_called_once_with(client_id="custom-native-client", flows=True)
