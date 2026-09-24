#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Самодиагностика и автозапуск — для раздела «Система» в настройках.

checks() — список проверок {id, state: ok|warn|bad|info, title, text, hint}:
жив ли сбор, когда было последнее уведомление и от кого, что за служба
уведомлений, известные ловушки (Telegram без системных уведомлений, Wayland),
библиотеки, звук, место на диске, копии, умный поиск.

Автозапуск — это юниты systemd --user (<APP_ID>.service — сбор, <APP_ID>-widget.service
— виджет): включить/выключить = systemctl --user enable/disable. На Windows сбор и виджет —
один процесс messhub.exe, автозапуск — значение в HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
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
WINDOWS = os.name == "nt"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WEBVIEW2 = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


def _run(cmd, timeout=5):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def systemctl(*args):
    return _run(["systemctl", "--user", *args])


def _unit(unit):
    """Юнит из ~/.config/systemd/user (./install.sh) или /usr/lib/systemd/user (пакет .deb/.rpm)."""
    code, out = systemctl("show", unit, "-p", "FragmentPath", "-p", "UnitFileState", "-p", "ActiveState")
    info = dict(line.split("=", 1) for line in out.splitlines() if "=" in line) if code == 0 else {}
    return {"unit": unit, "installed": bool(info.get("FragmentPath")),
            "enabled": info.get("UnitFileState") == "enabled", "active": info.get("ActiveState") == "active"}


def autostart_status():
    if WINDOWS:
        return {"collect": _win_autostart()}
    return {key: _unit(unit) for key, unit in UNITS.items()}


# ── Windows: автозапуск через реестр, перезапуск — новым процессом ────────────

