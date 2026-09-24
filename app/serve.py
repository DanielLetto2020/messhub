#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Локальный HTTP-сервер (stdlib): страницы виджета/настроек и их API.

  Страницы и файлы:
    / и /widget → widget.html (в браузере — та же доска)     /settings → settings.html
    /i18n.js — переводы страниц     /avatar/<файл> — аватары из уведомлений

  Сообщения:
    GET /api/messages   последние N (JSON); &after=ID — только новые (id > ID);
                        &limit=N &app=… &q=подстрока &ids=1,2,3 &unread=1
                        &rules=1 — «как видит виджет»: правила показа, без отложенного,
                                   плюс highlight (цвет) и mention (упоминание)
                        заголовки X-Rules-Ver / X-Prefs-Ver — версии правил и настроек
    GET /api/sources    источники [{key,name,ico,rank}] (&rules=1 — плюс hidden)
    GET /api/visible    {"max_id", "ids"} — что сейчас должно быть на доске виджета
    GET /api/column?src=KEY  сколько в колонке непрочитанного / закреплённого / отложенного
    POST /api/close-column {src} — закрыть колонку: прочитать её сообщения; колонка вернётся
                        с новым сообщением. Нельзя, если есть закреплённые или отложенные (409)
    POST /api/reopen-column {src, ids} — отмена закрытия
    GET /api/search     поиск по истории: q, src, chat, from, to, status, limit, offset
    GET /api/why?id=N   почему сообщение видно/скрыто/подсвечено/закреплено
    POST /api/read      {ids, unread?} — прочитано (или вернуть непрочитанным)
    POST /api/restore   {ids} — вернуть в виджет (непрочитано, не отложено)
    POST /api/pin       {ids, pinned}      POST /api/snooze {ids, preset: 1h|3h|evening|tomorrow}
    POST /api/ingest    событие от скрипта/сервиса (ключ в Authorization: Bearer …), см. ingest.py
    POST /api/event     итог команды от messhub run (run.py), только с этого компьютера

  Тематические колонки и журнал:
    GET /api/themed     настройки и состояние колонок «Контейнеры», «Службы», «Команды»
    GET /api/logs       журнал программы: level=all|warn|error, q, src, limit (applog.py)
    POST /api/logs/clear | /api/logs/export (в «Загрузки», домашняя папка → ~) | /api/logs/client (ошибки JS)

  Настройки: /api/settings/sources|source|rules, /api/rules(/delete), /api/source-mode,
    /api/prefs, /api/stats, /api/data, /api/purge, /api/export, /api/config/export|import,
    /api/backups(/make|/restore), /api/report/preview|send, /api/forward(/test),
    /api/rag/status|install|disable|remove-model|search|ask, /api/ingest/config|token,
    /api/diag, /api/autostart, /api/restart, /api/version, /api/update (новая версия на GitHub),
    /api/mail (ящики IMAP, см. mail.py) + /api/mail/channel|account|delete|test|check

Защита от чужих страниц в браузере: сервер отвечает, только если в Host стоит localhost или
IP-адрес (так не пройдёт DNS rebinding — подмена имени сайта на 127.0.0.1), не отвечает на
запросы к API с Sec-Fetch-Site: cross-site и с чужим Origin (переход на саму страницу по ссылке
разрешён — ответ чужому сайту всё равно не достаётся). Все POST — только с Content-Type:
application/json (чужая страница не пришлёт такой запрос без CORS-preflight, а на OPTIONS
мы не отвечаем);
ошибки — {"error": "текст для человека"} на языке из настроек. Каждый ответ несёт
X-App-Version — по нему виджет замечает обновление программы.

Фон (start_background): раз в минуту — авто-прочтение (всё, что в БД дольше 24 ч по
времени ЗАПИСИ, МСК; закреплённое не трогает, отложенное считает от возврата) и
недельный отчёт, раз в час — срок хранения и ежедневная копия; отдельно — векторы
для умного поиска, если он включён.

Запуск:
    python3 serve.py                 # http://127.0.0.1:8765
    python3 serve.py --port 9000 --db messages.db
