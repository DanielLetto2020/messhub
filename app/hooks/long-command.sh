# shellcheck shell=bash
# Долгие команды терминала → карточка в виджете («готово» или «ошибка», сколько шла).
#
# Подключение — одна строка в ~/.bashrc или ~/.zshrc (или ./install.sh --terminal-hook):
#     source /путь/к/программе/hooks/long-command.sh
#
# MESSHUB_LONG_CMD       — порог в секундах (по умолчанию 60)
# MESSHUB_LONG_CMD_SKIP  — программы, о которых не сообщать (редакторы, пейджеры, ssh…)
#
# Работает через обычный notify-send (всплывашка подписана «Терминал»), а на доске
# попадает в тематическую колонку «Команды» (desktop-entry messhub-commands) — она
# включается в настройках → «Тематические колонки». Дальше действуют правила виджета.
# Итог с хвостом вывода и «починилось» — у обёртки: messhub run -- команда.
# В bash, если подключён bash-preexec, хук встаёт в его списки; иначе использует
# trap DEBUG + PROMPT_COMMAND.

[ -n "${__EM_HOOK_LOADED:-}" ] && return 0
__EM_HOOK_LOADED=1
: "${MESSHUB_LONG_CMD:=60}"
: "${MESSHUB_LONG_CMD_SKIP:=vim nvim vi nano emacs less more man top htop btop ssh mc tmux screen watch tail journalctl}"

__em_start=""
__em_cmd=""

__em_preexec() {            # $1 — команда целиком
  __em_cmd="$1"
  __em_start=$(date +%s)
}

__em_precmd() {
  local code=$? now dur first took status app
  [ -z "$__em_start" ] && return $code
  now=$(date +%s); dur=$(( now - __em_start )); __em_start=""
  [ "$dur" -lt "$MESSHUB_LONG_CMD" ] && return $code
  first=${__em_cmd%% *}; first=${first##*/}
  case " $MESSHUB_LONG_CMD_SKIP " in *" $first "*) return $code ;; esac
  command -v notify-send >/dev/null 2>&1 || return $code
  case "${LANG:-}" in
    ru*|uk*|be*)
      app="Терминал"
      if [ $(( dur / 60 )) -gt 0 ]; then took="$(( dur / 60 )) мин $(( dur % 60 )) с"; else took="${dur} с"; fi
      if [ $code -eq 0 ]; then status="готово за $took"; else status="ошибка (код $code) через $took"; fi ;;
    *)
      app="Terminal"
      if [ $(( dur / 60 )) -gt 0 ]; then took="$(( dur / 60 ))m $(( dur % 60 ))s"; else took="${dur}s"; fi
      if [ $code -eq 0 ]; then status="done in $took"; else status="failed (code $code) after $took"; fi ;;
  esac
  notify-send -a "$app" -h "string:desktop-entry:messhub-commands" "${__em_cmd:0:80}" "$status" 2>/dev/null
  return $code
}

if [ -n "${ZSH_VERSION:-}" ]; then
  autoload -Uz add-zsh-hook
  add-zsh-hook preexec __em_preexec
  add-zsh-hook precmd __em_precmd
elif [ -n "${BASH_VERSION:-}" ]; then
  if declare -F __bp_preexec_invoke_exec >/dev/null 2>&1; then     # bash-preexec
    preexec_functions+=(__em_preexec)
    precmd_functions+=(__em_precmd)
  else
    __em_debug() {
      [ -n "${COMP_LINE:-}" ] && return                  # автодополнение
      case "$BASH_COMMAND" in __em_*) return ;; esac      # наши же функции
      [ -z "$__em_start" ] && __em_preexec "$BASH_COMMAND" # только первая команда строки
    }
    trap '__em_debug' DEBUG
    PROMPT_COMMAND="__em_precmd${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
  fi
fi
