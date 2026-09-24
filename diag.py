#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Самодиагностика и автозапуск — для раздела «Система» в настройках.

checks() — список проверок {id, state: ok|warn|bad|info, title, text, hint}:
жив ли сбор, когда было последнее уведомление и от кого, что за служба
уведомлений, известные ловушки (Telegram без системных уведомлений, Wayland),
библиотеки, звук, место на диске, копии, умный поиск.

Автозапуск — это юниты systemd --user (<APP_ID>.service — сбор, <APP_ID>-widget.service
— виджет): включить/выключить = systemctl --user enable/disable.
"""

import os
import shutil
import sqlite3
import subprocess
import sys

import backup
import catcher
import mail
import paths
import rules
import version
from i18n import L

UNITS = {"collect": f"{version.APP_ID}.service", "widget": f"{version.APP_ID}-widget.service"}
UNIT_DIR = os.path.expanduser("~/.config/systemd/user")


def _run(cmd, timeout=5):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def systemctl(*args):
    return _run(["systemctl", "--user", *args])


def autostart_status():
    out = {}
    for key, unit in UNITS.items():
        installed = os.path.exists(os.path.join(UNIT_DIR, unit))
        out[key] = {"unit": unit, "installed": installed,
                    "enabled": installed and systemctl("is-enabled", unit)[1] == "enabled",
                    "active": systemctl("is-active", unit)[1] == "active"}
    return out


def set_autostart(key, enabled):
    unit = UNITS.get(key)
    if not unit:
        raise ValueError(L("Неизвестный сервис", "Unknown service"))
    if not os.path.exists(os.path.join(UNIT_DIR, unit)):
        raise ValueError(L("Сервис не установлен — запусти ./install.sh",
                           "The service is not installed — run ./install.sh"))
    code, out = systemctl("enable" if enabled else "disable", unit)
    if code != 0:
        raise ValueError(out or L("systemctl завершился с ошибкой", "systemctl failed"))
    return autostart_status()


def restart_later(key):
    """Перезапуск сервиса без ожидания: сбор перезапускает сам себя, поэтому ответ
    должен уйти раньше, чем systemd нас остановит."""
    unit = UNITS.get(key)
    if not unit:
        raise ValueError(L("Неизвестный сервис", "Unknown service"))
    subprocess.Popen(["sh", "-c", f"sleep 0.7; systemctl --user restart --no-block {unit}"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def _collector_alive():
    """dbus-monitor с фильтром Notify среди процессов пользователя."""
    code, out = _run(["pgrep", "-u", str(os.getuid()), "-f", "dbus-monitor.*member='Notify'"])
    return code == 0 and bool(out)


def _proc_running(pattern):
    code, out = _run(["pgrep", "-u", str(os.getuid()), "-f", pattern])
    return code == 0 and bool(out)


def _gi_has(ns, ver):
    try:
        import gi
        gi.require_version(ns, ver)
        return True
    except (ImportError, ValueError):
        return False


def checks(db_path):
    res = []

    def add(cid, state, title, text, hint=""):
        res.append({"id": cid, "state": state, "title": title, "text": text, "hint": hint})

    st = autostart_status()
    alive = _collector_alive()
    add("collect", "ok" if alive else "bad", L("Сбор уведомлений", "Notification collector"),
        L("работает" if alive else "не запущен", "running" if alive else "not running"),
        "" if alive else L("Включи автозапуск ниже или запусти python3 collect.py",
                           "Enable autostart below or run python3 collect.py"))

    conn = sqlite3.connect(db_path, timeout=5)
    try:
        last = conn.execute("SELECT MAX(received_at) FROM messages").fetchone()[0]
        per = conn.execute("""SELECT app, COUNT(*), MAX(received_at) FROM messages
                              WHERE received_at >= ? GROUP BY app ORDER BY 2 DESC""",
                           (catcher.msk_time(24 * 7),)).fetchall()
        prefs = rules.get_prefs(conn)
        tg_recent = conn.execute("SELECT COUNT(*) FROM messages WHERE lower(app) LIKE '%telegram%' "
                                 "AND received_at >= ?", (catcher.msk_time(24 * 3),)).fetchone()[0]
    finally:
        conn.close()
    stale = not last or last < catcher.msk_time(24)
    add("last", "warn" if stale else "ok", L("Последнее уведомление", "Last notification"),
        last or L("ещё не было", "none yet"),
        L("Больше суток тишины — проверь, что приложения показывают уведомления",
          "Silent for over a day — check that apps show notifications") if stale else "")
    add("apps", "info", L("Кто присылал за 7 дней", "Who sent in 7 days"),
        ", ".join(f"{a} — {n}" for a, n, _ in per) or L("никто", "nobody"))

    code, out = _run(["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
                      "--object-path", "/org/freedesktop/Notifications", "--method",
                      "org.freedesktop.Notifications.GetServerInformation"])
    add("server", "ok" if code == 0 else "bad", L("Служба уведомлений", "Notification service"),
        out.strip("()").replace("'", "") if code == 0 else L("не отвечает", "not responding"))

    if _proc_running("telegram-desktop|Telegram") and not tg_recent:
        add("telegram", "warn", "Telegram",
            L("запущен, но его уведомлений за 3 дня нет", "running, but no notifications in 3 days"),
            L("Скорее всего, в Telegram выключены системные уведомления — см. «Справка → Telegram»",
              "Telegram probably uses its own pop-ups — see “Help → Telegram”"))

    session = os.environ.get("XDG_SESSION_TYPE") or ("wayland" if os.environ.get("WAYLAND_DISPLAY") else "x11")
    add("session", "ok" if session == "x11" else "warn", L("Сеанс рабочего стола", "Desktop session"),
        session, "" if session == "x11" else L(
            "На Wayland виджет не запоминает место и не держится под окнами — см. «Справка → Wayland»",
            "On Wayland the widget can't restore its position or stay below — see “Help → Wayland”"))

    libs = [("Gtk 3", _gi_has("Gtk", "3.0")), ("WebKit2 4.1", _gi_has("WebKit2", "4.1")),
            ("Wnck 3", _gi_has("Wnck", "3.0"))]
    missing = [n for n, ok in libs if not ok]
    add("libs", "ok" if not missing else ("bad" if "WebKit2 4.1" in missing or "Gtk 3" in missing else "warn"),
        L("Библиотеки виджета", "Widget libraries"),
        L("все на месте", "all present") if not missing else L("нет: ", "missing: ") + ", ".join(missing),
        "" if not missing else L("./install.sh подскажет, что поставить", "./install.sh tells what to install"))

    snd = shutil.which("canberra-gtk-play") or shutil.which("pw-play") or shutil.which("paplay")
    add("sound", "ok" if snd else "warn", L("Звук для правил", "Sound for rules"),
        os.path.basename(snd) if snd else L("нечем играть", "no player found"),
        "" if snd else L("Поставь пакет gnome-session-canberra или pipewire", "Install pipewire or libcanberra"))

    du = shutil.disk_usage(paths.DATA_DIR)
    size = sum(os.path.getsize(p) for p in (db_path, db_path + "-wal") if os.path.exists(p))
    add("disk", "ok" if du.free > 500 * 1024 ** 2 else "warn", L("Место", "Storage"),
        L(f"база {size / 1048576:.1f} МБ, свободно {du.free / 1024 ** 3:.1f} ГБ",
          f"database {size / 1048576:.1f} MB, free {du.free / 1024 ** 3:.1f} GB"))

    if prefs.get("mail_channel") == "imap":
        accs = mail.public_accounts()
        if not accs:
            add("mail", "warn", L("Почта", "Mail"), L("выбраны ящики, но ни одного не подключено",
                                                      "mailboxes chosen, but none connected"),
                L("Подключи ящик в «Почта» или верни канал «уведомления»",
                  "Add a mailbox under “Mail” or switch back to notifications"))
        for a in accs:
            st = "bad" if a.get("error") else ("ok" if a.get("enabled") else "info")
            txt = a.get("error") or (L("проверено ", "checked ") + a["checked"] if a.get("checked")
                                     else L("ещё не проверялся", "not checked yet"))
            add("mail-" + a["id"], st, L("Почта: ", "Mail: ") + a["label"], txt)

    bks = backup.list_backups()
    add("backup", "ok" if bks else ("warn" if prefs["backup"]["enabled"] else "info"),
        L("Резервные копии", "Backups"),
        (L("последняя: ", "latest: ") + bks[0]["at"]) if bks else L("ещё нет", "none yet"))

    for key, s in st.items():
        title = L("Автозапуск сбора", "Collector autostart") if key == "collect" else \
            L("Автозапуск виджета", "Widget autostart")
        if not s["installed"]:
            add("svc-" + key, "warn", title, L("не установлен", "not installed"),
                L("Запусти ./install.sh", "Run ./install.sh"))
        else:
            add("svc-" + key, "ok" if s["enabled"] else "info", title,
                L("включён" if s["enabled"] else "выключен", "enabled" if s["enabled"] else "disabled")
                + (L(", работает", ", running") if s["active"] else L(", остановлен", ", stopped")))
    return {"checks": res, "version": version.__version__, "python": sys.version.split()[0],
            "paths": {"code": paths.HERE, "data": paths.DATA_DIR, "config": paths.CONFIG_DIR,
                      "cache": paths.CACHE_DIR, "db": db_path},
            "autostart": st}