def win_command():
    """Чем запускать messhub на Windows: сама сборка messhub.exe или pythonw + messhub_win.py."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return f'"{pyw if os.path.exists(pyw) else sys.executable}" "{os.path.join(paths.HERE, "messhub_win.py")}"'


def _win_autostart():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            enabled = bool(winreg.QueryValueEx(k, version.APP_ID)[0])
    except OSError:
        enabled = False
    import wincatcher
    return {"unit": "HKCU\\" + RUN_KEY + "\\" + version.APP_ID, "installed": True, "enabled": enabled,
            "active": wincatcher.status["running"]}


def _win_set_autostart(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, version.APP_ID, 0, winreg.REG_SZ, win_command())
        else:
            try:
                winreg.DeleteValue(k, version.APP_ID)
            except OSError:
                pass


def _webview2_version():
    import winreg
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\WOW6432Node\\" + WEBVIEW2),
                      (winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\" + WEBVIEW2),
                      (winreg.HKEY_CURRENT_USER, "Software\\" + WEBVIEW2)):
        try:
            with winreg.OpenKey(root, key) as k:
                v = winreg.QueryValueEx(k, "pv")[0]
                if v and v != "0.0.0.0":
                    return v
        except OSError:
            continue
    return ""


def set_autostart(key, enabled):
    if WINDOWS:
        _win_set_autostart(enabled)
        return autostart_status()
    unit = UNITS.get(key)
    if not unit:
        raise ValueError(L("Неизвестный сервис", "Unknown service"))
    if not _unit(unit)["installed"]:
        raise ValueError(L("Сервис не установлен — запусти ./install.sh или поставь пакет",
                           "The service is not installed — run ./install.sh or install the package"))
    code, out = systemctl("enable" if enabled else "disable", unit)
    if code != 0:
        raise ValueError(out or L("systemctl завершился с ошибкой", "systemctl failed"))
    return autostart_status()


def restart_later(key):
    """Перезапуск сервиса без ожидания: сбор перезапускает сам себя, поэтому ответ
    должен уйти раньше, чем systemd нас остановит."""
    if WINDOWS:          # новый messhub.exe подождёт, пока этот отпустит порт (--wait-port)
        import threading
        subprocess.Popen(f"{win_command()} --wait-port", creationflags=0x00000008 | 0x00000200)  # DETACHED | NEW_GROUP
        threading.Timer(0.7, lambda: os._exit(0)).start()
        return
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
    if WINDOWS:
        _win_checks(add)
    else:
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
        accs = mail.public_accounts(conn) if prefs.get("mail_channel") == "imap" else []
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

    if not WINDOWS:
        _linux_checks(add, tg_recent)
    _common_checks(add, db_path, prefs, accs)
    for key, s in st.items():
        title = L("Автозапуск сбора", "Collector autostart") if key == "collect" else \
            L("Автозапуск виджета", "Widget autostart")
        if WINDOWS:
            title = L("Запуск при входе в Windows", "Start with Windows")
        if not s["installed"]:
            add("svc-" + key, "warn", title, L("не установлен", "not installed"),
                L("Запусти ./install.sh", "Run ./install.sh"))
        else:
            add("svc-" + key, "ok" if s["enabled"] else "info", title,
                L("включён" if s["enabled"] else "выключен", "enabled" if s["enabled"] else "disabled")
                + (L(", работает", ", running") if s["active"] else L(", остановлен", ", stopped")))
    return {"checks": res, "version": version.__version__, "python": sys.version.split()[0],
            "platform": "windows" if WINDOWS else "linux",
            "paths": {"code": paths.HERE, "data": paths.DATA_DIR, "config": paths.CONFIG_DIR,
                      "cache": paths.CACHE_DIR, "db": db_path},
            "autostart": st}


def _win_checks(add):
    import wincatcher
    s = wincatcher.status
    add("collect", "ok" if s["running"] else "bad", L("Сбор уведомлений", "Notification collector"),
        L("работает" if s["running"] else "не запущен", "running" if s["running"] else "not running"))
    acc = wincatcher.access_status()
    text = {"allowed": L("разрешён", "allowed"), "denied": L("запрещён", "denied"),
            "unspecified": L("ещё не спрашивали", "not asked yet"),
            "unavailable": L("недоступен", "unavailable")}.get(acc, acc)
    hint = {"denied": L("Параметры Windows → Конфиденциальность и защита → Уведомления: разрешить messhub. "
                        "Без этого Windows не показывает программе уведомления",
                        "Windows Settings → Privacy & security → Notifications: allow messhub"),
            "unspecified": L("Перезапусти messhub — Windows спросит разрешение",
                             "Restart messhub — Windows will ask for permission"),
            "unavailable": L("Нужна Windows 10 версии 1809 или новее, или Windows 11",
                             "Needs Windows 10 version 1809 or newer, or Windows 11")}.get(acc, "")
    add("access", "ok" if acc == "allowed" else "bad", L("Доступ к уведомлениям", "Notification access"),
        text, hint)
    if s.get("error"):
        add("listener", "warn", L("Чтение уведомлений", "Reading notifications"), s["error"])
    wv = _webview2_version()
    add("webview2", "ok" if wv else "bad", "WebView2", wv or L("не установлен", "not installed"),
        "" if wv else L("Поставь Microsoft Edge WebView2 Runtime с сайта Microsoft — без него доска не откроется",
                        "Install Microsoft Edge WebView2 Runtime — the board needs it"))


def _linux_checks(add, tg_recent):
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


def _common_checks(add, db_path, prefs, accs):
    du = shutil.disk_usage(os.path.dirname(os.path.abspath(db_path)))      # диск, где лежит база
    size = sum(os.path.getsize(p) for p in (db_path, db_path + "-wal") if os.path.exists(p))
    add("disk", "ok" if du.free > 500 * 1024 ** 2 else "warn", L("Место", "Storage"),
        L(f"база {size / 1048576:.1f} МБ, свободно {du.free / 1024 ** 3:.1f} ГБ",
          f"database {size / 1048576:.1f} MB, free {du.free / 1024 ** 3:.1f} GB"))

    if prefs.get("mail_channel") == "imap":
        if not accs:
            add("mail", "warn", L("Почта", "Mail"), L("выбраны ящики, но ни одного не подключено",
                                                      "mailboxes chosen, but none connected"),
                L("Подключи ящик в «Почта» или верни канал «уведомления»",
                  "Add a mailbox under “Mail” or switch back to notifications"))
        for a in accs:
            state = "bad" if a.get("error") else ("ok" if a.get("enabled") else "info")
            txt = a.get("error") or (L("проверено ", "checked ") + a["checked"] if a.get("checked")
                                     else L("ещё не проверялся", "not checked yet"))
            add("mail-" + a["id"], state, L("Почта: ", "Mail: ") + a["label"], txt)

    bks = backup.list_backups()
    add("backup", "ok" if bks else ("warn" if prefs["backup"]["enabled"] else "info"),
        L("Резервные копии", "Backups"),
        (L("последняя: ", "latest: ") + bks[0]["at"]) if bks else L("ещё нет", "none yet"))

