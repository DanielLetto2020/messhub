#!/usr/bin/env bash
# Удаление: останавливает сбор и виджет, убирает автозапуск (юниты systemd --user)
# и хук терминала. Данные (база, копии, настройки) остаются на месте.
#
#   ./uninstall.sh           убрать программу из системы, данные оставить
#   ./uninstall.sh --purge   и удалить все данные (спросит подтверждение)
#   ./uninstall.sh --purge --yes   без вопроса
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PURGE=0 YES=0
for a in "$@"; do
  case "$a" in
    --purge) PURGE=1 ;;
    --yes) YES=1 ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Неизвестный флаг: $a (см. --help)"; exit 2 ;;
  esac
done
PY=/usr/bin/python3; [ -x "$PY" ] || PY="$(command -v python3)"
read -r APP_ID LEGACY DATA CONFIG CACHE < <("$PY" -c "import sys; sys.path.insert(0, '$DIR'); import version, paths; print(version.APP_ID, ','.join(version.LEGACY_IDS), paths.DATA_DIR, paths.CONFIG_DIR, paths.CACHE_DIR)")
IDS="$APP_ID ${LEGACY//,/ }"     # и прежние имена — вдруг остались их сервисы

UNIT_DIR="$HOME/.config/systemd/user"
for u in $(for id in $IDS; do echo "$id-widget.service $id.service"; done); do
  if [ -f "$UNIT_DIR/$u" ]; then
    systemctl --user disable --now "$u" 2>/dev/null || true
    rm -f "$UNIT_DIR/$u"
    echo "Убран автозапуск: $u"
  fi
done
systemctl --user daemon-reload 2>/dev/null || true

for id in $IDS; do
  for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
    [ -f "$rc" ] && grep -qF "# >>> $id terminal hook >>>" "$rc" || continue
    sed -i "/# >>> $id terminal hook >>>/,/# <<< $id terminal hook <<</d" "$rc"
    echo "Убран хук терминала из $rc"
  done
done

if [ "$PURGE" = 1 ]; then
  echo "Будут удалены ВСЕ данные программы:"; printf '  %s\n' "$DATA" "$CONFIG" "$CACHE"
  if [ "$YES" != 1 ]; then read -r -p "Точно удалить? Введи «да»: " ans; [ "$ans" = "да" ] || [ "$ans" = "yes" ] || { echo "Отменено, данные на месте."; exit 0; }; fi
  rm -rf -- "$DATA" "$CONFIG" "$CACHE"
  echo "Данные удалены."
else
  echo "Данные оставлены: $DATA (база, копии), $CONFIG (настройки). Удалить: ./uninstall.sh --purge"
fi
