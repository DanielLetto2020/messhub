#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
События тематических колонок (контейнеры, службы, команды) и их жизненный цикл
«проблема → починилось».

У события может быть ключ (event_key): один ключ — одна проблема, например
container:podman:web или unit:system:backup.service.
  emit(…, key=K)  новая карточка; прежняя открытая карточка с тем же ключом отмечается
                  прочитанной — на доске всегда одна, самая свежая;
  resolve(K)      проблема ушла: карточке ставится resolved_at, в виджете она бледнеет и
                  получает «✓ починилось в 18:42» (прочитать её можно как обычно).
Приём событий (ingest.py) умеет то же: поля key и status: "resolved".

details — хвост лога или вывода: хранится только в базе, в виджете свёрнут и в Telegram
не пересылается (пересылка берёт только текст карточки).
"""

import sqlite3
import time
from datetime import datetime

import catcher
import i18n
import rules

APPS = {"containers": "messhub-containers", "services": "messhub-services", "commands": "messhub-commands"}
DETAILS_MAX = 6000


def _lang(conn):
    """Фоновые слушатели пишут карточки на языке из настроек."""
    i18n.set_lang(i18n.background(rules.get_prefs(conn)["language"]))


def enabled(conn, col):
    return rules.themed(rules.get_prefs(conn))[col]["enabled"]


def emit(conn, col, chat, text, sender="", details="", key="", urgency=1, supersede=True):
    """Карточка тематической колонки col (containers|services|commands). → id записи."""
    ts = time.time()
    chat = (chat or "")[:200]
    rec = {"app": APPS[col], "chat": chat, "sender": (sender or chat)[:200], "is_bot": 0,
           "message": text[:4000], "notification_id": 0, "urgency": urgency, "has_media": 0,
           "event_ts": ts, "event_iso": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
           "raw_summary": chat, "raw_body": text[:4000], "site": "", "avatar": None,
           "event_key": key or None, "details": (details or "")[-DETAILS_MAX:] or None}
    if key and supersede:
        conn.execute("UPDATE messages SET is_read = 1, read_at = ? WHERE event_key = ? AND is_read = 0 "
                     "AND pinned = 0", (catcher.msk_time(), key))
    rec["id"] = catcher.insert(conn, rec)
    try:
        rules.apply_on_insert(conn, rec)
    except Exception as e:  # noqa: BLE001 — правило не должно ронять слушателя
        print(f"Тематические колонки: действия правил: {e!r}", flush=True)
    return rec["id"]


def resolve(conn, key):
    """Проблема с ключом key ушла. → сколько карточек отмечено «починилось»."""
    if not key:
        return 0
    n = conn.execute("UPDATE messages SET resolved_at = ? WHERE event_key = ? AND resolved_at IS NULL",
                     (catcher.msk_time(), key)).rowcount
    conn.commit()
    return n


def open_problem(conn, key):
    """Последняя карточка с ключом key, если проблема ещё не ушла (прочитана она или нет)."""
    row = conn.execute("SELECT id FROM messages WHERE event_key = ? AND resolved_at IS NULL "
                       "ORDER BY id DESC LIMIT 1", (key,)).fetchone()
    return row[0] if row else None


def open_keys(conn, prefix):
    """Ключи с неушедшими проблемами (по префиксу) — чтобы заметить, что починилось."""
    return {r[0] for r in conn.execute(
        "SELECT DISTINCT event_key FROM messages WHERE event_key LIKE ? AND resolved_at IS NULL",
        (prefix.replace("%", "") + "%",))}


def recent_count(conn, key, minutes):
    """Сколько карточек с этим ключом за последние minutes минут (для «3-й раз за 10 минут»)."""
    return conn.execute("SELECT COUNT(*) FROM messages WHERE event_key = ? AND received_at >= ?",
                        (key, catcher.msk_time(minutes / 60))).fetchone()[0]


def connect(db_path):
    return sqlite3.connect(db_path, timeout=5)


def took(seconds):
    s = int(round(seconds))
    if s >= 3600:
        return i18n.L(f"{s // 3600} ч {s % 3600 // 60} мин", f"{s // 3600}h {s % 3600 // 60}m")
    if s >= 60:
        return i18n.L(f"{s // 60} мин {s % 60} с", f"{s // 60}m {s % 60}s")
    return i18n.L(f"{s} с", f"{s}s")


def command(db_path, payload):
    """Итог команды от messhub run (POST /api/event, kind=command). → ответ для run.py."""
    cmd = str(payload.get("cmd") or "").strip()
    if not cmd:
        raise ValueError(i18n.L("Нет команды", "No command"))
    code = int(payload.get("code") or 0)
    secs = float(payload.get("seconds") or 0)
    cwd = str(payload.get("cwd") or "")[:500]
    conn = connect(db_path)
    try:
        if not enabled(conn, "commands"):
            return {"skipped": True, "reason": i18n.L(
                "колонка «Команды» выключена: настройки → «Тематические колонки»",
                "the Commands column is off: settings → Themed columns")}
        lines = rules.themed(rules.get_prefs(conn))["commands"]["log_lines"]
        req_lang = i18n.lang()
        _lang(conn)
        key = "cmd:" + cwd + "\n" + cmd
        folder = cwd.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] if cwd else ""
        if code == 0:
            text = i18n.L(f"готово за {took(secs)}", f"done in {took(secs)}")
            fixed = resolve(conn, key)          # прошлые ошибки той же команды в той же папке
            mid = emit(conn, "commands", cmd[:120], text, sender=folder, key="", urgency=1)
        else:
            text = i18n.L(f"ошибка (код {code}) через {took(secs)}", f"failed (code {code}) after {took(secs)}")
            tail = "\n".join(str(payload.get("tail") or "").splitlines()[-lines:]) if lines else ""
            mid = emit(conn, "commands", cmd[:120], text, sender=folder, details=tail, key=key, urgency=2)
            fixed = 0
        i18n.set_lang(req_lang)
        return {"id": mid, "resolved": fixed}
    finally:
        conn.close()


def migrate(conn):
    """Раз при обновлении: кто уже пользовался хуком терминала (колонка «Терминал»), тому
    колонку «Команды» включаем сразу — иначе хук молча перестал бы попадать на доску."""
    if conn.execute("SELECT 1 FROM prefs WHERE key = 'themed'").fetchone():
        return False
    if not conn.execute("SELECT 1 FROM messages WHERE app IN ('Терминал', 'Terminal') LIMIT 1").fetchone():
        return False
    rules.set_prefs(conn, {"themed": {"commands": {"enabled": True}}})
    conn.commit()
    return True
