"""Textual application: Dashboard, Activity (task list) and Task detail
screens mirroring the Globus web app."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from rich.table import Table
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (Button, DataTable, Input, Sparkline, Static,
                             TabbedContent, TabPane)

from . import fmt
from .backend import TASK_STATUSES, TASK_TYPES

def _utf8_ok() -> bool:
    """HPC login nodes sometimes run with LANG=C; fall back to ASCII glyphs."""
    import os
    import sys

    if os.environ.get("GLOBUS_TUI_ASCII"):
        return False
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    return "utf" in enc


UTF8 = _utf8_ok()

STATUS_ICON = {
    "ACTIVE": ("▶" if UTF8 else ">", "bold #1e78c8"),
    "INACTIVE": ("‖" if UTF8 else "|", "bold yellow"),
    "SUCCEEDED": ("✔" if UTF8 else "+", "bold green"),
    "FAILED": ("✖" if UTF8 else "x", "bold red"),
}
BAR_ON, BAR_OFF, ELLIPSIS = ("█", "░", "…") if UTF8 else ("#", "-", "~")


def icon(status: str) -> Text:
    ch, style = STATUS_ICON.get(status, ("*", ""))
    return Text(ch, style=style)


def bar(frac: Optional[float], width: int = 18) -> Text:
    if frac is None:
        return Text("scanning...", style="dim")
    n = int(round(frac * width))
    t = Text()
    t.append(BAR_ON * n, style="#1e78c8")
    t.append(BAR_OFF * (width - n), style="grey50")
    t.append(f" {frac * 100:5.1f}%")
    return t


def ellipsis(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + ELLIPSIS


# ------------------------------------------------------------------------
# Shared top bar with "Update in m:ss" countdown
# ------------------------------------------------------------------------
class TopBar(Horizontal):
    def __init__(self, title: str, id: str = "topbar"):
        super().__init__(id=id)
        self._title = title

    def compose(self) -> ComposeResult:
        yield Static(self._title, classes="title")
        yield Static("", classes="meta", id="meta")

    def set_meta(self, text: str) -> None:
        self.query_one("#meta", Static).update(text)


class RefreshingScreen(Screen):
    """Screen with a periodic data refresh and a visible countdown."""

    def __init__(self) -> None:
        super().__init__()
        self.countdown = 0
        self.err_text: Optional[str] = None

    def on_mount(self) -> None:
        self.countdown = self.app.interval
        self.set_interval(1, self._tick)
        self.refresh_now()

    def _tick(self) -> None:
        if not self.app.paused:
            self.countdown -= 1
            if self.countdown <= 0:
                self.countdown = self.app.interval
                self.refresh_now()
        self._update_meta()

    def _update_meta(self) -> None:
        if self.app.paused:
            txt = "⏸ paused   r refresh   p resume"
        else:
            txt = f"Update in {fmt.countdown(self.countdown)}   p pause   ? help"
        if self.err_text:
            txt = f"[red]{self.err_text}[/]   " + txt
        try:
            self.query_one(TopBar).set_meta(txt)
        except Exception:
            pass

    def refresh_now(self) -> None:  # override
        raise NotImplementedError

    def action_refresh(self) -> None:
        self.countdown = self.app.interval
        self.refresh_now()


# ------------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------------
class DashboardScreen(RefreshingScreen):
    BINDINGS = [
        Binding("enter", "open_selected", "Open", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield TopBar("Dashboard")
        with VerticalScroll(id="dash-body"):
            yield Static("Transfer and Delete Tasks", classes="section-title")
            with Horizontal(id="stat-row"):
                yield Static("", classes="stat active", id="stat-active")
                yield Static("", classes="stat failed", id="stat-failed")
                yield Static("", classes="stat ok", id="stat-succeeded")
            yield Static("Active tasks", classes="section-title")
            with Vertical(id="active-list"):
                yield DataTable(id="active-table", cursor_type="row", zebra_stripes=True)
                yield Static("", id="active-empty")
            yield Static("Flow Runs", classes="section-title")
            yield Static("", id="flows-box")
            yield Static(
                "t  Activity (all tasks)    enter  open task    r  refresh    q  quit",
                classes="hint",
            )
            yield Static(f"Signed in as {self.app.backend.identity()}", classes="tip")

    def on_mount(self) -> None:
        t = self.query_one("#active-table", DataTable)
        label_w = max(24, self.app.size.width - 8 - (3 + 30 + 26 + 12 + 24 + 10))
        t.add_column("", width=1)
        t.add_column("Label", width=label_w)
        t.add_column("Status", width=30)
        t.add_column("Progress", width=26)
        t.add_column("Speed", width=12)
        t.add_column("Done / Total", width=24)
        super().on_mount()

    def refresh_now(self) -> None:
        self._load()

    @work(thread=True, exclusive=True, group="dash")
    def _load(self) -> None:
        b = self.app.backend
        week = datetime.now(timezone.utc) - timedelta(days=7)
        try:
            active = b.list_tasks(statuses=("ACTIVE", "INACTIVE"), limit=50)
            failed = b.count_tasks(("FAILED",), since=week)
            succ = b.count_tasks(("SUCCEEDED",), since=week)
            runs = b.flow_runs(since=week, limit=5)
            err = None
        except Exception as exc:
            active, failed, succ, runs, err = [], 0, 0, None, f"refresh failed: {exc}"
        self.app.call_from_thread(self._apply, active, failed, succ, runs, err)

    def _apply(self, active, failed, succ, runs, err) -> None:
        self.err_text = err
        self._update_meta()
        if err:
            return

        def stat(id_, cap, n, sub=""):
            w = self.query_one(id_, Static)
            w.update(Text.assemble((cap + "\n", "dim"), (str(n), "bold"), ("\n" + sub, "dim")))

        stat("#stat-active", "Active", len(active))
        stat("#stat-failed", "Failed", failed, "LAST 7 DAYS")
        stat("#stat-succeeded", "Succeeded", succ, "LAST 7 DAYS")

        table = self.query_one("#active-table", DataTable)
        cur = table.cursor_row
        table.clear()
        for t in active:
            table.add_row(
                icon(t["status"]),
                Text(t.get("label") or t["task_id"], overflow="ellipsis", no_wrap=True),
                fmt.status_message(t),
                bar(fmt.progress_fraction(t)),
                fmt.human_rate(t.get("effective_bytes_per_second")),
                f"{fmt.human_bytes(t.get('bytes_transferred'))} / {fmt.human_bytes(t.get('total_estimated_bytes'))}",
                key=t["task_id"],
            )
        if active and cur is not None and cur < len(active):
            table.move_cursor(row=cur)
        table.display = bool(active)
        self.query_one("#active-empty", Static).update(
            "" if active else "No active transfer or delete tasks."
        )

        fb = self.query_one("#flows-box", Static)
        if runs is None:
            fb.update("Flows not available (not enabled or no consent).")
        elif not runs:
            fb.update("No flow runs in the last 7 days.")
        else:
            lines = []
            for r in runs:
                lines.append(
                    f"{r.get('status', '?'):<10} {r.get('label') or r.get('flow_title') or r.get('run_id')}"
                    f"   {fmt.local_dt(r.get('start_time'))}"
                )
            fb.update("\n".join(lines))

    @on(DataTable.RowSelected, "#active-table")
    def _open(self, ev: DataTable.RowSelected) -> None:
        self.app.push_screen(TaskDetailScreen(str(ev.row_key.value)))

    def action_open_selected(self) -> None:
        table = self.query_one("#active-table", DataTable)
        if table.row_count and table.cursor_row is not None:
            key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
            self.app.push_screen(TaskDetailScreen(str(key.value)))


# ------------------------------------------------------------------------
# Activity / task list
# ------------------------------------------------------------------------
class TasksScreen(RefreshingScreen):
    BINDINGS = [
        Binding("slash", "focus_search", "Search"),
        Binding("escape", "unfocus", "Back to list", show=False),
        Binding("T", "toggle('TRANSFER')", "Transfer", show=False),
        Binding("D", "toggle('DELETE')", "Delete", show=False),
        Binding("a", "toggle('ACTIVE')", "Active", show=False),
        Binding("i", "toggle('INACTIVE')", "Inactive", show=False),
        Binding("f", "toggle('FAILED')", "Failed", show=False),
        Binding("s", "toggle('SUCCEEDED')", "Succeeded", show=False),
        Binding("x", "cancel_selected", "Cancel task", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.types = set(TASK_TYPES)
        self.statuses = set(TASK_STATUSES)
        self.query_text = ""
        self.tasks: list[dict] = []

    def compose(self) -> ComposeResult:
        yield TopBar("Activity > Tasks")
        yield Input(placeholder="search tasks by label or collection   (/ to focus, esc to leave)", id="search")
        yield Static("", id="filterbar")
        yield DataTable(id="task-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="empty")

    def on_mount(self) -> None:
        t = self.query_one("#task-table", DataTable)
        # fixed widths so a long label cannot push the other columns off-screen
        label_w = max(32, self.app.size.width - 4 - (3 + 30 + 26 + 12 + 22 + 10))
        t.add_column("", width=1)
        t.add_column("Label", width=label_w)
        t.add_column("Status", width=30)
        t.add_column("Progress", width=26)
        t.add_column("Speed", width=12)
        t.add_column("Requested", width=20)
        t.focus()
        self._draw_filterbar()
        super().on_mount()

    def _draw_filterbar(self) -> None:
        def box(name, on_, key):
            return f"[{'x' if on_ else ' '}] {name} ({key})"
        txt = ("TYPE  " + box("TRANSFER", "TRANSFER" in self.types, "T") + "  " + box("DELETE", "DELETE" in self.types, "D")
               + "    STATUS  " + "  ".join(box(s, s in self.statuses, s[0].lower()) for s in TASK_STATUSES)
               + "    enter open   x cancel   d dashboard")
        self.query_one("#filterbar", Static).update(txt)

    def refresh_now(self) -> None:
        self._load(tuple(sorted(self.types)), tuple(sorted(self.statuses)))

    @work(thread=True, exclusive=True, group="tasks")
    def _load(self, types, statuses) -> None:
        try:
            tasks = self.app.backend.list_tasks(types=types, statuses=statuses, limit=100)
            err = None
        except Exception as exc:
            tasks, err = [], f"refresh failed: {exc}"
        self.app.call_from_thread(self._apply, tasks, err)

    def _apply(self, tasks, err) -> None:
        self.err_text = err
        self._update_meta()
        if err:
            return
        self.tasks = tasks
        self._render_rows()

    def _render_rows(self) -> None:
        q = self.query_text.lower().strip()
        rows = self.tasks
        if q:
            rows = [t for t in rows if q in " ".join(
                str(t.get(k) or "") for k in ("label", "task_id", "source_endpoint_display_name",
                                              "destination_endpoint_display_name")).lower()]
        table = self.query_one("#task-table", DataTable)
        cur = table.cursor_row
        table.clear()
        for t in rows:
            st = t["status"]
            prog = bar(fmt.progress_fraction(t)) if st in ("ACTIVE", "INACTIVE") else Text("")
            table.add_row(
                icon(st),
                Text(t.get("label") or t["task_id"], overflow="ellipsis", no_wrap=True),
                fmt.status_message(t),
                prog,
                fmt.human_rate(t.get("effective_bytes_per_second")) if st == "ACTIVE" else "",
                fmt.local_dt(t.get("request_time")),
                key=t["task_id"],
            )
        if rows and cur is not None and cur < len(rows):
            table.move_cursor(row=cur)
        self.query_one("#empty", Static).update("" if rows else "No tasks match the current filters.")

    # -- actions ---------------------------------------------------------
    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_unfocus(self) -> None:
        self.query_one("#task-table", DataTable).focus()

    def action_toggle(self, name: str) -> None:
        group = self.types if name in TASK_TYPES else self.statuses
        if name in group:
            group.discard(name)
        else:
            group.add(name)
        self._draw_filterbar()
        self.action_refresh()

    @on(Input.Changed, "#search")
    def _search_changed(self, ev: Input.Changed) -> None:
        self.query_text = ev.value
        self._render_rows()

    @on(Input.Submitted, "#search")
    def _search_submitted(self) -> None:
        self.action_unfocus()

    def _selected_id(self) -> Optional[str]:
        table = self.query_one("#task-table", DataTable)
        if not table.row_count or table.cursor_row is None:
            return None
        return str(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)

    @on(DataTable.RowSelected, "#task-table")
    def _open(self, ev: DataTable.RowSelected) -> None:
        self.app.push_screen(TaskDetailScreen(str(ev.row_key.value)))

    def action_cancel_selected(self) -> None:
        tid = self._selected_id()
        if tid:
            task = next((t for t in self.tasks if t["task_id"] == tid), None)
            if task and task["status"] in ("ACTIVE", "INACTIVE"):
                self.app.confirm_cancel(task, after=self.action_refresh)
            else:
                self.notify("That task is already complete.", severity="warning")


# ------------------------------------------------------------------------
# Task detail: Overview + Event Log
# ------------------------------------------------------------------------
class TaskDetailScreen(RefreshingScreen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("backspace", "app.pop_screen", "Back", show=False),
        Binding("o", "tab('overview')", "Overview"),
        Binding("l", "tab('events')", "Event log"),
        Binding("F", "toggle_faults", "Faults only", show=False),
        Binding("x", "cancel", "Terminate task", show=False),
        Binding("e", "edit_label", "Edit label", show=False),
    ]

    def __init__(self, task_id: str) -> None:
        super().__init__()
        self.task_id = task_id
        self.task_doc: dict = {}
        self.event_docs: list[dict] = []
        self.faults_only = False

    def compose(self) -> ComposeResult:
        yield TopBar("Task")
        with Horizontal(id="detail-head"):
            yield Static("", classes="lbl", id="head-label")
            yield Static("", id="detail-progress")
        with TabbedContent(initial="overview"):
            with TabPane("Overview (o)", id="overview"):
                with Horizontal(id="overview-body"):
                    yield Static("", id="kv")
                    with Vertical(id="stats-col"):
                        yield Static("", id="actions")
                        yield Static("", id="stats")
            with TabPane("Event Log (l)", id="events"):
                with Horizontal(id="events-body"):
                    yield DataTable(id="event-table", cursor_type="row", zebra_stripes=True)
                    with Vertical(id="event-side"):
                        yield Static("", id="event-detail")
                        with Vertical(id="viz-box"):
                            yield Static("Event Log Visualization", classes="lbl")
                            yield Static("transfer rate (Mbit/s), oldest -> newest", classes="cap")
                            yield Sparkline([], summary_function=max, id="rate-spark")
                            yield Static("", classes="cap", id="viz-range")

    def on_mount(self) -> None:
        self.query_one("#event-table", DataTable).add_columns("Time", "Code", "Description")
        super().on_mount()

    def refresh_now(self) -> None:
        self._load()

    @work(thread=True, exclusive=True, group="detail")
    def _load(self) -> None:
        b = self.app.backend
        try:
            task = b.get_task(self.task_id)
            events = b.events(self.task_id, limit=200)
            err = None
        except Exception as exc:
            task, events, err = {}, [], f"refresh failed: {exc}"
        self.app.call_from_thread(self._apply, task, events, err)

    # -- rendering -------------------------------------------------------
    def _apply(self, task, events, err) -> None:
        self.err_text = err
        self._update_meta()
        if err:
            return
        self.task_doc, self.event_docs = task, events
        t = task
        label = t.get("label") or t["task_id"]
        self.query_one(TopBar).query_one(".title", Static).update(f"Task > {ellipsis(label, 70)}")
        head = Text.assemble(icon(t["status"]), " ", (label, "bold"), "\n", (fmt.status_message(t), "dim"))
        head.no_wrap, head.overflow = True, "ellipsis"
        self.query_one("#head-label", Static).update(head)
        frac = fmt.progress_fraction(t)
        self.query_one("#detail-progress", Static).update(
            bar(frac, 28) if t["status"] in ("ACTIVE", "INACTIVE") else Text(""))

        kv = Table.grid(padding=(0, 2))
        kv.add_column(justify="right", style="bold")
        kv.add_column()
        rows = [
            ("Task Label", label),
            ("Source", t.get("source_endpoint_display_name") or "-"),
            ("Destination", t.get("destination_endpoint_display_name") or "-"),
            ("Task ID", t["task_id"]),
            ("Owner", t.get("owner_string") or self.app.backend.identity()),
            ("Condition", Text(t["status"], style=STATUS_ICON.get(t["status"], ("", ""))[1])),
            ("Requested", fmt.local_dt(t.get("request_time"))),
            ("Completed" if t.get("completion_time") else "Deadline",
             fmt.local_dt(t.get("completion_time") or t.get("deadline"))),
            ("Duration", fmt.duration(t.get("request_time"), t.get("completion_time"))),
            ("Base Paths", f"Source       {t.get('source_base_path') or '-'}\n"
                           f"Destination  {t.get('destination_base_path') or '-'}"),
            ("Transfer Settings", "\n".join("- " + s for s in fmt.transfer_settings(t))),
        ]
        if t.get("fatal_error"):
            fe = t["fatal_error"]
            rows.insert(6, ("Fatal Error", Text(f"{fe.get('code')}: {fe.get('description')}", style="red")))
        if t.get("nice_status") and t["nice_status"] not in ("OK", "Queued"):
            rows.insert(6, ("Nice Status", Text(f"{t['nice_status']} - {t.get('nice_status_short_description') or ''}",
                                                style="yellow")))
        for k, v in rows:
            kv.add_row(k, v)
        self.query_one("#kv", Static).update(kv)

        st = Table.grid(padding=(0, 2))
        st.add_column(justify="right", style="bold")
        st.add_column(style="dim")
        for v, k in [
            (t.get("files"), "Files"),
            (t.get("directories"), "Directories"),
            (t.get("files_transferred"), "Files Transferred"),
            (fmt.human_bytes(t.get("total_estimated_bytes")), "Total Estimated Bytes"),
            (fmt.human_bytes(t.get("bytes_transferred")), "Bytes Transferred"),
            (fmt.human_rate(t.get("effective_bytes_per_second")), "Effective Speed"),
            (t.get("files_skipped") if t.get("sync_level") is not None else "n/a", "Skipped files on sync"),
            (t.get("subtasks_skipped_errors") if t.get("skip_source_errors") else "n/a", "Skipped files on error"),
            (t.get("faults", 0), "Faults"),
            (f"{t.get('subtasks_succeeded', 0)} / {t.get('subtasks_total', 0)}", "Subtasks done"),
        ]:
            st.add_row(str(v if v is not None else "n/a"), k)
        self.query_one("#stats", Static).update(st)

        live = t["status"] in ("ACTIVE", "INACTIVE")
        self.query_one("#actions", Static).update(
            ("e  Edit Label      x  Terminate Task\n" if live else "") + "esc  back     l  event log"
        )
        self._render_events()

    def _render_events(self) -> None:
        evs = self.event_docs
        if self.faults_only:
            evs = [e for e in evs if e.get("is_error")]
        table = self.query_one("#event-table", DataTable)
        cur = table.cursor_row
        table.clear()
        for i, e in enumerate(evs):
            style = "red" if e.get("is_error") else ""
            table.add_row(
                fmt.local_time(e.get("time")),
                Text(str(e.get("code", "")), style=style),
                Text(str(e.get("description", "")), style=style),
                key=str(i),
            )
        if evs:
            table.move_cursor(row=min(cur or 0, len(evs) - 1))
            self._show_event(evs[min(cur or 0, len(evs) - 1)])
        else:
            self.query_one("#event-detail", Static).update(
                "No fault events for this task." if self.faults_only else "No events.")

        # sparkline from PROGRESS events, oldest first
        rates, times = [], []
        for e in reversed(self.event_docs):
            if str(e.get("code", "")).upper() != "PROGRESS":
                continue
            d = _details(e)
            if isinstance(d, dict) and "mbps" in d:
                rates.append(float(d["mbps"]))
                times.append(e.get("time"))
        spark = self.query_one("#rate-spark", Sparkline)
        spark.display = bool(rates)
        spark.data = rates
        rng = self.query_one("#viz-range", Static)
        if rates:
            tf = "%I:%M:%S %p"
            rng.update(f"{fmt.local_dt(times[0], tf)} -> {fmt.local_dt(times[-1], tf)}  "
                       f"min {min(rates):.0f}  max {max(rates):.0f}  last {rates[-1]:.0f}")
        else:
            rng.update("no progress events")
        faults = [e for e in self.event_docs if e.get("is_error")]
        self.query_one("#viz-box").border_title = f"{len(faults)} fault event(s)" if faults else "no fault events"

    def _show_event(self, e: dict) -> None:
        d = _details(e)
        if isinstance(d, dict):
            body = "\n".join(f"{k}: {v}" for k, v in d.items())
        else:
            body = str(d)
        self.query_one("#event-detail", Static).update(
            Text.assemble((f"{e.get('code')}  ", "bold red" if e.get("is_error") else "bold"),
                          (fmt.local_time(e.get("time")), "dim"), "\n\n", body))

    @on(DataTable.RowHighlighted, "#event-table")
    def _hl(self, ev: DataTable.RowHighlighted) -> None:
        evs = [e for e in self.event_docs if e.get("is_error")] if self.faults_only else self.event_docs
        try:
            self._show_event(evs[int(ev.row_key.value)])
        except (ValueError, IndexError, TypeError):
            pass

    # -- actions ---------------------------------------------------------
    def action_tab(self, name: str) -> None:
        self.query_one(TabbedContent).active = name

    def action_toggle_faults(self) -> None:
        self.faults_only = not self.faults_only
        self._render_events()
        self.notify("Showing fault events only" if self.faults_only else "Showing all events")

    def action_cancel(self) -> None:
        if self.task_doc and self.task_doc["status"] in ("ACTIVE", "INACTIVE"):
            self.app.confirm_cancel(self.task_doc, after=self.action_refresh)
        else:
            self.notify("Task is already complete.", severity="warning")

    def action_edit_label(self) -> None:
        if not self.task_doc or self.task_doc["status"] not in ("ACTIVE", "INACTIVE"):
            self.notify("Only running tasks can be relabelled.", severity="warning")
            return

        def done(label: Optional[str]) -> None:
            if label:
                try:
                    self.app.backend.set_label(self.task_id, label)
                    self.notify("Label updated")
                    self.action_refresh()
                except Exception as exc:
                    self.notify(f"Could not update label: {exc}", severity="error")

        self.app.push_screen(TextPrompt("Edit label", self.task_doc.get("label") or ""), done)


def _details(e: dict):
    d = e.get("details")
    if isinstance(d, str):
        try:
            return json.loads(d)
        except Exception:
            return d
    return d


# ------------------------------------------------------------------------
# Modals
# ------------------------------------------------------------------------
class Confirm(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "no", "No"), Binding("y", "yes", "Yes"), Binding("n", "no", "No")]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Static(self.question, classes="q")
            with Horizontal():
                yield Button("Cancel (n)", id="no")
                yield Button("Terminate (y)", variant="error", id="yes")

    @on(Button.Pressed)
    def _b(self, ev: Button.Pressed) -> None:
        self.dismiss(ev.button.id == "yes")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class TextPrompt(ModalScreen[Optional[str]]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, value: str = "") -> None:
        super().__init__()
        self.title_ = title
        self.value = value

    def compose(self) -> ComposeResult:
        with Vertical(id="modal"):
            yield Static(self.title_, classes="q")
            yield Input(value=self.value, id="prompt-input")

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    @on(Input.Submitted)
    def _ok(self, ev: Input.Submitted) -> None:
        self.dismiss(ev.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape", "app.pop_screen", "Close"), Binding("question_mark", "app.pop_screen", "Close")]

    TEXT = """[b]globus-tui keys[/b]

