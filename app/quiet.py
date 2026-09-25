#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тихие часы: по расписанию, вручную («тихо на час», «до утра»), а по желанию — и вместе с «Не беспокоить» GNOME.
Это своё состояние программы: «Не беспокоить» в системе прячет только всплывающие уведомления, а сбор и
доска работают как обычно (по умолчанию тихие часы на него не смотрят — follow_dnd выключено).

Что меняется, пока тихо: правила не играют звук (можно разрешить), пересылка в Telegram — по
настройке (по умолчанию идёт как обычно), в шапке доски — луна. Сообщения копятся как всегда.
Когда тихие часы кончились — одна карточка-сводка в колонку «Сводки»: сколько пришло, откуда,
сколько упоминаний и проблем в тематических колонках. По желанию программа сама включает
«Не беспокоить» GNOME на время тихих часов (и выключает, если включала она).

Состояние (тихо ли сейчас, с какого момента, включали ли «Не беспокоить») — в prefs.quiet_state.
"""

import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timedelta

import catcher
import events
import rules
from i18n import L

WINDOWS = os.name == "nt"
DND_KEY = ("org.gnome.desktop.notifications", "show-banners")
current = {"active": False, "reason": "", "until": "", "dnd": None, "t": 0.0}
DND_OFF = "-dnd"             # manual_until: тишину выключили кнопкой при «Не беспокоить» — до его выключения


def gnome_dnd():
    """Включено ли «Не беспокоить» GNOME (баннеры выключены); None — не GNOME / не узнать."""
    exe = None if WINDOWS else shutil.which("gsettings")
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "get", *DND_KEY], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    v = r.stdout.strip()
    return {"false": True, "true": False}.get(v)


def set_gnome_dnd(on):
    exe = None if WINDOWS else shutil.which("gsettings")
    if exe:
        subprocess.run([exe, "set", *DND_KEY, "false" if on else "true"], capture_output=True, timeout=3)


def _slot_end(slot, now):
    """Если now внутри интервала (интервал может идти через полночь) — когда он кончится, иначе None."""
    hm = now.strftime("%H:%M")
    frm, to = slot["from"], slot["to"]
    day = now.weekday()
    if frm < to:
        if day in slot["days"] and frm <= hm < to:
            return now.replace(hour=int(to[:2]) % 24, minute=int(to[3:]), second=0) + \
                timedelta(days=1 if to == "24:00" else 0)
    else:                                   # 22:00–08:00: вечер этого дня или утро следующего
        if day in slot["days"] and hm >= frm:
            return (now + timedelta(days=1)).replace(hour=int(to[:2]), minute=int(to[3:]), second=0)
        if (day - 1) % 7 in slot["days"] and hm < to:
            return now.replace(hour=int(to[:2]), minute=int(to[3:]), second=0)
    return None


def evaluate(q, now=None, dnd=None):
    """(тихо ли, почему: manual|schedule|dnd|'', до скольки 'ЧЧ:ММ' или '')."""
    now = now or datetime.now(catcher.MSK).replace(tzinfo=None)
    mu = q.get("manual_until") or ""
    ts = now.strftime("%Y-%m-%d %H:%M:%S")
    if mu == DND_OFF:                               # выключили, пока включено «Не беспокоить»: его не слушаем,
        mu, dnd = "", False                         # расписание — как обычно
    if mu.startswith("-") and mu[1:] > ts:          # вручную выключили до конца интервала
        return False, "", ""
    if mu and not mu.startswith("-") and mu > ts:
        return True, "manual", mu[11:16]
    if q.get("enabled"):
        for slot in q.get("schedule") or []:
            end = _slot_end(slot, now)
            if end:
                return True, "schedule", end.strftime("%H:%M")
    if q.get("follow_dnd") and dnd:
        return True, "dnd", ""
    return False, "", ""


def active(prefs=None):
    """Тихо ли сейчас — для правил при записи (звук, пересылка). Берёт свежий расчёт фонового потока."""
    if prefs is not None and time.time() - current["t"] > 30:
        a, why, until = evaluate(prefs["quiet"], dnd=current["dnd"])
        current.update(active=a, reason=why, until=until, t=time.time())
    return current["active"]


def _state(conn):
    try:
        return json.loads(rules.get_prefs(conn).get("quiet_state") or "{}")
    except ValueError:
        return {}


def _save_state(conn, st):
    rules.set_prefs(conn, {"quiet_state": json.dumps(st, separators=(",", ":"))})
    conn.commit()


def summary_text(conn, since):
    """Сводка за тихие часы: сколько пришло и откуда, упоминания, проблемы в тематических колонках."""
    prefs = rules.get_prefs(conn)
    names = prefs["source_names"]
    mre = rules.mention_re(prefs["mentions"])
    by_src, total, mentions, problems = {}, 0, 0, 0
    for app, site, message, key in conn.execute(
            "SELECT app, COALESCE(site, ''), message, event_key FROM messages WHERE received_at >= ? "
            "AND app NOT IN ('messhub-digest', 'messhub-reminders')", (since,)):
        s = rules.source_of(app, site, names)
        by_src[s["name"]] = by_src.get(s["name"], 0) + 1
        total += 1
        if mre and mre.search(message or ""):
            mentions += 1
        if key:
            problems += 1
    if not total:
        return L("Пока было тихо, ничего не пришло.", "Nothing arrived during quiet hours.")
    top = ", ".join(f"{n} {c}" for n, c in sorted(by_src.items(), key=lambda x: -x[1])[:6])
    parts = [L(f"Пока было тихо, пришло {total}: {top}.", f"{total} arrived during quiet hours: {top}.")]
    if mentions:
        parts.append(L(f"Упоминаний тебя: {mentions}.", f"Mentions of you: {mentions}."))
    if problems:
        parts.append(L(f"Событий в тематических колонках: {problems}.", f"Themed column events: {problems}."))
    return "\n".join(parts)


def step(conn):
    """Одна проверка: переходы «стало тихо / кончилось» → «Не беспокоить» GNOME и сводка."""
    prefs = rules.get_prefs(conn)
    q = prefs["quiet"]
    dnd = gnome_dnd()                   # узнаём всегда: в настройках видно, включено ли оно в системе
    if q["manual_until"] == DND_OFF and not dnd:    # «Не беспокоить» выключили — дальше снова идём за ним
        rules.set_prefs(conn, {"quiet": {"manual_until": ""}})
        conn.commit()
        q = rules.get_prefs(conn)["quiet"]
    st = _state(conn)
    # «Не беспокоить», включённое нами, — не повод считать тихим (иначе тишина не кончится)
    a, why, until = evaluate(q, dnd=dnd and not st.get("dnd_set"))
    current.update(active=a, reason=why, until=until, dnd=dnd, t=time.time())
    was = bool(st.get("on"))
    if a and not was:
        st = {"on": True, "since": catcher.msk_time(), "dnd_set": False}
        if q["set_dnd"] and dnd is False and why != "dnd":
            set_gnome_dnd(True)
            st["dnd_set"] = True
        _save_state(conn, st)
        print(f"Тихие часы: начались ({why})", flush=True)
    elif not a and was:
        if st.get("dnd_set"):
            set_gnome_dnd(False)
        if q["summary"] and st.get("since"):
            events._lang(conn)
            events.emit(conn, "digest", L("Тихие часы", "Quiet hours"), summary_text(conn, st["since"]),
                        sender=L("сводка", "digest"))
        _save_state(conn, {"on": False})
        print("Тихие часы: кончились", flush=True)
    return current


def set_manual(conn, action):
    """Кнопка на доске: hour — тихо на час, morning — до 08:00, off — выключить до конца интервала
    (при «Не беспокоить» GNOME — пока оно не выключится)."""
    now = datetime.now(catcher.MSK).replace(tzinfo=None)
    q = rules.get_prefs(conn)["quiet"]
    if action == "hour":
        until = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    elif action == "morning":
        m = now.replace(hour=8, minute=0, second=0)
        until = (m if m > now else m + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    elif action == "off":
        a, why, end = evaluate(q, now, dnd=current["dnd"])
        if why == "schedule":           # выключить до конца текущего интервала расписания
            e = now.replace(hour=int(end[:2]), minute=int(end[3:]), second=0)
            until = "-" + (e if e > now else e + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        elif why == "dnd":              # «Не беспокоить» GNOME: не слушать его, пока его не выключат
            until = DND_OFF
        else:
            until = ""
    else:
        raise ValueError(L("Неизвестное действие", "Unknown action"))
    rules.set_prefs(conn, {"quiet": {"manual_until": until}})
    conn.commit()
    return step(conn)


def start(db_path):
    def loop():
        while True:
            try:
                conn = events.connect(db_path)
                try:
                    step(conn)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                print(f"Тихие часы: ошибка: {e!r}", flush=True)
            time.sleep(20)
    threading.Thread(target=loop, name="quiet", daemon=True).start()


def public_status():
    return {k: current[k] for k in ("active", "reason", "until", "dnd")}
