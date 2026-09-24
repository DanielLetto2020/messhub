#!/usr/bin/env bash
# Установка для текущего пользователя (sudo не нужен):
#   1) проверяет зависимости и подсказывает, какие пакеты поставить;
#   2) собирает юниты systemd --user из packaging/systemd/*.in с путём к ЭТОЙ папке;
#   3) включает автозапуск и запускает сбор и виджет.
# Данные программа хранит отдельно от кода: ~/.local/share/<id>, ~/.config/<id>.
#
#   ./install.sh                  установить и запустить
#   ./install.sh --no-widget      только сбор и страница (без окна на рабочем столе)
#   ./install.sh --no-start       поставить, но не запускать
#   ./install.sh --terminal-hook  ещё и сообщать о долгих командах терминала (bash/zsh)
#   ./install.sh --dry-run        показать, что будет сделано, ничего не меняя
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIDGET=1 START=1 HOOK=0 DRY=0
for a in "$@"; do
  case "$a" in
    --no-widget) WIDGET=0 ;;
    --no-start) START=0 ;;
    --terminal-hook) HOOK=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Неизвестный флаг: $a (см. --help)"; exit 2 ;;
  esac
done

run() { if [ "$DRY" = 1 ]; then echo "  [dry-run] $*"; else "$@"; fi; }
say() { printf '%s\n' "$*"; }

# системный python — у него есть gi (GTK/WebKit из пакетов дистрибутива)
PY=/usr/bin/python3
[ -x "$PY" ] || PY="$(command -v python3 || true)"
[ -n "$PY" ] || { say "Нужен python3 (3.9+)."; exit 1; }
read -r APP_ID APP_NAME VER LEGACY < <("$PY" -c "import sys; sys.path.insert(0, '$DIR'); import version as v; print(v.APP_ID, v.APP_NAME, v.__version__, ','.join(v.LEGACY_IDS))")
say "== $APP_NAME $VER — установка из $DIR"

# ── зависимости ──
has_gi() { "$PY" -c "import gi; gi.require_version('$1', '$2')" 2>/dev/null; }
missing_req=() missing_opt=()
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || missing_req+=("python3 ≥ 3.9")
command -v dbus-monitor >/dev/null || missing_req+=("dbus-monitor")
if [ "$WIDGET" = 1 ]; then
  "$PY" -c 'import gi' 2>/dev/null || missing_req+=("python3-gi")
  has_gi Gtk 3.0 || missing_req+=("GTK 3 (gir)")
  has_gi WebKit2 4.1 || missing_req+=("WebKit2GTK 4.1 (gir)")
  has_gi Wnck 3.0 || missing_opt+=("libwnck 3 (gir) — «перейти в приложение»")
fi
command -v notify-send >/dev/null || missing_opt+=("notify-send — свои события и хук терминала")
command -v canberra-gtk-play >/dev/null || command -v pw-play >/dev/null || command -v paplay >/dev/null \
  || missing_opt+=("canberra-gtk-play / pw-play — звук для правил")
command -v gdbus >/dev/null || missing_opt+=("gdbus — проверка службы уведомлений")

pkg_hint() {
  if command -v apt >/dev/null; then
    say "  sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-wnck-3.0 dbus-bin libnotify-bin gnome-session-canberra"
  elif command -v dnf >/dev/null; then
    say "  sudo dnf install python3-gobject gtk3 webkit2gtk4.1 libwnck3 dbus-tools libnotify libcanberra-gtk3"
  elif command -v pacman >/dev/null; then
    say "  sudo pacman -S python-gobject gtk3 webkit2gtk-4.1 libwnck3 dbus libnotify libcanberra"
  else
    say "  поставь пакеты с GObject-интроспекцией для GTK 3, WebKit2GTK 4.1 и libwnck 3"
  fi
}
if [ ${#missing_opt[@]} -gt 0 ]; then
  say "Необязательно, но полезно:"; for m in "${missing_opt[@]}"; do say "  – $m"; done
fi
if [ ${#missing_req[@]} -gt 0 ]; then
  say "Не хватает обязательного:"; for m in "${missing_req[@]}"; do say "  ✕ $m"; done
  say "Поставь, например:"; pkg_hint
  exit 1
fi
[ ${#missing_opt[@]} -gt 0 ] && { say "Поставить всё разом:"; pkg_hint; }

UNIT_DIR="$HOME/.config/systemd/user"

# ── переезд с прежнего имени (eXpress-msgs → messhub) ──
# Старые сервисы останавливаем ДО переноса папок: база не должна быть открыта при переезде.
for old in ${LEGACY//,/ }; do
  for u in "$old-widget.service" "$old.service"; do
    [ -f "$UNIT_DIR/$u" ] || continue
    run systemctl --user disable --now "$u" || true
    run rm -f "$UNIT_DIR/$u"
    say "Прежний сервис убран: $u"
  done
  for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [ -f "$rc" ] && grep -qF "# >>> $old terminal hook >>>" "$rc" || continue
    run sed -i "/# >>> $old terminal hook >>>/,/# <<< $old terminal hook <<</d" "$rc"
    say "Прежний хук терминала убран из $rc — ставлю новый"
    HOOK=1
  done
done
if [ "$DRY" = 1 ]; then say "  [dry-run] перенести папки данных прежних имён ($LEGACY) в ~/.local/share/$APP_ID, ~/.config/$APP_ID"
else "$PY" -c "import sys; sys.path.insert(0, '$DIR'); import paths; paths.migrate_old_app_dirs()"; fi

# ── юниты systemd --user ──
run mkdir -p "$UNIT_DIR"
render() {   # шаблон → юнит с путями этой установки
  sed -e "s|@DIR@|$DIR|g" -e "s|@PYTHON@|$PY|g" -e "s|@APP_ID@|$APP_ID|g" -e "s|@APP_NAME@|$APP_NAME|g" "$1"
}
units=("$APP_ID.service")
[ "$WIDGET" = 1 ] && units+=("$APP_ID-widget.service")
for u in "${units[@]}"; do
  tpl="$DIR/packaging/systemd/app.service.in"
  [ "$u" = "$APP_ID-widget.service" ] && tpl="$DIR/packaging/systemd/app-widget.service.in"
  if [ "$DRY" = 1 ]; then say "  [dry-run] $UNIT_DIR/$u:"; render "$tpl" | sed 's/^/      /'
  else render "$tpl" > "$UNIT_DIR/$u"; say "Юнит: $UNIT_DIR/$u"; fi
done
run systemctl --user daemon-reload
for u in "${units[@]}"; do
  run systemctl --user enable "$u"
  if [ "$START" = 1 ]; then run systemctl --user restart "$u"; fi
done

# ── хук терминала ──
if [ "$HOOK" = 1 ]; then
  line="source \"$DIR/hooks/long-command.sh\""
  for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [ -f "$rc" ] || continue
    if grep -qF "# >>> $APP_ID terminal hook >>>" "$rc"; then say "Хук терминала уже есть в $rc"; continue; fi
    if [ "$DRY" = 1 ]; then say "  [dry-run] добавить в $rc: $line"; continue; fi
    printf '\n# >>> %s terminal hook >>>\n%s\n# <<< %s terminal hook <<<\n' "$APP_ID" "$line" "$APP_ID" >> "$rc"
    say "Хук терминала добавлен в $rc (заработает в новом терминале)"
  done
fi

say ""
say "Готово. Страница: http://127.0.0.1:8765   ·   настройки: http://127.0.0.1:8765/settings"
say "Состояние: systemctl --user status $APP_ID   ·   удалить: ./uninstall.sh"