[b]Everywhere[/b]
  d           Dashboard            t     Activity (task list)
  r           Refresh now          p     Pause / resume auto-refresh
  enter       Open selected task   esc   Back
  ?           This help            q     Quit

[b]Activity[/b]
  /           Search by label / collection (esc returns to the list)
  T  D        Toggle TRANSFER / DELETE
  a i f s     Toggle ACTIVE / INACTIVE / FAILED / SUCCEEDED
  x           Terminate selected task

[b]Task[/b]
  o  l        Overview / Event Log tabs
  F           Fault events only
  e           Edit label        x   Terminate task
"""

    def compose(self) -> ComposeResult:
        yield Static(self.TEXT, id="help-box")


# ------------------------------------------------------------------------
# App
# ------------------------------------------------------------------------
class GlobusTUI(App):
    CSS_PATH = "app.tcss"
    TITLE = "Globus"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("d", "goto('dashboard')", "Dashboard"),
        Binding("t", "goto('tasks')", "Activity"),
        Binding("r", "screen_refresh", "Refresh"),
        Binding("p", "toggle_pause", "Pause"),
        Binding("question_mark", "help", "Help", show=False),
    ]
    SCREENS = {"dashboard": DashboardScreen, "tasks": TasksScreen}

    def __init__(self, backend, interval: int = 30, start: str = "dashboard") -> None:
        super().__init__()
        self.backend = backend
        self.interval = max(5, interval)
        self.paused = False
        self._start = start

    def on_mount(self) -> None:
        self.push_screen(self._start)

    def action_goto(self, name: str) -> None:
        if isinstance(self.screen, ModalScreen):
            return
        # unwind to the base screen (stack = [default, base]) and replace it
        while len(self.screen_stack) > 2:
            self.pop_screen()
        if isinstance(self.screen, self.SCREENS[name]):
            self.action_screen_refresh()
            return
        self.switch_screen(name)

    def action_screen_refresh(self) -> None:
        scr = self.screen
        if isinstance(scr, RefreshingScreen):
            scr.action_refresh()

    def action_toggle_pause(self) -> None:
        self.paused = not self.paused
        scr = self.screen
        if isinstance(scr, RefreshingScreen):
            scr._update_meta()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def confirm_cancel(self, task: dict, after=None) -> None:
        label = task.get("label") or task["task_id"]

        def done(yes: bool) -> None:
            if not yes:
                return
            try:
                msg = self.backend.cancel(task["task_id"])
                self.notify(msg)
            except Exception as exc:
                self.notify(f"Cancel failed: {exc}", severity="error")
            if after:
                after()

        self.push_screen(Confirm(f"Terminate task?\n\n[b]{label}[/b]\n\nThis stops the transfer and marks it FAILED (canceled)."), done)
