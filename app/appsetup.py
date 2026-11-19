#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика и настройка уведомлений приложений и браузеров (раздел «Подключение приложений»).

Зачем. Даже когда сам messhub работает исправно, уведомления конкретного браузера или
мессенджера могут не доходить до виджета, потому что:
  • на уровне ОС (GNOME «Уведомления» / параметры Windows) уведомления для этого
    приложения или браузера выключены или отключены баннеры;
  • в самом браузере (Chrome, Яндекс, Chromium, Brave, Edge, Firefox, Vivaldi, Opera)
    запрещены уведомления глобально или заблокирован конкретный сайт (web.telegram.org,
    max.ru, whatsapp.com и т.д.);
  • в Telegram Desktop на Linux не включена галочка «Использовать системные уведомления».

Только локальное чтение настроек разрешений уведомлений (историю браузера, пароли, cookie
и файлы сообщений программ не читаем); по клику пользователя:
  • включение/выключение уведомлений приложения в GNOME (gsettings);
  • открытие системных настроек уведомлений или страницы настроек уведомлений браузера;
  • отправка пробного уведомления с проверкой, что оно дошло до БД messhub.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
import urllib.parse

import catcher
import diag
import quiet
import rules
from i18n import L

WINDOWS = os.name == "nt"
_SAFE_SLUG = re.compile(r"^[a-zA-Z0-9._-]+$")
_KNOWN_DOMAINS = tuple((dom, key, name) for dom, key, name, _, _ in rules.SITES)

