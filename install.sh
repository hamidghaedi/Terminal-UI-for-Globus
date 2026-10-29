#!/usr/bin/env bash
# One-shot setup: install the package, log in once, wire the Ctrl+G hotkey.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v pipx >/dev/null 2>&1; then
    pipx install --force "$here"
else
    python3 -m pip install --user --upgrade "$here"
fi

if ! command -v globus-tui >/dev/null 2>&1; then
    echo "globus-tui is installed but not on PATH. Add ~/.local/bin to PATH and re-run." >&2
    exit 1
fi

echo
echo "== Globus login (one time; tokens are refreshed automatically afterwards) =="
globus-tui --login

rc="$HOME/.bashrc"
line="source \"$here/shell/globus-tui.bash\""
if ! grep -qF "$line" "$rc" 2>/dev/null; then
    printf '\n# globus-tui hotkey (Ctrl+G)\n%s\n' "$line" >> "$rc"
    echo "Added hotkey to $rc"
fi
if [ -f "$HOME/.zshrc" ]; then
    zline="source \"$here/shell/globus-tui.zsh\""
    grep -qF "$zline" "$HOME/.zshrc" || printf '\n# globus-tui hotkey (Ctrl+G)\n%s\n' "$zline" >> "$HOME/.zshrc"
fi

echo
echo "Done. Open a new shell (or: source ~/.bashrc) and press Ctrl+G."
