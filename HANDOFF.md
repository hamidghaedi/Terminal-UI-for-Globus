# Handoff: installing globus-tui on an HPC cluster

This file is written for an LLM agent (or a person) that has a shell on a
cluster login node and is asked to install `globus-tui` for a user. Follow
the steps in order. Everything is user-space; no root, no modules need to be
installed system-wide.

## 0. What you are installing

`globus-tui` is a Python terminal UI (Textual + globus-sdk) that shows the
user's Globus transfer tasks, like the Globus web app's Dashboard / Activity /
Task pages. It is launched by typing `globus-tui` or by pressing **Ctrl+G** in
bash once the hotkey is sourced. It talks to `transfer.api.globus.org`,
`flows.globus.org` and `auth.globus.org` over HTTPS and needs nothing else.

Repository: https://github.com/hamidghaedi/Terminal-UI-for-Globus

**Existing CLI authentication:** the default `auto` backend now uses an installed
`globus` command. First run `globus-tui --backend cli --check`. If that passes,
launch the TUI directly; no new browser consent is needed. Tokens are not copied
or inspected. CLI calls time out after 20 seconds. Flows require the separate SDK
backend. The native-app login instructions below apply to `--backend sdk` only;
use `globus-tui --backend sdk --login` for that route. A CLI login problem is
resolved by the user running `globus login`, and CLI logout is managed separately
so the TUI does not revoke a session shared with other project tools.

## 1. Hard constraints to respect

1. **Run on a login node (or any node with outbound HTTPS).** Compute nodes
   on most clusters have no internet, so the TUI cannot run there. Do not
   submit it as a job.
2. **A new Globus login is interactive and needs a human.** `globus-tui
   --backend sdk --login` prints a URL; the user must open it in their own browser, approve,
   and paste a code back into the terminal. You cannot complete this step
   yourself. Check the existing CLI session first; only hand back a login command
   when authentication is actually required.
3. **Do not install into the system Python, do not use `sudo`, do not use
   `pip install --user` into a cluster module's site-packages.** The installer
   makes a private venv under `~/.local/share/globus-tui/venv`.
4. **Do not edit the user's shell rc files by hand.** `install.sh` appends one
   clearly commented line to `~/.bashrc` (and `~/.zshrc` if it exists), and
   is idempotent. If the user does not want that, run it with `--no-rc`.
5. **Tokens live in `~/.globus/app/`** (created by the SDK with 0600 perms).
   Never copy, print, or move them.

## 2. Pre-flight

```bash
# where are we?
hostname; echo "$HOME"; df -h "$HOME" | tail -1          # need ~150 MB free in $HOME

# a Python >= 3.9 with venv + pip. On Alliance / Compute Canada / CAC clusters:
module avail python 2>&1 | head
module load python/3.11            # any 3.9+ is fine; 3.11 or 3.12 preferred
python3 --version
python3 -c "import venv, ensurepip; print('venv ok')"

# outbound HTTPS from this node (any HTTP status is fine; a timeout is not)
curl -sS -o /dev/null -w '%{http_code}\n' https://transfer.api.globus.org/v0.10/endpoint_search?limit=1
```

If `curl` times out, check whether the site needs a proxy (`env | grep -i proxy`,
cluster docs). The SDK honours `HTTPS_PROXY`. If there is no route out at
all, stop and tell the user the TUI must be installed on a login node that
has internet access.

If `module load python/...` is what provided Python, the user will need that
same `module load` in their `~/.bashrc` *before* the globus-tui line, or the
venv's interpreter may be missing from later shells. On Alliance clusters the
venv keeps an absolute path to the module's python, so the venv keeps working
as long as that module version stays installed; prefer a long-lived version.

## 3. Install

```bash
git clone https://github.com/hamidghaedi/Terminal-UI-for-Globus.git ~/globus-tui
cd ~/globus-tui
./install.sh              # add --no-rc to leave ~/.bashrc alone
```

What it does, so you can verify or redo pieces by hand:

