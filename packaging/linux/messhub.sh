#!/bin/sh
# messhub — команда из пакета .deb/.rpm (программа лежит в /usr/lib/messhub).
#   messhub            запустить сбор и доску (включит их автозапуск для тебя); уже работает — открыть настройки
#   messhub settings   открыть настройки в браузере
#   messhub stop       остановить сбор и доску
#   messhub autostart off   не запускать при входе в систему (on — снова запускать)
#   messhub run -- make build   выполнить команду, итог — в колонку «Команды» (код выхода сохраняется)
#   messhub --version
APP=/usr/lib/messhub
PY=/usr/bin/python3
UNITS="messhub.service messhub-widget.service"
has_user_systemd() { command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; }

case "${1:-}" in
  -V|--version) exec "$PY" "$APP/version.py" ;;
  -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  run) shift; exec "$PY" "$APP/run.py" "$@" ;;
  settings) exec xdg-open http://127.0.0.1:8765/settings ;;
  stop) exec systemctl --user stop $UNITS ;;
  autostart)
    case "${2:-}" in
      on) exec systemctl --user enable $UNITS ;;
      off) exec systemctl --user disable $UNITS ;;
      *) echo "messhub autostart on|off"; exit 2 ;;
    esac ;;
  collect|view|widget|show) cmd=$1; shift; exec "$PY" "$APP/$cmd.py" "$@" ;;
  "") ;;
  *) echo "Неизвестная команда: $1 (см. messhub --help)"; exit 2 ;;
esac

if has_user_systemd; then
  if systemctl --user is-active --quiet messhub-widget.service; then
    exec xdg-open http://127.0.0.1:8765/settings
  fi
  systemctl --user daemon-reload          # только что поставленный пакет — юниты ещё не прочитаны
  exec systemctl --user enable --now $UNITS
fi
# без systemd --user — просто запустить оба процесса
"$PY" "$APP/collect.py" --quiet >/dev/null 2>&1 &
sleep 1
exec "$PY" "$APP/widget.py"
