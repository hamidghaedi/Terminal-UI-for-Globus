#!/usr/bin/env bash
# globus-tui installer for shared HPC login nodes (no root, no pipx needed).
#
#   ./install.sh            install into ~/.local/share/globus-tui/venv, wire Ctrl+G
#   ./install.sh --login    ...and run the one-time Globus login at the end
#   ./install.sh --no-rc    do not touch ~/.bashrc / ~/.zshrc
#
# Override the interpreter with PYTHON=/path/to/python3 (3.9+). On Alliance
# clusters:  module load python/3.11 && ./install.sh
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
prefix="${GLOBUS_TUI_PREFIX:-$HOME/.local/share/globus-tui}"
venv="$prefix/venv"
bindir="$HOME/.local/bin"
do_login=0; touch_rc=1
for a in "$@"; do
    case "$a" in
        --login) do_login=1 ;;
        --no-rc) touch_rc=0 ;;
        *) echo "unknown option $a" >&2; exit 2 ;;
    esac
done

# --- pick a python >= 3.9 -------------------------------------------------
py="${PYTHON:-}"
if [ -z "$py" ]; then
    for c in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
        if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
            py="$(command -v "$c")"; break
        fi
    done
fi
if [ -z "$py" ]; then
    echo "No python >= 3.9 found. On a cluster try:  module load python/3.11   then re-run." >&2
    exit 1
fi
echo "Using $py ($("$py" -c 'import platform; print(platform.python_version())'))"

# --- venv + package ---------------------------------------------------------
mkdir -p "$prefix" "$bindir"
if [ ! -x "$venv/bin/python" ]; then
    "$py" -m venv "$venv" || { echo "python -m venv failed; try: module load python/3.11" >&2; exit 1; }
fi
"$venv/bin/python" -m pip install --quiet --upgrade pip
"$venv/bin/python" -m pip install --quiet --upgrade "$here"
ln -sf "$venv/bin/globus-tui" "$bindir/globus-tui"
echo "Installed: $bindir/globus-tui -> $venv"

case ":$PATH:" in
    *":$bindir:"*) ;;
    *) echo "NOTE: $bindir is not on PATH; the rc snippet below adds it." ;;
esac

# --- shell hotkey -----------------------------------------------------------
if [ "$touch_rc" = 1 ]; then
    add_line() {  # file, line
        [ -f "$1" ] || return 0
        grep -qF "$2" "$1" || printf '\n# globus-tui (Ctrl+G opens the Globus TUI)\n%s\n' "$2" >> "$1"
    }
    add_line "$HOME/.bashrc" "export PATH=\"$bindir:\$PATH\"; source \"$here/shell/globus-tui.bash\""
    add_line "$HOME/.zshrc"  "export PATH=\"$bindir:\$PATH\"; source \"$here/shell/globus-tui.zsh\""
    echo "Hotkey added to ~/.bashrc (and ~/.zshrc if present)."
fi

# --- login ------------------------------------------------------------------
if [ "$do_login" = 1 ]; then
    echo; echo "== Globus login: open the URL in any browser, approve, paste the code back =="
    "$bindir/globus-tui" --login
else
    echo; echo "Next: run   globus-tui --login   once (needs a human to paste a code),"
    echo "then open a new shell and press Ctrl+G.   Try it first with: globus-tui --demo"
fi
