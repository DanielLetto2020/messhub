#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Напоминания по сообщениям: на плашке «⏰ 15:00», если в тексте есть время (when.py), — по клику
«напомнить за 10 минут / за 30 минут / в это время». В срок в колонку «Напоминания» приходит
карточка с текстом исходного сообщения, играет звук (кроме тихих часов), а на Linux ещё и
всплывает системное уведомление (notify-send; сама программа его не записывает).
Время — местное, как на часах компьютера.
"""

import os
import shutil
import subprocess
import threading
import time
from datetime import datetime

import catcher
import events
import rules
from i18n import L

POPUP_ENTRY = "messhub-popup"        # desktop-entry своих всплывашек: catcher их не записывает


def now_s():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def add(conn, mid, at, event_at=""):
    if not conn.execute("SELECT 1 FROM messages WHERE id = ?", (mid,)).fetchone():
        raise ValueError(L("Нет такого сообщения", "No such message"))
    try:
        datetime.strptime(at, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ValueError(L("Время — в виде ГГГГ-ММ-ДД ЧЧ:ММ", "Time must look like YYYY-MM-DD HH:MM"))
    if at <= now_s():
        raise ValueError(L("Это время уже прошло", "That time has passed"))
    conn.execute("DELETE FROM reminders WHERE message_id = ? AND fired = 0", (mid,))   # одно на сообщение
    conn.execute("INSERT INTO reminders (message_id, at, event_at, created) VALUES (?,?,?,?)",
                 (mid, at, event_at[:16], catcher.msk_time()))
    return at


def cancel(conn, mid):
    return conn.execute("DELETE FROM reminders WHERE message_id = ? AND fired = 0", (mid,)).rowcount


def for_ids(conn, ids):
    """{id сообщения: время напоминания} — для плашек."""
    if not ids:
        return {}
    q = ",".join("?" * len(ids))
    return {m: a for m, a in conn.execute(
        f"SELECT message_id, at FROM reminders WHERE fired = 0 AND message_id IN ({q})", list(ids))}


def popup(title, body):
    exe = shutil.which("notify-send") if os.name != "nt" else None
    if exe:
        try:
            subprocess.run([exe, "-a", "messhub", "-h", f"string:desktop-entry:{POPUP_ENTRY}", title, body],
                           timeout=5, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            pass


def fire_due(conn):
    """Наступившие напоминания → карточки. → сколько сработало."""
    import actions
    import quiet
    due = conn.execute("SELECT r.id, r.message_id, r.event_at, m.app, COALESCE(m.site, ''), m.chat, m.sender, m.message "
                       "FROM reminders r JOIN messages m ON m.id = r.message_id "
                       "WHERE r.fired = 0 AND r.at <= ? ORDER BY r.at", (now_s(),)).fetchall()
    if not due:
        return 0
    prefs = rules.get_prefs(conn)
    events._lang(conn)
    for rid, mid, event_at, app, site, chat, sender, message in due:
        conn.execute("UPDATE reminders SET fired = 1 WHERE id = ?", (rid,))
        src = rules.source_of(app, site, prefs["source_names"])
        head = (L(f"в {event_at[11:16]}", f"at {event_at[11:16]}") + " · ") if event_at else ""
        text = head + (message or "")[:1500]
        who = chat + (f" · {sender}" if sender and sender != chat else "")
        events.emit(conn, "reminders", who[:200], text, sender=src["name"], urgency=2)
        if not (quiet.active(prefs) and not prefs["quiet"]["sound"]):
            actions.play_sound()
        popup(L("Напоминание", "Reminder") + f" — {who[:80]}", text[:300])
    conn.commit()
    return len(due)


def start(db_path):
    def loop():
        while True:
            try:
                conn = events.connect(db_path)
                try:
                    n = fire_due(conn)
                    if n:
                        print(f"Напоминания: сработало {n}", flush=True)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                print(f"Напоминания: ошибка: {e!r}", flush=True)
            time.sleep(20)
    threading.Thread(target=loop, name="reminders", daemon=True).start()