"""

import argparse
import csv
import ipaddress
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import actions
import applog
import avatars
import backup
import catcher
import containers
import diag
import events
import i18n
import ingest
import mail
import paths
import rag
import report
import rules
import services
import stats
import updates
import version
from i18n import L

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = paths.DB_PATH
PAGES = {
    "/": ("widget.html", "text/html; charset=utf-8"),
    "/widget": ("widget.html", "text/html; charset=utf-8"),
    "/settings": ("settings.html", "text/html; charset=utf-8"),
    "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
}

AUTO_READ_HOURS = 24      # лежит в БД дольше — считается прочитанным
TS = "%Y-%m-%d %H:%M:%S"

FIELDS = ("id", "app", "site", "chat", "sender", "is_bot", "message", "has_media",
          "urgency", "event_iso", "received_at", "is_read", "pinned", "snooze_until", "avatar",
          "resolved_at", "details")


def open_db(path):
    # Обычное подключение + PRAGMA query_only: гарантированно читает базу в WAL
    # при активной записи из catcher.py и при этом сам ничего не пишет.
    conn = sqlite3.connect(path, timeout=2.0)
    conn.execute("PRAGMA query_only=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def open_rw(path):
    # отдельное пишущее подключение; catcher коммитит сразу — ждём блокировку до 5 сек
    return sqlite3.connect(path, timeout=5.0)


def write(db_path, fn, *args):
    """Выполнить fn(conn, *args) одной транзакцией."""
    conn = open_rw(db_path)
    try:
        res = fn(conn, *args)
        conn.commit()
        return res
    finally:
        conn.close()


def read(db_path, fn, *args):
    conn = open_db(db_path)
    try:
        return fn(conn, *args)
    finally:
        conn.close()


# ── сообщения ───────────────────────────────────────────────────────────────

class View:
    """Всё, что нужно, чтобы оформить строку сообщения: правила, названия, упоминания."""

    def __init__(self, conn):
        self.prefs = rules.get_prefs(conn)
        self.rs = rules.load(conn, self.prefs)
        self.names = self.prefs["source_names"]
        self.mre = rules.mention_re(self.prefs["mentions"])

    def row(self, d):
        s = rules.source_of(d["app"], d.get("site") or "", self.names)
        text = d.get("message") or ""
        d.update(src=s["key"], src_name=s["name"], src_ico=s["ico"], src_rank=s["rank"],
                 highlight=self.rs.highlight(s["key"], d["chat"], d["sender"], text),
                 mention=bool(self.mre and self.mre.search(text)))
        return d

    def visible(self, d):
        return bool(d.get("pinned")) or self.rs.visible(d["src"], d["chat"], d["sender"], d.get("message") or "")


def query(db_path, after=None, limit=100, app="", q="", unread=False, widget=False,
          ids=None, upto=None):
    """Строки сообщений + (версия правил, версия настроек).
    widget — «как видит виджет»: правила показа (закреплённое видно всегда), без
    отложенного; лимит считаем уже после фильтра."""
    if not os.path.exists(db_path):
        return [], "", ""
    conn = open_db(db_path)
    try:
        v = View(conn)
        where, params = [], []
        if after is not None:
            where.append("id > ?"); params.append(after)
        if upto is not None:
            where.append("id <= ?"); params.append(upto)
        if ids:
            where.append(f"id IN ({','.join('?' * len(ids))})"); params += ids
        if unread:
            where.append("is_read = 0")
        if widget:
            where.append("(snooze_until IS NULL OR snooze_until <= ?)")
            params.append(catcher.msk_time())
        if app:
            where.append("app LIKE ?"); params.append(f"%{app}%")
        if q:
            where.append("(message LIKE ? OR sender LIKE ? OR chat LIKE ?)")
            params += [f"%{q}%", f"%{q}%", f"%{q}%"]
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        order = "ASC" if after is not None else "DESC"
        sql = f"SELECT {', '.join(FIELDS)} FROM messages{wsql} ORDER BY id {order}"
        if not widget:
            sql += " LIMIT ?"; params.append(limit)
        out = []
        for r in conn.execute(sql, params):
            d = v.row(dict(r))
            if widget and not v.visible(d):
                continue
            out.append(d)
            if len(out) >= limit:
                break
        if after is None:
            out.reverse()
        return out, v.rs.ver, rules.prefs_ver(v.prefs)
    finally:
        conn.close()


def _casefold(s):
    return s.casefold() if isinstance(s, str) else s


def search(db_path, q="", src="", chat="", date_from="", date_to="", status="all", limit=50, offset=0):
    """Поиск по истории: подстрока без учёта регистра (в т.ч. кириллица — встроенный
    LIKE SQLite этого не умеет) по тексту, чату и отправителю + фильтры."""
    conn = open_db(db_path)
    conn.create_function("cf", 1, _casefold, deterministic=True)
    try:
        v = View(conn)
        where, params = [], []
        if q:
            pat = "%" + q.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where.append("(cf(message) LIKE ? ESCAPE '\\' OR cf(chat) LIKE ? ESCAPE '\\' "
                         "OR cf(sender) LIKE ? ESCAPE '\\')")
            params += [pat] * 3
        if chat:
            where.append("chat = ?"); params.append(chat)
        if date_from:
            where.append("received_at >= ?"); params.append(date_from)
        if date_to:
            where.append("received_at < ?")
            params.append((datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"))
        if status == "unread":
            where.append("is_read = 0")
        elif status == "read":
            where.append("is_read = 1")
        elif status == "pinned":
            where.append("pinned = 1")
        wsql = (" WHERE " + " AND ".join(where)) if where else ""
        rows = []
        for r in conn.execute(f"SELECT {', '.join(FIELDS)} FROM messages{wsql} ORDER BY id DESC", params):
            d = v.row(dict(r))
            if src and d["src"] != src:
                continue
            rows.append(d)
        page = rows[offset:offset + limit]
        for d in page:
            d["visible"] = v.visible(d)
        return {"total": len(rows), "rows": page}
    finally:
        conn.close()


def rag_rows(db_path, hits):
    """Строки сообщений для результатов умного поиска (в порядке близости)."""
    if not hits:
        return []
    conn = open_db(db_path)
    try:
        v = View(conn)
        ids = [mid for _, mid in hits]
        by_id = {r["id"]: v.row(dict(r)) for r in conn.execute(
            f"SELECT {', '.join(FIELDS)} FROM messages WHERE id IN ({','.join('?' * len(ids))})", ids)}
        out = []
        for score, mid in hits:
            if mid in by_id:
                d = by_id[mid]
                d["score"] = round(score, 3)
                d["visible"] = v.visible(d)
                out.append(d)
        return out
    finally:
        conn.close()


def sources(db_path, apply_rules=False):
    """Все источники, что когда-либо писали, — для колонок виджета."""
    if not os.path.exists(db_path):
        return []
    conn = open_db(db_path)
    try:
        prefs = rules.get_prefs(conn)
        rs = rules.load(conn, prefs)
        found = rules.all_sources(conn)
        # почта из ящиков: колонка «Почта» есть, как только подключён хоть один ящик
        if prefs["mail_channel"] == "imap" and mail.load_accounts():
            m = rules.source_of(mail.APP, "", prefs["source_names"])
            found.setdefault(m["key"], m)
        res = sorted(({k: s[k] for k in ("key", "name", "ico", "rank")} for s in found.values()),
                     key=lambda s: (s["rank"], s["name"]))
        if apply_rules:
            for s in res:
                s["hidden"] = rs.source_hidden(s["key"])
                s["closed"] = s["key"] in prefs["closed_cols"]
        return res
    finally:
        conn.close()


def visible_ids(db_path):
    """Что сейчас должно быть на доске виджета (id <= max_id)."""
    if not os.path.exists(db_path):
        return {"max_id": 0, "ids": []}
    max_id = read(db_path, lambda c: c.execute("SELECT COALESCE(MAX(id), 0) FROM messages").fetchone()[0])
    rows, _, _ = query(db_path, limit=10 ** 6, unread=True, widget=True, upto=max_id)
    # «починилось» у карточек тематических колонок — виджет перерисует их на месте
    return {"max_id": max_id, "ids": [r["id"] for r in rows],
            "resolved": {str(r["id"]): r["resolved_at"] for r in rows if r.get("resolved_at")}}


def column_state(db_path, src):
    """Что сейчас в колонке: непрочитанные видимые (их прочитает «закрыть»),
    закреплённые и отложенные (из-за них закрыть нельзя)."""
    conn = open_db(db_path)
    try:
        v, now = View(conn), catcher.msk_time()
        ids, pinned, snoozed = [], 0, 0
        for r in conn.execute(f"SELECT {', '.join(FIELDS)} FROM messages WHERE is_read = 0"):
            d = v.row(dict(r))
            if d["src"] != src or not v.visible(d):
                continue
            if d["snooze_until"] and d["snooze_until"] > now:
                snoozed += 1
            elif d["pinned"]:
                pinned += 1
            else:
                ids.append(d["id"])
        return {"src": src, "unread": len(ids), "ids": ids, "pinned": pinned, "snoozed": snoozed}
    finally:
        conn.close()


class Conflict(ValueError):
    """Нельзя сделать то, о чём просят, — ответ 409 с подробностями."""
    def __init__(self, msg, data):
        super().__init__(msg)
        self.data = data


def close_column(db_path, src):
    st = column_state(db_path, src)
    if st["pinned"] or st["snoozed"]:
        raise Conflict(L("Колонку нельзя закрыть: в ней есть закреплённые или отложенные сообщения",
                         "The column can't be closed: it has pinned or snoozed messages"), st)

    def upd(conn):
        n = mark_read(conn, st["ids"])
        closed = rules.get_prefs(conn)["closed_cols"]
        rules.set_prefs(conn, {"closed_cols": [*[k for k in closed if k != src], src]})
        return n
    n = write(db_path, upd)
    return {"read": n, "ids": st["ids"], "_ver": read(db_path, _prefs_view)["_ver"]}


def reopen_column(db_path, src, ids):
    def upd(conn):
        mark_read(conn, ids, unread=True)
        _reopen(conn, {src})
    write(db_path, upd)
    return {"ok": True}


def _reopen(conn, keys):
    """Открыть закрытые колонки keys (если среди них есть закрытые)."""
    closed = rules.get_prefs(conn)["closed_cols"]
    if keys & set(closed):
        rules.set_prefs(conn, {"closed_cols": [k for k in closed if k not in keys]})


def _reopen_for(conn, ids):
    """Сообщения вернули в виджет — их закрытые колонки снова открыты."""
    prefs = rules.get_prefs(conn)
    if prefs["closed_cols"] and ids:
        rows = conn.execute(f"SELECT app, site FROM messages WHERE id IN ({_in(ids)})", ids).fetchall()
        _reopen(conn, {rules.source_of(a, s or "", prefs["source_names"])["key"] for a, s in rows})


def _in(ids):
    return ",".join("?" * len(ids))


def mark_read(conn, ids, unread=False):
    """Прочитано (заодно снимаем закрепление) или обратно непрочитанным (отмена)."""
    if not ids:
        return 0
    if unread:
        _reopen_for(conn, ids)
        return conn.execute(f"UPDATE messages SET is_read = 0, read_at = NULL WHERE id IN ({_in(ids)})",
                            ids).rowcount
    return conn.execute(f"UPDATE messages SET is_read = 1, read_at = ?, pinned = 0 "
                        f"WHERE is_read = 0 AND id IN ({_in(ids)})", [catcher.msk_time(), *ids]).rowcount


def restore(conn, ids):
    """Вернуть в виджет: непрочитано и не отложено. Если сообщение старше суток,
    сдвигаем время записи на «почти сейчас», иначе авто-прочтение сразу заберёт его снова."""
    if not ids:
        return 0
    _reopen_for(conn, ids)
    return conn.execute(f"""UPDATE messages SET is_read = 0, read_at = NULL, snooze_until = NULL,
                               received_at = MAX(received_at, ?) WHERE id IN ({_in(ids)})""",
                        [catcher.msk_time(AUTO_READ_HOURS - 1), *ids]).rowcount


def set_pinned(conn, ids, pinned):
    if not ids:
        return 0
    return conn.execute(f"UPDATE messages SET pinned = ? WHERE id IN ({_in(ids)})",
                        [1 if pinned else 0, *ids]).rowcount


SNOOZE_PRESETS = ("1h", "3h", "evening", "tomorrow")


def snooze_until(preset):
    """До какого времени (МСК) отложить. «Вечером» — 19:00 (после 18:00 — завтра)."""
    now = datetime.now(catcher.MSK).replace(tzinfo=None)
    if preset == "1h":
        t = now + timedelta(hours=1)
    elif preset == "3h":
        t = now + timedelta(hours=3)
    elif preset == "evening":
        t = now.replace(hour=19, minute=0, second=0) + timedelta(days=1 if now.hour >= 18 else 0)
    else:
        t = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0)
    return t.strftime(TS)


def set_snooze(conn, ids, preset):
    if not ids:
        return 0, ""
    until = snooze_until(preset)
    return conn.execute(f"UPDATE messages SET snooze_until = ? WHERE id IN ({_in(ids)})",
                        [until, *ids]).rowcount, until


# ── фон ─────────────────────────────────────────────────────────────────────

def auto_read(db_path, hours=AUTO_READ_HOURS):
    """Пометить прочитанным всё, что записано в БД больше hours часов назад (МСК).
    Закреплённое не трогаем; отложенное считаем от момента, когда оно вернулось."""
    if not os.path.exists(db_path):
        return 0
    cutoff = catcher.msk_time(hours)
    return write(db_path, lambda conn: conn.execute(
        """UPDATE messages SET is_read = 1, read_at = ?
           WHERE is_read = 0 AND pinned = 0 AND received_at <= ?
             AND (snooze_until IS NULL OR snooze_until <= ?)""",
        (catcher.msk_time(), cutoff, cutoff)).rowcount)


def purge(conn, days):
    """Удалить записи старше days дней (по времени записи), кроме закреплённых."""
    if days <= 0:
        return 0
    cutoff = catcher.msk_time(days * 24)
    old = "SELECT id FROM messages WHERE received_at < ? AND pinned = 0"
    conn.execute(f"DELETE FROM embeddings WHERE message_id IN ({old})", (cutoff,))
    conn.execute(f"DELETE FROM rule_hits WHERE message_id IN ({old})", (cutoff,))
    return conn.execute("DELETE FROM messages WHERE received_at < ? AND pinned = 0", (cutoff,)).rowcount


def start_background(db_path):
    """Фоновые задачи сервера (см. докстринг модуля)."""
    def slow():
        tick = 0
        while True:
            try:
                n = auto_read(db_path)
                if n:
                    print(f"Авто-прочитано (в БД дольше {AUTO_READ_HOURS} ч): {n}", flush=True)
                err = report.maybe_send(db_path)
                if err:
                    print(f"Недельный отчёт: {err}", flush=True)
                if tick % 60 == 0:
                    days = read(db_path, rules.get_prefs)["retention_days"]
                    if days:
                        n = write(db_path, purge, days)
                        if n:
                            print(f"Удалено по сроку хранения ({days} дн.): {n}", flush=True)
                    name = backup.daily(db_path)
                    if name:
                        print(f"Резервная копия: {name}", flush=True)
            except (sqlite3.Error, OSError) as e:
                print(f"Фоновые задачи: ошибка: {e}", flush=True)
            tick += 1
            time.sleep(60)

    def rag_loop():
        while True:
            n = 0
            try:
                n = rag.index_step(db_path)
            except Exception as e:  # Ollama выключили, модель удалили — не падаем
                rag.state["error"] = str(e)
            time.sleep(1 if n else 20)

    threading.Thread(target=slow, name="background", daemon=True).start()
    threading.Thread(target=rag_loop, name="rag-index", daemon=True).start()


# ── данные, выгрузки ────────────────────────────────────────────────────────

def data_info(db_path):
    size = sum(os.path.getsize(p) for p in (db_path, db_path + "-wal", db_path + "-shm")
               if os.path.exists(p))

    def q(conn):
        n, oldest, newest = conn.execute(
            "SELECT COUNT(*), MIN(received_at), MAX(received_at) FROM messages").fetchone()
        pinned = conn.execute("SELECT COUNT(*) FROM messages WHERE pinned = 1").fetchone()[0]
        prefs = rules.get_prefs(conn)
        return {"bytes": size, "messages": n, "oldest": oldest, "newest": newest, "pinned": pinned,
                "retention_days": prefs["retention_days"], "backup": prefs["backup"],
                "backups": backup.list_backups(), "paths": {"data": paths.DATA_DIR, "backups": paths.BACKUP_DIR}}
    return read(db_path, q)


def downloads_dir():
    if os.environ.get(f"{paths.ENV_PREFIX}_EXPORT_DIR"):          # для тестов
        return os.environ[f"{paths.ENV_PREFIX}_EXPORT_DIR"]
    try:
        d = subprocess.run(["xdg-user-dir", "DOWNLOAD"], capture_output=True, text=True,
                           timeout=3).stdout.strip()
        if d and os.path.isdir(d):
            return d
    except (OSError, subprocess.SubprocessError):
        pass
    d = os.path.expanduser("~/Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


EXPORT_COLS = ("id", "source", "app", "site", "chat", "sender", "message", "received_at",
               "event_iso", "is_read", "pinned")


def _stamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def export(db_path, fmt, days):
    """Выгрузить сообщения (за days дней, 0 — все) в CSV/JSON в «Загрузки». → (путь, строк)."""
    def q(conn):
        names = rules.get_prefs(conn)["source_names"]
        since = catcher.msk_time(days * 24) if days else ""
        return [dict(zip(EXPORT_COLS, (r[0], rules.source_of(r[1], r[2], names)["name"], *r[1:])))
                for r in conn.execute(
                    "SELECT id, app, COALESCE(site, ''), chat, sender, message, received_at, "
                    "event_iso, is_read, pinned FROM messages WHERE received_at >= ? ORDER BY id", (since,))]
    rows = read(db_path, q)
    path = os.path.join(downloads_dir(), f"{version.APP_ID}-{_stamp()}.{fmt}")
    if fmt == "csv":
        with open(path, "w", encoding="utf-8-sig", newline="") as f:   # BOM — для Excel/LibreOffice
            w = csv.DictWriter(f, fieldnames=EXPORT_COLS)
            w.writeheader()
            w.writerows(rows)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=1)
    return path, len(rows)


def export_config(db_path):
    data = read(db_path, rules.export_config)
    path = os.path.join(downloads_dir(), f"{version.APP_ID}-settings-{_stamp()}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return path, len(data["rules"])


def themed_info(db_path):
    """Настройки и состояние тематических колонок — для раздела настроек."""
    prefs = read(db_path, rules.get_prefs)
    run_cmd = (f'"{os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "messhub-run.exe")}" -- …'
               if getattr(sys, "frozen", False) else
               "messhub run -- …" if HERE.startswith("/usr/lib/") else f"python3 {os.path.join(HERE, 'run.py')} -- …")
    hook = "" if os.name == "nt" else (
        "source /usr/lib/messhub/hooks/long-command.sh" if HERE.startswith("/usr/lib/")
        else f"source {os.path.join(HERE, 'hooks', 'long-command.sh')}")
    demo = os.environ.get(f"{paths.ENV_PREFIX}_THEMED_DEMO") == "1"      # снимки экрана: без настоящих движков
    cont = ({"podman": {"found": True, "running": True, "error": "", "events": 128},
             "docker": {"found": True, "running": False, "events": 0,
                        "error": containers.human_error("docker", "permission denied")}} if demo
            else containers.public_status())
    serv = (dict(services.public_status(), found=True, running=True, error="", failed=1) if demo
            else services.public_status())
    return {"prefs": rules.themed(prefs), "platform": "windows" if os.name == "nt" else "linux",
            "containers": cont, "services": serv, "commands": {"run": run_cmd, "hook": hook},
            "log_lines": list(rules.LOG_LINES)}


def export_logs(level="all", q=""):
    rows = applog.query(level, q, limit=10 ** 6)["rows"]
    rows.reverse()
    path = os.path.join(downloads_dir(), f"{version.APP_ID}-log-{_stamp()}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{version.version_line()}\n\n" + applog.mask(applog.as_text(rows)) + "\n")
    return path, len(rows)


# ── HTTP ────────────────────────────────────────────────────────────────────

def host_allowed(host):
    """Host: localhost или IP-адрес (с портом или без). Имя сайта — нет: это DNS rebinding."""
    h = (host or "").strip().lower()
    if not h:
        return False
    if h.startswith("["):                                   # [::1]:8765
        h = h[1:].split("]", 1)[0]
    elif h.count(":") == 1:
        h = h.split(":", 1)[0]
    if h in ("localhost", "localhost."):
        return True
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def origin_allowed(origin, host):
    """Origin страницы, если он есть, должен совпадать с самим сервером."""
    if not origin:
        return True
    o = origin.strip().lower()
    return o in (f"http://{(host or '').strip().lower()}",) or \
        any(o == f"http://{name}:{port}" for name in ("127.0.0.1", "localhost", "[::1]")
            for port in [(host or "").rsplit(":", 1)[-1]] if port.isdigit())


class BadRequest(ValueError):
    pass


def _ids(payload):
    ids = payload.get("ids", [])
    if not isinstance(ids, list):
        raise BadRequest(L("ids — список", "ids must be a list"))
    return [int(i) for i in ids][:5000]


def _prefs_view(conn):
    prefs = rules.get_prefs(conn)
    return dict(prefs, _ver=rules.prefs_ver(prefs), _lang=i18n.lang(),
                _active_profile=rules.active_profile(prefs))


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # тихо
            pass

        def _send(self, code, body, ctype, headers=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            # по нему виджет замечает обновление программы и перезагружает страницу
            self.send_header("X-App-Version", version.__version__)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, code=200, headers=None):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8", headers)

        def _lang(self):
            """Язык ответов — из настроек, при «auto» — по Accept-Language."""
            try:
                pref = read(db_path, lambda c: rules.get_prefs(c)["language"])
            except sqlite3.Error:
                pref = "auto"
            i18n.set_lang(i18n.pick(pref, self.headers.get("Accept-Language", "")))

        def _file(self, path, ctype, headers=None):
            try:
                with open(path, "rb") as f:
                    self._send(200, f.read(), ctype, headers)
            except OSError:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def _guard(self):
            """Чужие страницы в браузере сюда не ходят (см. докстринг модуля). → можно ли отвечать.
            Переход на саму страницу (ссылка из другой программы или сайта) разрешён: прочитать ответ
            чужой сайт не может, а Host всё равно проверяется. С чужого сайта нельзя только API."""
            host = self.headers.get("Host", "")
            page_nav = (self.command == "GET" and urlparse(self.path).path in PAGES
                        and self.headers.get("Sec-Fetch-Mode", "navigate") == "navigate"
                        and self.headers.get("Sec-Fetch-Dest", "document") == "document")    # не во фрейме
            cross = self.headers.get("Sec-Fetch-Site", "") == "cross-site" and not page_nav
            if not host_allowed(host) or cross or not origin_allowed(self.headers.get("Origin"), host):
                self._send(403, b"forbidden", "text/plain; charset=utf-8")
                return False
            return True

        def do_GET(self):
            if not self._guard():
                return
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            arg = lambda k: (qs.get(k, [""])[0] or "").strip()  # noqa: E731
            num = lambda k, d: int(arg(k)) if arg(k).isdigit() else d  # noqa: E731
            p = parsed.path

            if p in PAGES:
                name, ctype = PAGES[p]
                return self._file(os.path.join(HERE, "web", name), ctype, {
                    "X-Frame-Options": "DENY", "Content-Security-Policy": "frame-ancestors 'none'"})
            if p.startswith("/avatar/"):
                f = avatars.file_for(unquote(p[8:]))
                if not f:
                    return self._send(404, b"not found", "text/plain; charset=utf-8")
                return self._file(f, "image/png" if f.endswith(".png") else "image/jpeg")

            self._lang()
            try:
                if p == "/api/version":
                    self._json({"name": version.APP_NAME, "id": version.APP_ID, "version": version.__version__,
                                "author": version.AUTHOR, "email": version.AUTHOR_EMAIL, "repo": version.REPO_URL})
                elif p == "/api/update":
                    enabled = read(db_path, rules.get_prefs)["update_check"]
                    self._json(updates.status(enabled, force=arg("force") == "1"))
                elif p == "/api/messages":
                    after = arg("after")
                    ids = [int(x) for x in arg("ids").split(",") if x.isdigit()][:5000]
                    data, rver, pver = query(
                        db_path, after=int(after) if after.isdigit() else None,
                        limit=max(1, min(1000, num("limit", 100))), app=arg("app"), q=arg("q"),
                        unread=arg("unread") == "1", widget=arg("rules") == "1", ids=ids)
                    self._json(data, headers={"X-Rules-Ver": rver, "X-Prefs-Ver": pver})
                elif p == "/api/sources":
                    self._json(sources(db_path, apply_rules=arg("rules") == "1"))
                elif p == "/api/visible":
                    self._json(visible_ids(db_path))
                elif p == "/api/column" and arg("src"):
                    st = column_state(db_path, arg("src"))
                    st.pop("ids")
                    self._json(st)
                elif p == "/api/mail":
                    self._json({"channel": read(db_path, mail.channel),
                                "accounts": read(db_path, mail.public_accounts), "presets": mail.PRESETS})
                elif p == "/api/search":
                    self._json(search(db_path, q=arg("q"), src=arg("src"), chat=arg("chat"),
                                      date_from=arg("from"), date_to=arg("to"), status=arg("status") or "all",
                                      limit=max(1, min(200, num("limit", 50))), offset=num("offset", 0)))
                elif p == "/api/why":
                    self._json(read(db_path, rules.why, num("id", 0))
                               or {"error": L("Нет такого сообщения", "No such message")})
                elif p == "/api/settings/sources":
                    self._json(read(db_path, rules.overview))
                elif p == "/api/settings/source" and arg("src"):
                    self._json(read(db_path, rules.detail, arg("src")))
                elif p == "/api/settings/rules":
                    self._json(read(db_path, rules.global_rules))
                elif p == "/api/prefs":
                    self._json(read(db_path, _prefs_view))
                elif p == "/api/stats":
                    self._json(read(db_path, stats.stats, num("days", 0), arg("src")))
                elif p == "/api/data":
                    self._json(data_info(db_path))
                elif p == "/api/backups":
                    self._json(backup.list_backups())
                elif p == "/api/report/preview":
                    self._json({"text": read(db_path, report.build)})
                elif p == "/api/forward":
                    self._json(actions.public_cfg())
                elif p == "/api/rag/status":
                    self._json(read(db_path, rag.status))
                elif p == "/api/ingest/config":
                    self._json({"token": ingest.load_token(),
                                "bind": read(db_path, lambda c: rules.get_prefs(c)["ingest_bind"])})
                elif p == "/api/themed":
                    self._json(themed_info(db_path))
                elif p == "/api/logs":
                    self._json(applog.query(arg("level") or "all", arg("q"), arg("src"),
                                            max(1, min(5000, num("limit", 1000)))))
                elif p == "/api/diag":
                    self._json(diag.checks(db_path))
                elif p == "/api/autostart":
                    self._json(diag.autostart_status())
                else:
                    self._send(404, b"not found", "text/plain; charset=utf-8")
            except sqlite3.OperationalError as e:
                self._json({"error": str(e)}, 503)

        def do_POST(self):
            if not self._guard():
                return
            p = urlparse(self.path).path
            self._lang()
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                self._send(415, b"application/json expected", "text/plain; charset=utf-8")
                return
            if p == "/api/ingest" and not ingest.authorized(self.headers.get("Authorization")):
                return self._json({"error": L("Неверный ключ приёма событий", "Bad ingest key")}, 401)
            try:
                size = int(self.headers.get("Content-Length") or 0)
                cap = 1024 * 1024 if p == "/api/config/import" else 65536
                payload = json.loads(self.rfile.read(min(size, cap)) or b"{}")
                if not isinstance(payload, dict):
                    raise BadRequest(L("Ожидался JSON-объект", "Expected a JSON object"))
                self._json(self._post(p, payload))
            except LookupError:
                self._send(404, b"not found", "text/plain; charset=utf-8")
            except Conflict as e:
                self._json(dict(e.data, error=str(e)), 409)
            except (BadRequest, ValueError, TypeError, AttributeError) as e:
                self._json({"error": str(e) or L("Неверный запрос", "Bad request")}, 400)
            except sqlite3.OperationalError as e:
                self._json({"error": str(e)}, 503)
            except OSError as e:          # Ollama/Telegram недоступны, диск и т.п.
                self._json({"error": str(e)}, 502)

        def _post(self, p, payload):
            if p == "/api/read":
                return {"updated": write(db_path, mark_read, _ids(payload), bool(payload.get("unread")))}
            if p == "/api/restore":
                return {"updated": write(db_path, restore, _ids(payload))}
            if p == "/api/pin":
                return {"updated": write(db_path, set_pinned, _ids(payload), bool(payload.get("pinned")))}
            if p == "/api/snooze":
                if payload.get("preset") not in SNOOZE_PRESETS:
                    raise BadRequest(L("Неизвестный вариант «отложить»", "Unknown snooze option"))
                n, until = write(db_path, set_snooze, _ids(payload), payload["preset"])
                return {"updated": n, "until": until}
            if p == "/api/ingest":
                return ingest.accept_api(db_path, payload)
            if p == "/api/event":
                if payload.get("kind") != "command":
                    raise BadRequest(L("Неизвестное событие", "Unknown event"))
                return events.command(db_path, payload)
            if p == "/api/logs/clear":
                return {"cleared": applog.clear()}
            if p == "/api/logs/export":
                path, n = export_logs(str(payload.get("level") or "all"), str(payload.get("q") or ""))
                return {"path": path, "rows": n}
            if p == "/api/logs/client":
                return {"ok": applog.client_error(payload)}
            if p == "/api/close-column":
                return close_column(db_path, str(payload.get("src") or ""))
            if p == "/api/reopen-column":
                return reopen_column(db_path, str(payload.get("src") or ""), _ids(payload))
            if p == "/api/mail/channel":
                ch = payload.get("channel")
                if ch not in ("notify", "imap"):
                    raise BadRequest(L("Канал почты — notify или imap", "Mail channel must be notify or imap"))

                def upd(conn):
                    # письма, пришедшие, пока почта шла уведомлениями, уже в базе — не дублируем
                    if ch == "imap" and mail.channel(conn) != "imap":
                        mail.forget(conn)
                    rules.set_prefs(conn, {"mail_channel": ch})
                write(db_path, upd)
                return {"channel": ch}
            if p == "/api/mail/account":
                write(db_path, mail.save_account, payload)
                return {"accounts": read(db_path, mail.public_accounts)}
            if p == "/api/mail/delete":
                write(db_path, mail.delete_account, str(payload.get("id") or ""))
                return {"accounts": read(db_path, mail.public_accounts)}
            if p == "/api/mail/test":
                ok, err, n = mail.test(payload)
                return {"ok": ok, "error": err, "count": n}
            if p == "/api/mail/check":
                return {"new": mail.check_now(db_path, str(payload.get("id") or "")),
                        "accounts": read(db_path, mail.public_accounts)}
            if p == "/api/rules":
                write(db_path, rules.save_rule, rules.clean_rule(payload))
                return {"ok": True}
            if p == "/api/rules/delete":
                return {"ok": True, "deleted": write(db_path, rules.delete_rule, int(payload.get("id")))}
            if p == "/api/source-mode":
                src, mode = payload.get("src"), payload.get("mode")
                if not isinstance(src, str) or not src or mode not in rules.VIS_ACTIONS:
                    raise BadRequest(L("Нужны источник и режим show/hide", "A source and show/hide mode are needed"))
                write(db_path, rules.set_mode, src, mode)
                return {"ok": True}
            if p == "/api/prefs":
                write(db_path, rules.set_prefs, payload)
                return read(db_path, _prefs_view)
            if p == "/api/purge":
                days = int(payload.get("days"))
                if days < 1:
                    raise BadRequest(L("Срок — от 1 дня", "The period must be at least 1 day"))
                return {"deleted": write(db_path, purge, days)}
            if p == "/api/export":
                fmt = payload.get("format")
                if fmt not in ("csv", "json"):
                    raise BadRequest(L("Формат — csv или json", "Format must be csv or json"))
                path, n = export(db_path, fmt, int(payload.get("days") or 0))
                return {"path": path, "rows": n}
            if p == "/api/config/export":
                path, n = export_config(db_path)
                return {"path": path, "rules": n}
            if p == "/api/config/import":
                return write(db_path, rules.import_config, payload.get("data"), bool(payload.get("replace")))
            if p == "/api/backups/make":
                return {"name": backup.make(db_path, "manual"), "backups": backup.list_backups()}
            if p == "/api/backups/restore":
                return {"before": backup.restore(db_path, str(payload.get("name") or ""))}
            if p == "/api/report/send":
                text = read(db_path, report.build)
                ok, err = actions.send(text)
                return {"ok": ok, "error": err, "text": text}
            if p == "/api/forward":
                actions.save_cfg(str(payload.get("token") or ""), str(payload.get("chat_id") or ""),
                                 str(payload.get("thread_id") or ""))
                return actions.public_cfg()
            if p == "/api/forward/test":
                ok, err = actions.send(L(f"✅ {version.APP_NAME}: проверка пересылки. Если вы это видите — всё настроено.",
                                         f"✅ {version.APP_NAME}: forwarding test. If you see this, it works."))
                return {"ok": ok, "error": err}
            if p == "/api/rag/install":
                rag.install(db_path, str(payload.get("model") or "bge-m3").strip(),
                            str(payload.get("chat_model") or "").strip())
                return {"ok": True}
            if p == "/api/rag/disable":
                write(db_path, rag.disable, bool(payload.get("drop")))
                return {"ok": True}
            if p == "/api/rag/remove-model":
                rag.remove_model(str(payload.get("model") or ""))
                return {"ok": True}
            if p == "/api/rag/search":
                q = str(payload.get("q") or "").strip()
                if not q:
                    raise BadRequest(L("Пустой запрос", "Empty query"))
                return {"rows": rag_rows(db_path, read(db_path, rag.search, q, int(payload.get("k") or 30)))}
            if p == "/api/rag/ask":
                q = str(payload.get("q") or "").strip()
                if not q:
                    raise BadRequest(L("Пустой вопрос", "Empty question"))
                rows = rag_rows(db_path, read(db_path, rag.search, q, 12))
                answer, model = read(db_path, rag.ask, q, {r["id"]: r for r in rows})
                return {"answer": answer, "model": model, "rows": rows}
            if p == "/api/ingest/token":
                return {"token": ingest.new_token()}
            if p == "/api/autostart":
                return diag.set_autostart(str(payload.get("which")), bool(payload.get("enabled")))
            if p == "/api/restart":
                diag.restart_later(str(payload.get("which")))
                return {"ok": True}
            raise LookupError(p)

    return Handler


def prepare(db_path):
    """Перед стартом: перенести файлы старых версий в XDG-папки и досоздать схему."""
    if os.path.abspath(db_path) == paths.DB_PATH:
        paths.migrate_legacy()
    else:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = catcher.init_db(db_path)
    try:
        events.migrate(conn)
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Веб-просмотр перехваченных сообщений (реалтайм)")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--version", action="version", version=version.version_line())
    args = ap.parse_args()

    prepare(args.db)
    start_background(args.db)
    httpd = ThreadingHTTPServer((args.host, args.port), make_handler(args.db))
    url = f"http://{args.host}:{args.port}"
    print(f"{version.version_line()} — только просмотр. Смотрю БД: {args.db}")
    print(f"Открой в браузере: {url}   (Ctrl+C — остановить)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
