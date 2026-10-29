# globus-tui hotkey for zsh
# Source this from ~/.zshrc:   source ~/globus-tui/shell/globus-tui.zsh
#
# Ctrl+G        -> dashboard
# Ctrl+X Ctrl+G -> Activity (task list)

__globus_tui_widget() {
    zle -I                      # invalidate the prompt before taking the screen
    globus-tui "$@" </dev/tty >/dev/tty
    zle reset-prompt
}
__globus_tui_dash()  { __globus_tui_widget; }
__globus_tui_tasks() { __globus_tui_widget --tasks; }
zle -N __globus_tui_dash
zle -N __globus_tui_tasks
bindkey '^G' __globus_tui_dash
bindkey '^X^G' __globus_tui_tasks