# Известные браузеры: id, отображаемое имя, ключи в БД/GNOME, пути конфигов, URL настроек уведомлений
BROWSERS = (
    {
        "id": "chrome",
        "name": "Google Chrome",
        "kind": "chromium",
        "url": "chrome://settings/content/notifications",
        "bins": ("google-chrome", "google-chrome-stable"),
        "apps": ("google-chrome", "chrome"),
        "gnome_ids": ("google-chrome", "google-chrome.desktop"),
        "linux_dirs": ("~/.config/google-chrome", "~/.var/app/com.google.Chrome/config/google-chrome"),
        "win_dirs": (r"%LOCALAPPDATA%\Google\Chrome\User Data",),
        "win_aumid": ("Chrome", "Google.Chrome"),
    },
    {
        "id": "yandex",
        "name": "Яндекс Браузер",
        "name_en": "Yandex Browser",
        "kind": "chromium",
        "url": "browser://settings/content/notifications",
        "bins": ("yandex-browser", "yandex-browser-stable", "yandex-browser-beta"),
        "apps": ("yandex",),
        "gnome_ids": ("yandex-browser", "yandex-browser-beta", "yandex-browser.desktop"),
        "linux_dirs": ("~/.config/yandex-browser", "~/.config/yandex-browser-beta"),
        "win_dirs": (r"%LOCALAPPDATA%\Yandex\YandexBrowser\User Data",),
        "win_aumid": ("Yandex",),
    },
    {
        "id": "firefox",
        "name": "Firefox",
        "kind": "firefox",
        "url": "about:preferences#privacy",
        "bins": ("firefox", "firefox-esr"),
        "apps": ("firefox",),
        "gnome_ids": ("firefox", "firefox-firefox", "firefox_firefox", "org.mozilla.firefox"),
        "linux_dirs": ("~/.mozilla/firefox", "~/snap/firefox/common/.mozilla/firefox",
                       "~/.var/app/org.mozilla.firefox/.mozilla/firefox"),
        "win_dirs": (r"%APPDATA%\Mozilla\Firefox\Profiles",),
        "win_aumid": ("Firefox", "Mozilla.Firefox"),
    },
    {
        "id": "chromium",
        "name": "Chromium",
        "kind": "chromium",
        "url": "chrome://settings/content/notifications",
        "bins": ("chromium", "chromium-browser"),
        "apps": ("chromium",),
        "gnome_ids": ("chromium", "chromium-browser", "chromium-chromium", "chromium_chromium"),
        "linux_dirs": ("~/.config/chromium", "~/snap/chromium/common/chromium",
                       "~/.var/app/org.chromium.Chromium/config/chromium"),
        "win_dirs": (r"%LOCALAPPDATA%\Chromium\User Data",),
        "win_aumid": ("Chromium",),
    },
    {
        "id": "edge",
        "name": "Microsoft Edge",
        "kind": "chromium",
        "url": "edge://settings/content/notifications",
        "bins": ("microsoft-edge", "microsoft-edge-stable"),
        "apps": ("edge", "msedge"),
        "gnome_ids": ("microsoft-edge", "microsoft-edge.desktop"),
        "linux_dirs": ("~/.config/microsoft-edge", "~/.var/app/com.microsoft.Edge/config/microsoft-edge"),
        "win_dirs": (r"%LOCALAPPDATA%\Microsoft\Edge\User Data",),
        "win_aumid": ("MSEdge",),
    },
    {
        "id": "brave",
        "name": "Brave",
        "kind": "chromium",
        "url": "brave://settings/content/notifications",
        "bins": ("brave-browser", "brave"),
        "apps": ("brave",),
        "gnome_ids": ("brave-browser", "com.brave.Browser"),
        "linux_dirs": ("~/.config/BraveSoftware/Brave-Browser",
                       "~/.var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser"),
        "win_dirs": (r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data",),
        "win_aumid": ("Brave",),
    },
    {
        "id": "vivaldi",
        "name": "Vivaldi",
        "kind": "chromium",
        "url": "vivaldi://settings/content/notifications",
        "bins": ("vivaldi", "vivaldi-stable"),
        "apps": ("vivaldi",),
        "gnome_ids": ("vivaldi-stable", "vivaldi"),
        "linux_dirs": ("~/.config/vivaldi",),
        "win_dirs": (r"%LOCALAPPDATA%\Vivaldi\User Data",),
        "win_aumid": ("Vivaldi",),
    },
    {
        "id": "opera",
        "name": "Opera",
        "kind": "chromium",
        "url": "opera://settings/content/notifications",
        "bins": ("opera",),
        "apps": ("opera",),
        "gnome_ids": ("opera",),
        "linux_dirs": ("~/.config/opera",),
        "win_dirs": (r"%APPDATA%\Opera Software\Opera Stable",),
        "win_aumid": ("Opera",),
    },
)


def _known_site(host):
    """Относится ли домен к известным веб-мессенджерам/почтам (rules.SITES); личные сайты не светим."""
    h = (host or "").strip().lower().split(":")[0]
    if not h:
        return None
    for dom, key, name in _KNOWN_DOMAINS:
        if h == dom or h.endswith("." + dom):
            return {"domain": h, "key": key, "name": name[1] if L("ru", "en") == "en" else name[0]}
    return None


def _host_from_pattern(pat):
    s = str(pat or "").split(",")[0].strip()
    if not s or s == "*":
        return ""
    if "://" in s:
        p = urllib.parse.urlparse(s)
        return p.hostname or ""
    return s.split("/")[0].split(":")[0]


def parse_chromium_prefs(data):
    """Разобрать ключи уведомлений из Chromium Preferences (dict). Личные домены не отдаём."""
    prof = data.get("profile") if isinstance(data, dict) else None
    if not isinstance(prof, dict):
        return {"default": "unknown", "sites": [], "allowed_total": 0, "blocked_total": 0}
    dval = (prof.get("default_content_setting_values") or {}).get("notifications")
    default = {1: "allowed", 2: "blocked", 3: "ask"}.get(dval, "ask")
    exc = (prof.get("content_settings") or {}).get("exceptions") or {}
    notifs = exc.get("notifications") or {}
    allowed_total = blocked_total = 0
    seen = {}
    if isinstance(notifs, dict):
        for pat, info in notifs.items():
            setting = info.get("setting") if isinstance(info, dict) else None
            if setting not in (1, 2):
                continue
            status = "allowed" if setting == 1 else "blocked"
            if status == "allowed":
                allowed_total += 1
            else:
                blocked_total += 1
            known = _known_site(_host_from_pattern(pat))
            if known:
                prev = seen.get(known["domain"])
                # если сайт заблокирован хотя бы в одном правиле, считаем предупреждением
                if not prev or prev["status"] != "blocked":
                    seen[known["domain"]] = {**known, "status": status}
    sites = sorted(seen.values(), key=lambda s: (s["status"] != "blocked", s["name"], s["domain"]))
    return {"default": default, "sites": sites, "allowed_total": allowed_total, "blocked_total": blocked_total}


def _read_chromium(user_data_dir):
    profiles = []
    if not os.path.isdir(user_data_dir):
        return profiles
    try:
        entries = sorted(os.listdir(user_data_dir))
    except OSError:
        return profiles
    cand = [e for e in entries if e == "Default" or e.startswith("Profile ")]
    for name in cand[:6]:
        pfile = os.path.join(user_data_dir, name, "Preferences")
        if not os.path.isfile(pfile):
            continue
        try:
            with open(pfile, encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        parsed = parse_chromium_prefs(data)
        prof_name = ((data.get("profile") or {}).get("name") or name).strip() or name
        profiles.append({"name": prof_name, "dir": name, **parsed})
    return profiles


def parse_firefox_prefs(text):
    """Разобрать уведомления в prefs.js Firefox → (enabled: bool, default: ask|allowed|blocked)."""
    enabled = True
    default = "ask"
    m = re.search(r'user_pref\(\s*"dom\.webnotifications\.enabled"\s*,\s*(true|false)\s*\)', text or "")
    if m:
        enabled = m.group(1) == "true"
    m2 = re.search(r'user_pref\(\s*"permissions\.default\.desktop-notification"\s*,\s*(\d+)\s*\)', text or "")
    if m2:
        default = {"1": "allowed", "2": "blocked"}.get(m2.group(1), "ask")
    return enabled, default


def _read_firefox(base_dir):
    profiles = []
    if not os.path.isdir(base_dir):
        return profiles
    try:
        entries = sorted(os.listdir(base_dir))
    except OSError:
        return profiles
    for name in entries[:8]:
        pdir = os.path.join(base_dir, name)
        if not os.path.isdir(pdir):
            continue
        prefs_path = os.path.join(pdir, "prefs.js")
        perms_path = os.path.join(pdir, "permissions.sqlite")
        if not (os.path.isfile(prefs_path) or os.path.isfile(perms_path)):
            continue
        enabled, default = True, "ask"
        if os.path.isfile(prefs_path):
            try:
                with open(prefs_path, encoding="utf-8", errors="replace") as f:
                    enabled, default = parse_firefox_prefs(f.read())
            except OSError:
                pass
        if not enabled:
            default = "blocked"
        allowed_total = blocked_total = 0
        seen = {}
        if os.path.isfile(perms_path):
            uri = f"file:{urllib.parse.quote(perms_path)}?mode=ro&immutable=1"
            try:
                conn = sqlite3.connect(uri, uri=True, timeout=1)
                try:
                    rows = conn.execute(
                        "SELECT origin, permission FROM moz_perms WHERE type = 'desktop-notification'"
                    ).fetchall()
                finally:
                    conn.close()
                for origin, perm in rows:
                    if perm not in (1, 2):
                        continue
                    status = "allowed" if perm == 1 else "blocked"
                    if status == "allowed":
                        allowed_total += 1
                    else:
                        blocked_total += 1
                    known = _known_site(_host_from_pattern(origin))
                    if known:
                        seen[known["domain"]] = {**known, "status": status}
            except sqlite3.Error:
                pass
        label = name.split(".", 1)[1] if "." in name else name
        sites = sorted(seen.values(), key=lambda s: (s["status"] != "blocked", s["name"], s["domain"]))
        profiles.append({"name": label, "dir": name, "default": default, "sites": sites,
                         "allowed_total": allowed_total, "blocked_total": blocked_total})
    return profiles


def parse_gnome_children(out):
    return [s for s in re.findall(r"'([^']+)'", out or "") if _SAFE_SLUG.match(s)]


def parse_gnome_app_lines(out):
    """Разобрать вывод gsettings list-recursively org.gnome.desktop.notifications.application:..."""
    res = {"app_id": "", "enable": True, "banners": True}
    for line in (out or "").splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        key, val = parts[1], parts[2].strip()
        if key == "application-id":
            res["app_id"] = val.strip("'\"")
        elif key == "enable":
            res["enable"] = val == "true"
        elif key == "show-banners":
            res["banners"] = val == "true"
    return res


def _gnome_apps():
    """Все приложения из GNOME «Настройки → Уведомления» → {slug: {slug, app_id, enable, banners}}."""
    if WINDOWS or not shutil.which("gsettings"):
        return {}
    code, out = diag._run(["gsettings", "get", "org.gnome.desktop.notifications", "application-children"])
    if code != 0:
        return {}
    apps = {}
    for slug in parse_gnome_children(out):
        path = f"org.gnome.desktop.notifications.application:/org/gnome/desktop/notifications/application/{slug}/"
        c2, out2 = diag._run(["gsettings", "list-recursively", path])
        if c2 != 0:
            continue
        info = parse_gnome_app_lines(out2)
        apps[slug] = {"slug": slug, **info}
    return apps


def _match_gnome(gnome_apps, candidate_ids):
    """Найти запись GNOME по возможным application-id / slug."""
    cands = [c.lower() for c in candidate_ids]
    for slug, info in gnome_apps.items():
        aid = info["app_id"].lower().removesuffix(".desktop")
        sl = slug.lower()
        if sl in cands or aid in cands or any(aid.startswith(c + "_") or sl.startswith(c + "-") for c in cands):
            return info
    return None


def _win_toast_enabled():
    if not WINDOWS:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\PushNotifications") as k:
            return bool(winreg.QueryValueEx(k, "ToastEnabled")[0])
    except OSError:
        return True


def _win_app_enabled(prefixes):
    if not WINDOWS or not prefixes:
        return None
    try:
        import winreg
        base = r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base) as root:
            n = winreg.QueryInfoKey(root)[0]
            for i in range(n):
                sub = winreg.EnumKey(root, i)
                if any(p.lower() in sub.lower() for p in prefixes):
                    try:
                        with winreg.OpenKey(root, sub) as ak:
                            val = winreg.QueryValueEx(ak, "Enabled")[0]
                            return bool(val)
                    except OSError:
                        return True
    except OSError:
        pass
    return None


def _expand(p):
    return os.path.expanduser(os.path.expandvars(p))


def _system_info():
    if WINDOWS:
        import wincatcher
        acc = wincatcher.access_status()
        toast = _win_toast_enabled()
        return {
            "platform": "windows",
            "desktop": "windows",
            "collector": bool(wincatcher.status["running"]),
            "win_access": acc,
            "win_toast": toast,
            "dnd": None,
            "dbus_ok": True,
            "notify_send": True,
            "can_open_os": True,
        }
    dbus_code, dbus_out = diag._run([
        "gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
        "--object-path", "/org/freedesktop/Notifications",
        "--method", "org.freedesktop.Notifications.GetServerInformation",
    ])
    dnd = quiet.gnome_dnd()
    desk = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    desktop = "gnome" if ("gnome" in desk or dnd is not None) else ("kde" if "kde" in desk else "other")
    return {
        "platform": "linux",
        "desktop": desktop,
        "collector": diag._collector_alive(),
        "dbus_ok": dbus_code == 0,
        "dbus_server": dbus_out.strip("()").replace("'", "") if dbus_code == 0 else "",
        "dnd": dnd,
        "notify_send": bool(shutil.which("notify-send")),
        "can_open_os": bool(shutil.which("gnome-control-center")),
    }


def _inspect_browsers(gnome_apps, recent_rows, sys_info):
    out = []
    matched_slugs = set()
    en = L("ru", "en") == "en"
    for b in BROWSERS:
        dirs = b["win_dirs"] if WINDOWS else b["linux_dirs"]
        profiles = []
        for raw_d in dirs:
            d = _expand(raw_d)
            if not os.path.isdir(d):
                continue
            profiles.extend(_read_firefox(d) if b["kind"] == "firefox" else _read_chromium(d))
        has_bin = any(shutil.which(x) for x in b["bins"])
        ginfo = _match_gnome(gnome_apps, b["gnome_ids"]) if gnome_apps else None
        if ginfo:
            matched_slugs.add(ginfo["slug"])
        win_on = _win_app_enabled(b.get("win_aumid")) if WINDOWS else None

        rec_n, rec_last = 0, ""
        for app, _site, cnt, last_at in recent_rows:
            al = (app or "").lower()
            if any(m in al for m in b["apps"]):
                rec_n += cnt
                if last_at > rec_last:
                    rec_last = last_at

        if not (profiles or has_bin or ginfo or rec_n):
            continue

        os_blocked = (ginfo is not None and not ginfo["enable"]) or (win_on is False)
        os_no_banners = ginfo is not None and ginfo["enable"] and not ginfo["banners"]
        glob_blocked = any(p["default"] == "blocked" for p in profiles)
        blocked_sites = [s for p in profiles for s in p["sites"] if s["status"] == "blocked"]
        allowed_sites = [s for p in profiles for s in p["sites"] if s["status"] == "allowed"]

        if os_blocked or glob_blocked:
            state = "bad"
        elif os_no_banners or blocked_sites:
            state = "warn"
        elif rec_n or allowed_sites:
            state = "ok"
        else:
            state = "info"

        hints = []
        if ginfo is not None and not ginfo["enable"]:
            hints.append(L("Уведомления браузера выключены в настройках GNOME — нажми «Включить в системе».",
                           "Browser notifications are disabled in GNOME Settings — click “Enable in system”."))
        elif os_no_banners:
            hints.append(L("В GNOME выключены баннеры этого браузера — проверь настройки уведомлений системы.",
                           "Banners for this browser are off in GNOME — check system notification settings."))
        if win_on is False:
            hints.append(L("Уведомления этого браузера выключены в Параметрах Windows → Уведомления.",
                           "This browser's notifications are off in Windows Settings → Notifications."))
        if glob_blocked:
            hints.append(L(f"В самом браузере сайтам запрещено показывать уведомления. Открой {b['url']} и включи разрешение для нужных мессенджеров.",
                           f"Notifications are globally blocked in this browser. Open {b['url']} and allow notifications for your messengers."))
        elif blocked_sites:
            names = ", ".join(s["domain"] for s in blocked_sites[:4])
            hints.append(L(f"В браузере заблокированы уведомления для: {names}. Разблокируй их на странице {b['url']}.",
                           f"Notifications are blocked in the browser for: {names}. Allow them at {b['url']}."))
        elif not allowed_sites and not rec_n:
            hints.append(L(f"Если веб-чат (Telegram Web, MAX, почта) не шлёт уведомления — открой сайт, нажми на замочек слева от адреса → «Уведомления → Разрешить», или проверь {b['url']}.",
                           f"If web chats don't send notifications, open the site, click the lock icon in the address bar → Notifications → Allow, or check {b['url']}."))
        if WINDOWS and sys_info["platform"] == "windows":
            hints.append(L("На Windows сам сайт (web.telegram.org) нужно открыть в фоне, и в колонке Chrome все сайты можно разделить на подколонки.",
                           "On Windows, web notifications go under the browser column; you can split columns by sub-source."))

        out.append({
            "id": b["id"],
            "name": b["name_en"] if (en and "name_en" in b) else b["name"],
            "kind": b["kind"],
            "settings_url": b["url"],
            "can_open": has_bin,
            "gnome": ginfo,
            "win_enabled": win_on,
            "profiles": profiles,
            "recent_count": rec_n,
            "last_seen": rec_last,
            "state": state,
            "hints": hints,
        })
    return out, matched_slugs


def _inspect_apps(gnome_apps, matched_slugs, recent_rows, prefs):
    """Основные мессенджеры и почтовые клиенты + отключённые в GNOME приложения."""
    apps_out = []

    def recent_for(*marks):
        n, last = 0, ""
        for app, _site, cnt, at in recent_rows:
            al = (app or "").lower()
            if any(m in al for m in marks):
                n += cnt
                if at > last:
                    last = at
        return n, last

    # 1. Telegram Desktop
    tg_bin = (shutil.which("telegram-desktop") or shutil.which("Telegram")
              or (os.path.exists("/snap/bin/telegram-desktop"))
              or (not WINDOWS and os.path.isdir(os.path.expanduser("~/snap/telegram-desktop")))
              or (not WINDOWS and os.path.isdir(os.path.expanduser("~/.var/app/org.telegram.desktop"))))
    tg_running = False if WINDOWS else diag._proc_running(r"telegram-desktop|Telegram")
    tg_gnome = _match_gnome(gnome_apps, ("telegram-desktop", "telegram-desktop-telegram-desktop",
                                         "telegram-desktop_telegram-desktop", "org.telegram.desktop"))
    if tg_gnome:
        matched_slugs.add(tg_gnome["slug"])
    tg_win = _win_app_enabled(("Telegram",)) if WINDOWS else None
    tg_n, tg_last = recent_for("telegram")
    tg_hints = []
    if prefs.get("telegram_channel") == "mtproto":
        tg_hints.append(L("Сейчас выбран прямой канал Telegram (MTProto), поэтому системные уведомления Telegram Desktop пропускаются во избежание дублей.",
                          "Telegram channel is set to direct MTProto, so Telegram Desktop system notifications are skipped to avoid duplicates."))
    if tg_gnome and not tg_gnome["enable"]:
        tg_hints.append(L("Уведомления Telegram выключены в настройках GNOME — нажми «Включить в системе».",
                          "Telegram notifications are disabled in GNOME Settings — click “Enable in system”."))
    if tg_win is False:
        tg_hints.append(L("Уведомления Telegram выключены в Параметрах Windows → Уведомления.",
                          "Telegram notifications are off in Windows Settings → Notifications."))
    if not WINDOWS and (tg_running or tg_bin or tg_gnome) and not tg_n:
        tg_hints.append(L(
            "Telegram Desktop по умолчанию рисует свои плашки мимо системы! Открой в Telegram: "
            "Настройки → Уведомления и звуки → Взаимодействие с системой → включи «Использовать системные уведомления». "
            "Экспериментальную опцию GNotification включать НЕ нужно.",
            "On Linux, Telegram Desktop uses custom pop-ups by default. Enable: Settings → Notifications and Sounds → "
            "System integration → Use native notifications. Do NOT enable GNotification."))
    else:
        tg_hints.append(L(
            "Убедись, что включены показ имени отправителя и текста сообщения (иначе приходит только «Новое сообщение»). "
            "Если окно Telegram открыто на конкретном чате, уведомления из этого чата не отправляются.",
            "Keep sender name and message preview enabled. Note: Telegram suppresses notifications for the currently open chat."))
    if tg_bin or tg_running or tg_gnome or tg_n or tg_win is not None:
        tg_state = "bad" if (tg_gnome and not tg_gnome["enable"]) or tg_win is False else \
            ("warn" if (not WINDOWS and tg_running and not tg_n) else ("ok" if tg_n else "info"))
        apps_out.append({
            "id": "telegram", "name": "Telegram Desktop", "ico": "✈️",
            "installed": bool(tg_bin or tg_running or tg_gnome or tg_n), "running": tg_running,
            "gnome": tg_gnome, "win_enabled": tg_win,
            "recent_count": tg_n, "last_seen": tg_last, "state": tg_state, "hints": tg_hints,
        })

    # 2. eXpress
    ex_running = False if WINDOWS else diag._proc_running(r"express")
    ex_gnome = _match_gnome(gnome_apps, ("express",))
    if ex_gnome:
        matched_slugs.add(ex_gnome["slug"])
    ex_win = _win_app_enabled(("eXpress",)) if WINDOWS else None
    ex_n, ex_last = recent_for("express")
    ex_hints = []
    if ex_gnome and not ex_gnome["enable"]:
        ex_hints.append(L("Уведомления eXpress выключены в настройках GNOME — нажми «Включить в системе».",
                          "eXpress notifications are disabled in GNOME Settings."))
    ex_hints.append(L("Если уведомления не приходят — проверь в самом eXpress «Настройки → Уведомления» (что звук/всплывающие окна включены и чат не в mute).",
                      "Make sure desktop notifications are enabled in eXpress settings and the chat is not muted."))
    if ex_running or ex_gnome or ex_n or ex_win is not None:
        ex_state = "bad" if (ex_gnome and not ex_gnome["enable"]) or ex_win is False else ("ok" if ex_n else "info")
        apps_out.append({
            "id": "express", "name": "eXpress", "ico": "💬",
            "installed": True, "running": ex_running,
            "gnome": ex_gnome, "win_enabled": ex_win,
            "recent_count": ex_n, "last_seen": ex_last, "state": ex_state, "hints": ex_hints,
        })

    # 3. Почтовые клиенты
    mail_apps = (("thunderbird", "Thunderbird", ("thunderbird",)),
                 ("evolution", "Evolution", ("evolution", "org.gnome.evolution")),
                 ("geary", "Geary", ("geary", "org.gnome.geary")))
    for mid, mname, mkeys in mail_apps:
        has_m = any(shutil.which(k) for k in mkeys if "." not in k)
        gm = _match_gnome(gnome_apps, mkeys)
        if gm:
            matched_slugs.add(gm["slug"])
        mn, mlast = recent_for(*mkeys)
        if has_m or gm or mn:
            hints = []
            if prefs.get("mail_channel") == "imap":
                hints.append(L("Сейчас канал почты — «Ящики (IMAP)», поэтому уведомления почтовых программ намеренно пропускаются, чтобы не дублировать письма.",
                               "Mail channel is currently set to IMAP mailboxes, so mail app notifications are intentionally skipped."))
            elif gm and not gm["enable"]:
                hints.append(L("Уведомления выключены в GNOME Settings — нажми «Включить в системе».",
                               "Notifications are disabled in GNOME Settings."))
            else:
                hints.append(L("Включи показ системных уведомлений о новых письмах в настройках программы (или подключи ящик напрямую в разделе «Почта»).",
                               "Enable new-mail system notifications in the app (or connect your mailbox directly under “Mail”)."))
            mstate = "bad" if (gm and not gm["enable"]) else ("ok" if mn else "info")
            apps_out.append({
                "id": mid, "name": mname, "ico": "✉️",
                "installed": bool(has_m or gm or mn), "running": False,
                "gnome": gm, "win_enabled": None,
                "recent_count": mn, "last_seen": mlast, "state": mstate, "hints": hints,
            })

    # Любые другие приложения, явно выключенные пользователем в GNOME
    gnome_disabled = sorted(
        (info for slug, info in gnome_apps.items() if slug not in matched_slugs and not info["enable"]),
        key=lambda x: x["slug"],
    )
    return apps_out, gnome_disabled


def _demo_data():
    """Вымышленные данные для скриншотов (MESSHUB_THEMED_DEMO=1) — без чтения реальной системы."""
    en = L("ru", "en") == "en"
    return {
        "system": {
            "platform": "linux", "desktop": "gnome", "collector": True,
            "dbus_ok": True, "dbus_server": "gnome-shell, GNOME, 46", "dnd": False,
            "notify_send": True, "can_open_os": True,
        },
        "browsers": [
            {
                "id": "chrome", "name": "Google Chrome", "kind": "chromium",
                "settings_url": "chrome://settings/content/notifications", "can_open": True,
                "gnome": {"slug": "google-chrome", "app_id": "google-chrome.desktop", "enable": True, "banners": True},
                "win_enabled": None,
                "profiles": [{
                    "name": "Person 1" if en else "Профиль 1", "dir": "Default", "default": "ask",
                    "sites": [
                        {"domain": "web.telegram.org", "key": "telegram", "name": "Telegram", "status": "blocked"},
                        {"domain": "web.max.ru", "key": "max", "name": "MAX", "status": "allowed"},
                        {"domain": "mail.google.com", "key": "mail", "name": "Mail" if en else "Почта", "status": "allowed"},
                    ],
                    "allowed_total": 4, "blocked_total": 2,
                }],
                "recent_count": 42, "last_seen": "2026-09-25 14:10:00", "state": "warn",
                "hints": [L("В браузере заблокированы уведомления для: web.telegram.org. Разблокируй их на странице chrome://settings/content/notifications.",
                            "Notifications are blocked in the browser for: web.telegram.org. Allow them at chrome://settings/content/notifications.")],
            },
            {
                "id": "firefox", "name": "Firefox", "kind": "firefox",
                "settings_url": "about:preferences#privacy", "can_open": True,
                "gnome": {"slug": "firefox-firefox", "app_id": "firefox_firefox.desktop", "enable": False, "banners": True},
                "win_enabled": None,
                "profiles": [{"name": "default", "dir": "default", "default": "ask", "sites": [],
                              "allowed_total": 0, "blocked_total": 0}],
                "recent_count": 0, "last_seen": "", "state": "bad",
                "hints": [L("Уведомления браузера выключены в настройках GNOME — нажми «Включить в системе».",
                            "Browser notifications are disabled in GNOME Settings — click “Enable in system”.")],
            },
        ],
        "apps": [
            {
                "id": "telegram", "name": "Telegram Desktop", "ico": "✈️",
                "installed": True, "running": True,
                "gnome": {"slug": "telegram-desktop-telegram-desktop",
                          "app_id": "telegram-desktop_telegram-desktop.desktop", "enable": True, "banners": True},
                "win_enabled": None, "recent_count": 118, "last_seen": "2026-09-25 14:22:00", "state": "ok",
                "hints": [L("Убедись, что включены показ имени отправителя и текста сообщения.",
                            "Keep sender name and message preview enabled.")],
            },
            {
                "id": "express", "name": "eXpress", "ico": "💬",
                "installed": True, "running": True, "gnome": None, "win_enabled": None,
                "recent_count": 64, "last_seen": "2026-09-25 14:20:00", "state": "ok",
                "hints": [L("Если уведомления не приходят — проверь в самом eXpress «Настройки → Уведомления».",
                            "Make sure desktop notifications are enabled in eXpress settings.")],
            },
        ],
        "gnome_disabled": [
            {"slug": "slack-slack", "app_id": "slack.desktop", "enable": False, "banners": True},
        ],
    }


def inspect(db_path):
    """Полная диагностика системы, браузеров и приложений."""
    if os.environ.get("MESSHUB_THEMED_DEMO") == "1":
        return _demo_data()
    sys_info = _system_info()
    gnome_apps = _gnome_apps()
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        recent = conn.execute(
            "SELECT app, COALESCE(site, ''), COUNT(*), MAX(received_at) FROM messages "
            "WHERE received_at >= ? GROUP BY app, site",
            (catcher.msk_time(24 * 7),),
        ).fetchall()
        prefs = rules.get_prefs(conn)
    finally:
        conn.close()
    browsers, matched = _inspect_browsers(gnome_apps, recent, sys_info)
    apps, gnome_disabled = _inspect_apps(gnome_apps, matched, recent, prefs)
    return {
        "system": sys_info,
        "browsers": browsers,
        "apps": apps,
        "gnome_disabled": gnome_disabled,
    }


def set_gnome_app(slug, enable):
    """Включить/выключить уведомления приложения в GNOME."""
    if WINDOWS:
        raise ValueError(L("Это настройка GNOME на Linux", "This setting is for GNOME on Linux"))
    slug = (slug or "").strip()
    if not _SAFE_SLUG.match(slug):
        raise ValueError(L("Некорректный идентификатор приложения", "Invalid application slug"))
    if not shutil.which("gsettings"):
        raise ValueError(L("Утилита gsettings не найдена", "gsettings command not found"))
    code, out = diag._run(["gsettings", "get", "org.gnome.desktop.notifications", "application-children"])
    if code != 0 or slug not in parse_gnome_children(out):
        raise ValueError(L("Приложение не найдено в списке уведомлений GNOME",
                           "Application not found in GNOME notification list"))
    path = f"org.gnome.desktop.notifications.application:/org/gnome/desktop/notifications/application/{slug}/"
    val = "true" if enable else "false"
    r = subprocess.run(["gsettings", "set", path, "enable", val], capture_output=True, text=True, timeout=5)
    if r.returncode != 0:
        raise ValueError((r.stderr or r.stdout or "gsettings error").strip())
    if enable:
        subprocess.run(["gsettings", "set", path, "show-banners", "true"], capture_output=True, text=True, timeout=5)
    return {"ok": True, "slug": slug, "enable": bool(enable)}


def open_os_settings(kind="notifications"):
    """Открыть системный раздел настроек уведомлений."""
    if WINDOWS:
        uri = "ms-settings:privacy-notifications" if kind == "privacy" else "ms-settings:notifications"
        os.startfile(uri)  # noqa: S606 — жёстко заданный URI Параметров Windows
        return {"ok": True, "opened": uri}
    if shutil.which("gnome-control-center"):
        subprocess.Popen(["gnome-control-center", "notifications"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "opened": "gnome-control-center notifications"}
    raise ValueError(L("Открой настройки уведомлений вручную в параметрах рабочего стола",
                       "Open notification settings manually in your desktop settings"))


def open_browser_settings(browser_id):
    """Открыть страницу настроек уведомлений в выбранном браузере."""
    b = next((x for x in BROWSERS if x["id"] == browser_id), None)
    if not b:
        raise ValueError(L("Неизвестный браузер", "Unknown browser"))
    if WINDOWS:
        return {"ok": False, "url": b["url"],
                "hint": L(f"Скопируй и вставь в адресную строку браузера: {b['url']}",
                          f"Copy and paste into the browser address bar: {b['url']}")}
    exe = next((shutil.which(x) for x in b["bins"] if shutil.which(x)), None)
    if not exe:
        return {"ok": False, "url": b["url"],
                "hint": L(f"Команда запуска не найдена. Скопируй адрес: {b['url']}",
                          f"Browser binary not found. Copy the address: {b['url']}")}
    subprocess.Popen([exe, b["url"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True, "url": b["url"], "opened": os.path.basename(exe)}


def send_test(db_path):
    """Отправить тестовое уведомление и проверить, что сборщик положил его в БД."""
    import secrets
    marker = "messhub-probe-" + secrets.token_hex(4)
    title = "messhub"
    body = L(f"Проверка перехвата ({marker})", f"Capture check ({marker})")
    if WINDOWS:
        ps = shutil.which("powershell.exe") or shutil.which("powershell")
        if not ps:
            return {"ok": False, "error": L("PowerShell не найден", "PowerShell not found")}
        script = (
            "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
            "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
            f"$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text>messhub</text><text>{marker}</text></binding></visual></toast>');"
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('messhub').Show([Windows.UI.Notifications.ToastNotification]::new($x))"
        )
        r = subprocess.run([ps, "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=10,
                           creationflags=0x08000000)
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or r.stdout or "toast failed").strip()[:300]}
    else:
        ns = shutil.which("notify-send")
        if not ns:
            return {"ok": False, "error": L("Не установлена утилита notify-send (пакет libnotify-bin / libnotify)",
                                            "notify-send is not installed (libnotify-bin / libnotify)")}
        r = subprocess.run([ns, "-a", "messhub", "-t", "2500", title, body], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or r.stdout or "notify-send failed").strip()[:300]}

    t0 = time.monotonic()
    deadline = t0 + 4.0
    found_id = None
    while time.monotonic() < deadline:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            row = conn.execute("SELECT id FROM messages WHERE message LIKE ? ORDER BY id DESC LIMIT 1",
                               (f"%{marker}%",)).fetchone()
            if row:
                found_id = row[0]
                for tbl in ("rule_hits", "reminders", "embeddings"):
                    conn.execute(f"DELETE FROM {tbl} WHERE message_id = ?", (found_id,))
                conn.execute("DELETE FROM messages WHERE id = ?", (found_id,))
                conn.commit()
                break
        finally:
            conn.close()
        time.sleep(0.15)
    if found_id is not None:
        return {"ok": True, "ms": int((time.monotonic() - t0) * 1000)}
    return {"ok": False, "error": L("Уведомление отправлено, но не попало в базу за 4 с — проверь, запущен ли сбор и включён ли перехват.",
                                    "Notification was sent but not captured within 4s — check collector and system permissions.")}
