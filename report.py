#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Недельный отчёт в Telegram — цифры без ИИ: сколько и откуда пришло, самые шумные
чаты, кто больше писал, упоминания, что осталось непрочитанным и закреплённым.
Шлётся через ту же пересылку (actions.send), в день и время из настроек (МСК).
"""

import sqlite3
from datetime import datetime, timedelta

import actions
import catcher
import i18n
import rules
import stats
import version
from i18n import L

DOW_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
DOW_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def build(conn, days=7):
    d = stats.stats(conn, days)
    now = datetime.now(catcher.MSK)
    frm = (now - timedelta(days=days)).strftime("%d.%m")
    unread = conn.execute("SELECT COUNT(*) FROM messages WHERE is_read = 0").fetchone()[0]
    pinned = conn.execute("SELECT COUNT(*) FROM messages WHERE pinned = 1").fetchone()[0]
    dow = DOW_EN if i18n.lang() == "en" else DOW_RU
    lines = [L(f"📊 {version.APP_NAME}: неделя {frm}–{now.strftime('%d.%m')}",
               f"📊 {version.APP_NAME}: week {frm}–{now.strftime('%d.%m')}")]
    if not d["total"]:
        lines.append(L("Сообщений за неделю не было.", "No messages this week."))
        return "\n".join(lines)
    lines.append(L(f"Всего: {d['total']} сообщ. в {d['chats']} чатах от {d['senders']} отправителей",
                   f"Total: {d['total']} messages in {d['chats']} chats from {d['senders']} senders"))
    lines.append(L("По источникам: ", "By source: ")
                 + ", ".join(f"{s['ico']} {s['name']} {s['n']}" for s in d["by_source"][:8]))
    lines.append("")
    lines.append(L("Самые шумные чаты:", "Noisiest chats:"))
    lines += [f"  {i}. {c['ico']} {c['chat'] or '—'} — {c['n']}" for i, c in enumerate(d["top_chats"][:5], 1)]
    lines.append(L("Больше всех писали:", "Most active senders:"))
    lines += [f"  {i}. {s['sender'] or '—'} — {s['n']}" for i, s in enumerate(d["top_senders"][:5], 1)]
    lines.append("")
    if d["busiest_hour"] is not None:
        lines.append(L(f"Пик: {dow[d['busiest_day']]}, около {d['busiest_hour']:02d}:00",
                       f"Peak: {dow[d['busiest_day']]}, around {d['busiest_hour']:02d}:00"))
    lines.append(L(f"Упоминаний: {d['mentions']} · не прочитано сейчас: {unread} · закреплено: {pinned}",
                   f"Mentions: {d['mentions']} · unread now: {unread} · pinned: {pinned}"))
    return "\n".join(lines)


def due(prefs, now):
    r = prefs["report"]
    return (r["enabled"] and now.weekday() == r["weekday"] and now.strftime("%H:%M") >= r["time"]
            and prefs["report_last"] != now.strftime("%Y-%m-%d"))


def maybe_send(db_path):
    """Из фонового цикла (раз в минуту): пора — отправить. → текст ошибки или None."""
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        prefs = rules.get_prefs(conn)
        now = datetime.now(catcher.MSK).replace(tzinfo=None)
        if not due(prefs, now):
            return None
        i18n.set_lang(i18n.pick(prefs["language"]))
        ok, err = actions.send(build(conn))
        if ok:
            rules.set_prefs(conn, {"report_last": now.strftime("%Y-%m-%d")})
            conn.commit()
            return None
        return err
    finally:
        conn.close()
