# globus-tui hotkey for bash (WSL2 / MobaXterm friendly)
# Source this from ~/.bashrc:   source ~/globus-tui/shell/globus-tui.bash
#
# Ctrl+G  -> open the Globus TUI (dashboard). Closing it (q) returns you to
#            exactly where you were, with your half-typed command intact.
# Ctrl+X Ctrl+G -> open straight on the Activity (task list) screen.
#
# Change the key by editing the two bind lines; see `bind -P` for what's free.

if [[ $- == *i* ]]; then
    __globus_tui_dash() { globus-tui </dev/tty >/dev/tty; }
    __globus_tui_tasks() { globus-tui --tasks </dev/tty >/dev/tty; }
    bind -x '"\C-g": __globus_tui_dash'
    bind -x '"\C-x\C-g": __globus_tui_tasks'
fi
