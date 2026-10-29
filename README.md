# globus-tui

A lightweight terminal UI for keeping an eye on Globus transfers without
leaving your shell. Press **Ctrl+G** in your terminal, see what is in flight,
press **q**, and you are back where you were.

It mirrors the three views of the Globus web app:

| Screen | What you see |
|---|---|
| **Dashboard** | Active / Failed / Succeeded counters (last 7 days), every active task with a progress bar, speed, bytes done / total, recent flow runs |
| **Activity › Tasks** | Searchable task list with TYPE and STATUS filters, status line per task ("sync transfer completed", "transfer started", …), progress for running tasks |
| **Task** | *Overview* tab with the same fields and stats box as the web app (files, directories, total estimated bytes, bytes transferred, effective speed …) and an *Event Log* tab with every event, its details, a fault-only toggle and a transfer-rate sparkline built from the PROGRESS events |

Auto-refresh with a visible "Update in m:ss" countdown, pause/resume, terminate
a task (with confirmation), edit a running task's label.

Built on [Textual](https://textual.textualize.io/) and the
[Globus SDK](https://globus-sdk-python.readthedocs.io/). Pure Python, no
daemon, no browser.

![Activity screen](docs/tasks.svg)

![Event log with transfer-rate sparkline](docs/event-log.svg)

## Install

```bash
git clone https://github.com/hamidghaedi/Terminal-UI-for-Globus.git ~/globus-tui
cd ~/globus-tui
./install.sh
```

`install.sh` does three things: `pipx install` (or `pip install --user`),
a one-time Globus login, and adds `source ~/globus-tui/shell/globus-tui.bash`
to your `~/.bashrc` (and `~/.zshrc` if present).

Manual equivalent:

```bash
pipx install .              # or: pip install --user .
globus-tui --login          # prints a URL, paste the code back
source shell/globus-tui.bash
```

Try it without an account first:

```bash
globus-tui --demo
```

### Login and tokens

The first run opens a standard Globus native-app login (a URL you open in any
browser, then paste the code back). Refresh tokens are stored by the SDK under
`~/.globus/app/`, so you only do this once. `globus-tui --logout` revokes and
deletes them.

By default the SDK's public tutorial client id is used. If you would rather
the tokens be issued to a client you own, register a *Native App* at
<https://app.globus.org/settings/developers> and either

```bash
export GLOBUS_TUI_CLIENT_ID=<your-uuid>
```

or put it in `~/.config/globus-tui/config.json`:

```json
{ "client_id": "<your-uuid>", "interval": 20, "flows": true }
```

## Hotkey

`shell/globus-tui.bash` binds, for interactive bash:

| Key | Opens |
|---|---|
| `Ctrl+G` | Dashboard |
| `Ctrl+X` `Ctrl+G` | Activity (task list) |

It uses `bind -x`, so whatever you had half-typed on the command line survives
the round trip. For zsh use `shell/globus-tui.zsh`; for tmux, the snippet in
`shell/tmux.conf` opens it as a popup over the current pane with `prefix g`.

If `Ctrl+G` is taken on your setup, change the key in the one `bind` line.

## Keys inside the TUI

```
Everywhere   d dashboard   t activity   r refresh   p pause   enter open   esc back   ? help   q quit
Activity     / search      T D  toggle TRANSFER / DELETE     a i f s  toggle ACTIVE / INACTIVE / FAILED / SUCCEEDED
             x terminate selected task
Task         o overview    l event log   F faults only   e edit label   x terminate
```

## Options

```
globus-tui [--demo] [--tasks] [-i SECONDS] [--client-id UUID] [--no-flows] [--login] [--logout]
```

`--no-flows` skips the Flows scope entirely if you never use flows and want a
smaller consent screen at login.

## Layout of the code

```
globus_tui/
  cli.py       argument parsing, login handling, launches the app
  backend.py   GlobusBackend (Transfer + Flows via globus-sdk UserApp) and DemoBackend
  fmt.py       byte / rate / date formatting and the web-app style status lines
  app.py       Textual screens: Dashboard, Tasks, TaskDetail, modals
  app.tcss     styling
shell/         bash, zsh and tmux bindings
```

The backend is a small interface (`list_tasks`, `count_tasks`, `get_task`,
`events`, `cancel`, `set_label`, `flow_runs`), so swapping in another data
source or adding screens (e.g. collections, timers) is straightforward.

## Notes

* Task event history is kept by Globus for 30 days; older tasks show a
  "could not load events" entry in the Event Log, same as the web app.
* Total estimated bytes can grow while a task is still scanning directories,
  so the progress bar can move backwards early in a recursive transfer.
* Progress on the Dashboard and Activity screens is bytes-based when Globus
  has an estimate, and subtask-based otherwise (delete tasks, early scanning).