| Step | Command equivalent |
|---|---|
| pick python >= 3.9 (`$PYTHON` overrides) | `python3 -m venv ~/.local/share/globus-tui/venv` |
| install the package into that venv | `~/.local/share/globus-tui/venv/bin/pip install ~/globus-tui` |
| expose the command | `ln -sf ~/.local/share/globus-tui/venv/bin/globus-tui ~/.local/bin/globus-tui` |
| hotkey + PATH | appends `export PATH="$HOME/.local/bin:$PATH"; source "$HOME/globus-tui/shell/globus-tui.bash"` to `~/.bashrc` |

The pip step downloads `textual` and `globus-sdk` from PyPI. On Alliance
clusters pip is configured to prefer the local wheelhouse and fall back to
PyPI; that works. If the cluster blocks PyPI entirely, build the wheels
elsewhere and `pip install` them from a directory with `--no-index
--find-links`.

## 4. Verify (non-interactive, safe to run yourself)

```bash
export PATH="$HOME/.local/bin:$PATH"
globus-tui --version
globus-tui --check          # environment report; exits 1 while not logged in, that is expected
globus-tui --check --demo   # same report without the login requirement; must exit 0
```

Expected `--check` output before login:

```
[ok]   python 3.11.x at /home/.../venv/bin/python
[ok]   textual 8.x, globus-sdk 4.x
[ok]   stdout encoding utf-8
[ok]   TERM=xterm-256color
[FAIL] not logged in: run `globus-tui --login` (interactive)
[ok]   transfer.api.globus.org reachable (HTTP 400)
```

Only the "not logged in" line should fail. If `stdout encoding` warns, the
TUI still works with ASCII glyphs; suggesting `export LANG=C.UTF-8` in
`~/.bashrc` fixes the look. If `TERM` warns, the TUI forces
`xterm-256color` itself.

You can also open the UI with fake data to confirm rendering in the user's
terminal: `globus-tui --demo` (press `q` to exit). Only do this in an
interactive session, never from a script.

## 5. Hand back to the user

Tell the user to run, in a terminal where they can open a browser on their
laptop:

```bash
globus-tui --backend sdk --login
```

then open a new shell (or `source ~/.bashrc`) and press **Ctrl+G**. Also
mention `globus-tui --tasks` (open on the task list), `Ctrl+X Ctrl+G` (same,
via hotkey) and `?` inside the UI for keys.

## 6. Optional configuration

`~/.config/globus-tui/config.json`:

```json
{ "interval": 20, "flows": true, "client_id": "<uuid>" }
```

* `interval` refresh seconds (default 30). Keep it >= 10 on shared nodes.
* `flows: false` (or `--no-flows`) drops the Flows scope and the Flow Runs
  box; useful if the user never uses flows and wants a shorter consent page.
* `client_id` a native-app client the user registered at
  https://app.globus.org/settings/developers. Default is the Globus SDK's
  public tutorial client, which works fine for personal monitoring.

tmux users: `shell/tmux.conf` has a `prefix g` popup binding (tmux >= 3.2).

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `python -m venv` fails with "ensurepip is not available" | Distro python without venv. `module load python/3.11` or `PYTHON=/path/to/other/python3 ./install.sh`. |
| `pip install` hangs or fails on SSL | Node has no outbound HTTPS or needs `HTTPS_PROXY`. Install on a login node. |
| `globus-tui: command not found` after install | `~/.local/bin` not on PATH in that shell. `export PATH="$HOME/.local/bin:$PATH"` or open a new login shell. |
| `--login` prints the URL but the paste fails with "invalid grant" | Code expired or already used; re-run `--login`. |
| TUI opens but every screen says `refresh failed: ... 401/403` | Tokens revoked or consent missing. `globus-tui --logout && globus-tui --login`. |
| Boxes/bars render as `?` | Terminal locale is not UTF-8. `export LANG=C.UTF-8` or set `GLOBUS_TUI_ASCII=1`. |
| Ctrl+G does nothing | The rc line was not sourced (non-interactive shell, or a different rc file such as `~/.bash_profile`). `source ~/globus-tui/shell/globus-tui.bash` in the right file. |
| Event Log says "could not load events" | Task is older than 30 days; Globus deletes event history. Normal. |

## 8. Uninstall

```bash
globus-tui --logout                  # revokes tokens (optional)
rm -rf ~/.local/share/globus-tui ~/.local/bin/globus-tui ~/globus-tui ~/.config/globus-tui
# then delete the "globus-tui" line from ~/.bashrc / ~/.zshrc
```
