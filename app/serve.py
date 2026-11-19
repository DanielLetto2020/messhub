#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Локальный HTTP-сервер (stdlib): страницы виджета/настроек и их API.

  Страницы и файлы:
    / и /widget → widget.html (в браузере — та же доска)     /settings → settings.html
    /message?id=N → message.html — отдельное окно: сообщение и лог целиком
    /find?q=… → find.html — результаты поиска из шапки доски (окно выпадает над панелью)
    /i18n.js — переводы страниц     /common.js — общие esc(), api(), буфер обмена
                         (её подключают все страницы вместо копий в каждой)
    /avatar/<файл> — аватары из уведомлений

  Сообщения:
    GET /api/messages   последние N (JSON); &after=ID — только новые (id > ID);
                        &limit=N &app=… &q=подстрока &ids=1,2,3 &unread=1
                        &rules=1 — «как видит виджет»: правила показа, без отложенного,
                                   плюс highlight (цвет) и mention (упоминание)
                        заголовки X-Rules-Ver / X-Prefs-Ver — версии правил и настроек
    GET /api/sources    источники [{key,name,ico,rank}] (&rules=1 — плюс hidden) и свои колонки (my:…)
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

  Настройки: /api/settings/sources|source|rules, /api/rules(/delete) (у «перенести в колонку» — ещё ico),
    /api/source-mode,
    /api/prefs, /api/stats, /api/data, /api/purge, /api/export, /api/config/export|import,
    /api/backups(/make|/restore), /api/report/preview|send, /api/forward(/test),
    /api/rag/status|install|disable|retry|remove-model|search|ask, /api/ingest/config|token, /api/session/token (сменить токен сеанса; см. session.py),
    /api/diag, /api/autostart, /api/restart, /api/version, /api/update (новая версия на GitHub),
    /api/mail (ящики IMAP, см. mail.py) + /api/mail/channel|account|delete|test|check
    /api/telegram (прямой канал MTProto, см. tgdirect.py) + /api/telegram/channel|install-lib|auth/send-code|auth/sign-in|auth/cancel|settings|reconnect|logout

  Настройка уведомлений приложений (appsetup.py):
    GET  /api/notify-setup — проверка системы, браузеров и приложений
    POST /api/notify-setup/gnome {slug, enable} | /api/notify-setup/open-os |
         /api/notify-setup/open-browser {browser_id} | /api/notify-setup/test

  Прочее:
    GET  /api/quiet (луна и «Не беспокоить»), /api/scripts (свои источники из sources.d)
    POST /api/quiet {action}, /api/remind {id, at}, /api/remind/cancel {id},
         /api/logwatch/preview {watch}, /api/scripts/example|run|open

  Все пути перечислены в GET_ROUTES и POST_ROUTES (словари «путь → функция»); каждый
  упомянут в этом докстринге - проверяет tests/test_api.py.

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
import appsetup
import avatars
import backup
import calendar_src
import catcher
import containers
import diag
import events
import i18n
import ingest
import logwatch
import mail
import paths
import rag
import report
import quiet
import reminders
import resources
import rules
import scripts
import services
import session
import stats
import tgdirect
import updates
import when
import version
from i18n import L

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = paths.DB_PATH
PAGES = {
    "/": ("widget.html", "text/html; charset=utf-8"),
    "/widget": ("widget.html", "text/html; charset=utf-8"),
    "/settings": ("settings.html", "text/html; charset=utf-8"),
    "/message": ("message.html", "text/html; charset=utf-8"),     # окно одного сообщения: /message?id=N
    "/find": ("find.html", "text/html; charset=utf-8"),           # результаты поиска из шапки доски
    "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
    "/common.js": ("common.js", "text/javascript; charset=utf-8"),
}

AUTO_READ_HOURS = 24      # лежит в БД дольше — считается прочитанным
TS = "%Y-%m-%d %H:%M:%S"

FIELDS = ("id", "app", "site", "chat", "sender", "is_bot", "message", "has_media",
          "urgency", "event_iso", "received_at", "is_read", "pinned", "snooze_until", "avatar",
          "resolved_at", "details", "fmt")


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
        s0 = rules.source_of(d["app"], d.get("site") or "", self.names)
        text = d.get("message") or ""
        # правило «перенести в колонку» ставит сообщение в свою колонку; видимость и подсветку решают
        # по-прежнему правила источника (rsrc), а откуда оно — видно по orig_*
        s = rules.place(self.rs, s0, d["chat"], d["sender"], text, self.names)
        sub, sub_name = rules.sub_of(d["app"], d.get("site") or "", d.get("chat") or "")
        d.update(src=s["key"], src_name=s["name"], src_ico=s["ico"], src_rank=s["rank"], sub=sub, sub_name=sub_name,
                 rsrc=s0["key"], highlight=self.rs.highlight(s0["key"], d["chat"], d["sender"], text),
                 mention=bool(self.mre and self.mre.search(text)))
        if s is not s0:
            d.update(orig_src=s0["key"], orig_name=s0["name"], orig_ico=s0["ico"])
        return d

    def times(self, d):
        """Будущие дата/время из текста — «⏰» на плашке (кроме своих служебных колонок)."""
        if not self.prefs["time_hints"] or (d.get("app") or "").startswith("messhub-") or not d.get("event_iso"):
            return []
        try:
            base = datetime.fromisoformat(d["event_iso"][:19])
        except ValueError:
            return []
        return when.find(d.get("message") or "", base)

    def visible(self, d):
        return bool(d.get("pinned")) or self.rs.visible(d.get("rsrc") or d["src"], d["chat"], d["sender"],
                                                        d.get("message") or "")


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
        if widget or ids:                    # доска и окно сообщения: «⏰» и заведённые напоминания
            rem = reminders.for_ids(conn, [d["id"] for d in out])
            for d in out:
                d["times"] = v.times(d)
                d["remind_at"] = rem.get(d["id"], "")
        return out, v.rs.ver, rules.prefs_ver(v.prefs)
    finally:
        conn.close()


def _casefold(s):
    return s.casefold() if isinstance(s, str) else s


def src_where(conn, src, names):
    """SQL-условие «сообщения из колонки src» по парам (app, site) → (фрагмент, параметры).

    Колонку определяет rules.source_of, но он считается на Python, поэтому условие строится по
    реальным парам из базы (их единицы, не строки). None — выразить нельзя: свои колонки
    (my:…) собирает правило «перенести в колонку» по тексту сообщения, это решается построчно."""
    if src.startswith(rules.MY_PREFIX):
        return None
    keep = [(r[0], r[1] or "") for r in conn.execute("SELECT DISTINCT app, site FROM messages")
            if rules.source_of(r[0], r[1] or "", names)["key"] == src]
    if not keep:
        return "0", []                        # ни одного приложения/сайта не попадает в колонку
    frag = "(" + " OR ".join(["(app = ? AND COALESCE(site, '') = ?)"] * len(keep)) + ")"
    return frag, [x for pair in keep for x in pair]


def _search_where(q, chat, date_from, date_to, status, prefix=""):
    """Условия выборки поиска (без источника) → (фрагмент, параметры). prefix — псевдоним
    таблицы, чтобы этим же кодом собирать условие и для messages, и для другого запроса."""
    where, params = [], []
    if q:
        # подстрока без учёта регистра, в т.ч. кириллица: встроенный LIKE SQLite это не умеет,
        # поэтому своя функция cf() и LIKE по её результату
        pat = "%" + q.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(" + " OR ".join(f"cf({prefix}{col}) LIKE ? ESCAPE '\\'"
                                       for col in ("message", "chat", "sender")) + ")")
        params += [pat] * 3
    if chat:
        where.append(f"{prefix}chat = ?"); params.append(chat)
    if date_from:
        where.append(f"{prefix}received_at >= ?"); params.append(date_from)
    if date_to:
        where.append(f"{prefix}received_at < ?")
        params.append((datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d"))
    if status == "unread":
        where.append(f"{prefix}is_read = 0")
    elif status == "read":
        where.append(f"{prefix}is_read = 1")
    elif status == "pinned":
        where.append(f"{prefix}pinned = 1")
    return where, params


def _where_sql(where):
    return (" WHERE " + " AND ".join(where)) if where else ""


def search(db_path, q="", src="", chat="", date_from="", date_to="", status="all", limit=50, offset=0):
    """Поиск по истории: подстрока без учёта регистра (в т.ч. кириллица — встроенный
    LIKE SQLite этого не умеет) по тексту, чату и отправителю + фильтры.

    Источник, если он выразим в SQL (src_where), и постраничный отбор делает база: раньше
    подряд читались все строки, каждая прогонялась через правила, и только потом брались
    нужные 50 — на 20 тыс. сообщений это 0.3 с вместо 0.002 с."""
    if not os.path.exists(db_path):
        return {"total": 0, "rows": []}
    conn = open_db(db_path)
    conn.create_function("cf", 1, _casefold, deterministic=True)
    try:
        v = View(conn)
        sw = src_where(conn, src, v.names) if src else None
        has_move_from = bool(src) and any(r["src"] in (src, "*") for r in v.rs.rows if r["action"] == "move")
        if src and (sw is None or has_move_from):
            return _search_scan(conn, v, q, src, chat, date_from, date_to, status, limit, offset, sw=sw)
        where, params = _search_where(q, chat, date_from, date_to, status)
        if sw:
            where = [sw[0]] + where
            params = sw[1] + params
        wsql = _where_sql(where)
        rows, total = _search_page(conn, v, FIELDS, wsql, params, limit, offset, count_in_page=bool(q))
        for d in rows:
            d["visible"] = v.visible(d)
        return {"total": total, "rows": rows}
    finally:
        conn.close()


def _search_page(conn, v, fields, wsql, params, limit, offset, count_in_page):
    """Страница результатов и их всего. С текстовым фильтром считаем и берём страницу
    одним проходом (оконная функция): два прохода с casefold на каждой строке вдвое дороже.
    Без текста считаем отдельно - там COUNT быстрый, а оконная функция заставляет
    вычитать все строки. На сборках SQLite без оконных функций - просто два запроса."""
    if count_in_page:
        try:
            out = list(conn.execute(
                f"SELECT {', '.join(fields)}, COUNT(*) OVER () AS _n FROM messages{wsql} "
                f"ORDER BY id DESC LIMIT ? OFFSET ?", [*params, limit, offset]))
        except sqlite3.OperationalError:
            out = None
        if out is not None:
            total = out[0]["_n"] if out else 0
            if not out:                 # страница за концом - считать всё равно нужно
                total = conn.execute(f"SELECT COUNT(*) FROM messages{wsql}", params).fetchone()[0]
            return [v.row({k: r[k] for k in fields}) for r in out], total
    total = conn.execute(f"SELECT COUNT(*) FROM messages{wsql}", params).fetchone()[0]
    rows = [v.row(dict(r)) for r in conn.execute(
        f"SELECT {', '.join(fields)} FROM messages{wsql} ORDER BY id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset])]
    return rows, total


def _empty_my_column(v, src):
    """Свою колонку наполняет правило «перенести в колонку». Если такого правила нет,
    колонка пуста - и перебор всей базы ради неё не нужен."""
    return src not in v.rs.my_columns()


def _search_scan(conn, v, q, src, chat, date_from, date_to, status, limit, offset, sw=None):
    """Поиск с построчным фильтром через правила (свои колонки my:… или источники с правилом move)."""
    if sw is None and _empty_my_column(v, src):
        return {"total": 0, "rows": []}
    where, params = _search_where(q, chat, date_from, date_to, status)
    if sw is not None:
        where = [sw[0]] + where
        params = sw[1] + params
    wsql = _where_sql(where)
    rows = []
    for r in conn.execute(f"SELECT {', '.join(FIELDS)} FROM messages{wsql} ORDER BY id DESC", params):
        d = v.row(dict(r))
        if d["src"] != src:
            continue
        rows.append(d)
    page = rows[offset:offset + limit]
    for d in page:
        d["visible"] = v.visible(d)
    return {"total": len(rows), "rows": page}


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
        # свои колонки (правило «перенести в колонку») — есть, пока есть правило, даже пустые
        for name in rs.my_columns().values():
            m = rules.my_meta(name, prefs["source_names"])
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


_visible_cache = {"key": None, "val": None}
_visible_lock = threading.Lock()


def _board_key(conn, v, now):
    """Подпись состояния доски: что изменилось с прошлого запроса /api/visible.

    max(id) и суммы id по флагам ловят новые сообщения, любые изменения «прочитано»,
    «закреплено», активных отложенных (snooze_until > now) и «починилось» (даже при одновременных
    взаимных переключениях), а версии правил и настроек — их правку."""
    unread = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(id), 0), "
        "COALESCE(SUM(CASE WHEN is_read = 0 THEN id ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN pinned = 1 THEN id ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN snooze_until IS NOT NULL AND snooze_until > ? THEN id ELSE 0 END), 0), "
        "COALESCE(SUM(CASE WHEN resolved_at IS NOT NULL THEN id ELSE 0 END), 0), "
        "COALESCE(MAX(resolved_at), '') "
        "FROM messages "
        "WHERE is_read = 0 OR pinned = 1 OR (snooze_until IS NOT NULL AND snooze_until > ?) OR resolved_at IS NOT NULL",
        (now, now),
    ).fetchone()
    return (conn.execute("SELECT COALESCE(MAX(id), 0) FROM messages").fetchone()[0], *unread,
            v.rs.ver, rules.prefs_ver(v.prefs))


def visible_ids(db_path):
    """Что сейчас должно быть на доске виджета (id <= max_id). Виджет спрашивает это раз в
    15 с, а пересборка ответа — это прогон всех непрочитанных строк через правила. Между
    сообщениями это десятки тысяч вычислений впустую, поэтому результат кэшируем по подписи
    состояния (см. _board_key): пока база и правила не менялись, отдаём прошлый."""
    if not os.path.exists(db_path):
        return {"max_id": 0, "ids": []}
    conn = open_db(db_path)
    try:
        v, now = View(conn), catcher.msk_time()
        sign = _board_key(conn, v, now)
        key = (os.path.abspath(db_path), sign)
        with _visible_lock:
            if _visible_cache["key"] == key:
                return _visible_cache["val"]
        rows = _visible_rows(conn, v, sign[0], now)
        val = {"max_id": sign[0], "ids": [r["id"] for r in rows],
               "resolved": {str(r["id"]): r["resolved_at"] for r in rows if r.get("resolved_at")},
               "pinned": [r["id"] for r in rows if r.get("pinned")]}   # закрепили в окне сообщения
        with _visible_lock:
            _visible_cache.update(key=key, val=val)
        return val
    finally:
        conn.close()


def _visible_rows(conn, v, max_id, now):
    """Непрочитанные, которые виджет должен показать (до max_id), — как видит правила."""
    out = []
    for r in conn.execute(f"SELECT {', '.join(FIELDS)} FROM messages "
                          f"WHERE is_read = 0 AND id <= ? AND (snooze_until IS NULL OR snooze_until <= ?) "
                          f"ORDER BY id", (max_id, now)):
        d = v.row(dict(r))
        if v.visible(d):
            out.append(d)
    return out


def column_state(db_path, src):
    """Что сейчас в колонке: непрочитанные видимые (их прочитает «закрыть»),
    закреплённые и отложенные (из-за них закрыть нельзя)."""
    conn = open_db(db_path)
    try:
        v, now = View(conn), catcher.msk_time()
        sw = src_where(conn, src, v.names)
        ids, pinned, snoozed = [], 0, 0
        if sw is None and _empty_my_column(v, src):
            return {"src": src, "unread": 0, "ids": [], "pinned": 0, "snoozed": 0}
        if sw is None:                      # своя колонка: решает правило, в SQL не отсечь
            rows = conn.execute(f"SELECT {', '.join(FIELDS)} FROM messages WHERE is_read = 0")
        else:
            rows = conn.execute(f"SELECT {', '.join(FIELDS)} FROM messages WHERE is_read = 0 AND {sw[0]}", sw[1])
        for r in rows:
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
    """Сообщения вернули в виджет — их закрытые колонки (и свои, куда их переносит правило) снова открыты."""
    prefs = rules.get_prefs(conn)
    if prefs["closed_cols"] and ids:
        v = View(conn)
        _reopen(conn, {v.row(dict(zip(FIELDS, r)))["src"] for r in conn.execute(
            f"SELECT {', '.join(FIELDS)} FROM messages WHERE id IN ({_in(ids)})", ids)})


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
    """Вернуть в виджет: непрочитано и не отложено. Время записи сдвигаем на «сейчас»,
    иначе авто-прочтение сразу (или через час-другой) заберёт старое сообщение снова."""
    if not ids:
        return 0
    _reopen_for(conn, ids)
    return conn.execute(f"""UPDATE messages SET is_read = 0, read_at = NULL, snooze_until = NULL,
                               received_at = MAX(received_at, ?) WHERE id IN ({_in(ids)})""",
                        [catcher.msk_time(), *ids]).rowcount


def set_pinned(conn, ids, pinned):
    if not ids:
        return 0
    return conn.execute(f"UPDATE messages SET pinned = ? WHERE id IN ({_in(ids)})",
                        [1 if pinned else 0, *ids]).rowcount


SNOOZE_PRESETS = ("1h", "3h", "evening", "tomorrow")


def snooze_until(preset):
    """До какого времени отложить: расчёт в местном времени, запись в БД по МСК.
    «Вечером» — 19:00 (после 18:00 — завтра 19:00), «Завтра» — 09:00."""
    local_now = datetime.now().astimezone()
    if preset == "1h":
        t = local_now + timedelta(hours=1)
    elif preset == "3h":
        t = local_now + timedelta(hours=3)
    elif preset == "evening":
        t = local_now.replace(hour=19, minute=0, second=0, microsecond=0) + \
            timedelta(days=1 if local_now.hour >= 18 else 0)
    else:
        t = (local_now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return t.astimezone(catcher.MSK).strftime(TS)


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
    conn.execute(f"DELETE FROM reminders WHERE message_id IN ({old})", (cutoff,))
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
            except Exception as e:  # noqa: BLE001 — любая ошибка не должна навсегда останавливать авто-прочтение
                print(f"Фоновые задачи: ошибка: {e!r}", flush=True)
            tick += 1
            time.sleep(60)

    def rag_loop():
        # сбойные тексты считаются по кускам (rag.index_step); Ollama недоступна — пауза растёт до 5 минут,
        # пропущенные сообщения пробуются снова при запуске и раз в сутки
        pause, retry_at = 20, 0.0
        while True:
            n = 0
            if time.time() >= retry_at:
                try:
                    rag.retry_skipped(db_path)
                except sqlite3.Error:
                    pass
                retry_at = time.time() + 86400
            try:
                n = rag.index_step(db_path)
                pause = 20
            except Exception as e:  # noqa: BLE001 — Ollama выключили, модель удалили — не падаем
                msg = rag.human_error(e)
                if msg != rag.state["error"]:
                    applog.warn(f"Умный поиск: векторы не посчитались ({msg}), повторяю сам")
                rag.state.update(error=msg, retry_at=time.time() + pause)
                time.sleep(pause)
                pause = min(300, pause * 2)
                continue
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
    run_exe = "messhub-run.exe" if os.name == "nt" else "messhub-run"     # в сборке — рядом с messhub(.exe)
    run_cmd = (f'"{os.path.join(os.path.dirname(os.path.abspath(sys.executable)), run_exe)}" -- …'
               if getattr(sys, "frozen", False) else
               "messhub run -- …" if HERE.startswith("/usr/lib/") else f"python3 {os.path.join(HERE, 'run.py')} -- …")
    hook = "" if os.name == "nt" else (      # хук шлёт notify-send — он есть на Linux
        "source /usr/lib/messhub/hooks/long-command.sh" if HERE.startswith("/usr/lib/")
        else f"source {os.path.join(HERE, 'hooks', 'long-command.sh')}")
    demo = os.environ.get(f"{paths.ENV_PREFIX}_THEMED_DEMO") == "1"      # снимки экрана: без настоящих движков
    cont = ({"podman": {"found": True, "running": True, "error": "", "events": 128},
             "docker": {"found": True, "running": False, "events": 0,
                        "error": containers.human_error("docker", "permission denied")}} if demo
            else containers.public_status())
    serv = (dict(services.public_status(), found=True, running=True, error="", failed=1) if demo
            else services.public_status())
    res = (dict(resources.public_status(), running=True, values={"disk /": "72%", "memory": "41%", "cpu": "54°C",
                                                                  "gpu0": "49°C"}) if demo else resources.public_status())
    cal = calendar_src.public_status()
    cal_srcs = [p.replace(os.path.expanduser("~"), "~") for p, _ in calendar_src.sources(rules.themed(prefs)["calendar"]["files"])]
    if demo:
        cal, cal_srcs = dict(cal, running=True, events=4, sources=2), ["~/.local/share/evolution/calendar/system/calendar.ics",
                                                                     "~/Календари/работа.ics"]
    return {"prefs": rules.themed(prefs),
            "platform": "windows" if os.name == "nt" else "linux",
            "containers": cont, "services": serv, "commands": {"run": run_cmd, "hook": hook},
            "resources": res, "logwatch": logwatch.public_status(), "calendar": dict(cal, files=cal_srcs),
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


class Json:
    """Ответ, которому нужен не только код 200: Json(данные, code=…, headers=…)."""

    def __init__(self, data, code=200, headers=None):
        self.data = data
        self.code = code
        self.headers = headers


class Req:
    """Параметры одного запроса: база, путь, строка запроса и тело."""

    def __init__(self, db, path, query, payload):
        self.db = db
        self.path = path
        self.q = query
        self.payload = payload

    def arg(self, key, default=""):
        v = (self.q.get(key, [""])[0] or "").strip()
        return v or default

    def num(self, key, default=0):
        v = self.arg(key)
        return int(v) if v.isdigit() else default

    def flag(self, key):
        return self.arg(key) == "1"

    def query_ids(self):
        return [int(x) for x in self.arg("ids").split(",") if x.isdigit()][:5000]


# ── маршруты ─────────────────────────────────────────────────────────────────
# Маршруты - обычные словари «путь → функция», а не цепочки if/elif: все ~90 путей видно
# в одном месте, по ним можно пройтись (tools/route_check.py печатает список и сверяет
# с докстрингом модуля). Функция возвращает данные ответа, Json(...) - если нужен другой
# код или заголовки, и бросает исключение - оно превращается в код ответа в do_GET/do_POST.

def _r_version(c):
    return {"name": version.APP_NAME, "id": version.APP_ID, "version": version.__version__,
            "author": version.AUTHOR, "email": version.AUTHOR_EMAIL, "repo": version.REPO_URL}


def _r_update(c):
    return updates.status(read(c.db, rules.get_prefs)["update_check"], force=c.flag("force"))


def _r_messages(c):
    after = c.num("after") if c.arg("after").isdigit() else None
    data, rver, pver = query(c.db, after=after,
                             limit=max(1, min(1000, c.num("limit", 100))),
                             app=c.arg("app"), q=c.arg("q"),
                             unread=c.flag("unread"), widget=c.flag("rules"), ids=c.query_ids())
    q = quiet.current
    return Json(data, headers={"X-Rules-Ver": rver, "X-Prefs-Ver": pver,
                               "X-Quiet": f"{int(bool(q['active']))};{q['reason']};{q['until']}"})


def _r_sources(c):
    return sources(c.db, apply_rules=c.flag("rules"))


def _r_visible(c):
    return visible_ids(c.db)


def _r_column(c):
    src = c.arg("src")
    if not src:
        return Json({"error": L("Нужен источник", "A source is needed")}, 400)
    st = column_state(c.db, src)
    st.pop("ids")                     # сами id на доске уже есть (их берёт /api/messages)
    return st


def _r_search(c):
    return search(c.db, q=c.arg("q"), src=c.arg("src"), chat=c.arg("chat"),
                  date_from=c.arg("from"), date_to=c.arg("to"), status=c.arg("status") or "all",
                  limit=max(1, min(200, c.num("limit", 50))), offset=c.num("offset", 0))


def _r_why(c):
    return read(c.db, rules.why, c.num("id")) or \
        {"error": L("Нет такого сообщения", "No such message")}


def _r_quiet(c):
    st = quiet.public_status()
    if os.environ.get(f"{paths.ENV_PREFIX}_THEMED_DEMO") == "1" and st["dnd"] is None:
        st["dnd"] = False             # снимки экрана: как на GNOME, «Не беспокоить» выключено
    return dict(st, prefs=read(c.db, rules.get_prefs)["quiet"])


def _r_scripts(c):
    return dict(scripts.info(c.db), dir=scripts.DIR.replace(os.path.expanduser("~"), "~")
                if os.environ.get(f"{paths.ENV_PREFIX}_THEMED_DEMO") else scripts.DIR)


def _r_logs(c):
    return applog.query(c.arg("level") or "all", c.arg("q"), c.arg("src"),
                        max(1, min(5000, c.num("limit", 1000))))


def _r_setting_source(c):
    src = c.arg("src")
    return read(c.db, rules.detail, src) if src else \
        Json({"error": L("Нужен источник", "A source is needed")}, 400)


GET_ROUTES = {
    "/api/version": _r_version,
    "/api/update": _r_update,
    "/api/messages": _r_messages,
    "/api/sources": _r_sources,
    "/api/visible": _r_visible,
    "/api/column": _r_column,
    "/api/mail": lambda c: {"channel": read(c.db, mail.channel),
                            "accounts": read(c.db, mail.public_accounts),
                            "presets": mail.PRESETS},
    "/api/telegram": lambda c: read(c.db, tgdirect.public_status),
    "/api/search": _r_search,
    "/api/why": _r_why,
    "/api/settings/sources": lambda c: read(c.db, rules.overview),
    "/api/settings/source": _r_setting_source,
    "/api/settings/rules": lambda c: read(c.db, rules.global_rules),
    "/api/prefs": lambda c: read(c.db, _prefs_view),
    "/api/stats": lambda c: read(c.db, stats.stats, c.num("days"), c.arg("src")),
    "/api/data": lambda c: data_info(c.db),
    "/api/backups": lambda c: backup.list_backups(),
    "/api/report/preview": lambda c: {"text": read(c.db, report.build)},
    "/api/forward": lambda c: actions.public_cfg(),
    "/api/rag/status": lambda c: read(c.db, rag.status),
    "/api/ingest/config": lambda c: {"token": ingest.load_token(),
                                      "bind": read(c.db, lambda x: rules.get_prefs(x)["ingest_bind"]),
                                      "session": session.script_help()},
    # ключ приёма событий отдаёт этот GET - поэтому он под токеном сеанса (session.GUARDED_GET).
    "/api/themed": lambda c: themed_info(c.db),
    "/api/quiet": _r_quiet,
    "/api/scripts": _r_scripts,
    "/api/logs": _r_logs,
    "/api/diag": lambda c: diag.checks(c.db),
    "/api/autostart": lambda c: diag.autostart_status(),
    "/api/notify-setup": lambda c: appsetup.inspect(c.db),
}


# POST: путь → функция(Req). Тело запроса - c.payload, база - c.db.
def _p_read(c):
    return {"updated": write(c.db, mark_read, _ids(c.payload), bool(c.payload.get("unread")))}


def _p_restore(c):
    return {"updated": write(c.db, restore, _ids(c.payload))}


def _p_pin(c):
    return {"updated": write(c.db, set_pinned, _ids(c.payload), bool(c.payload.get("pinned")))}


def _p_snooze(c):
    if c.payload.get("preset") not in SNOOZE_PRESETS:
        raise BadRequest(L("Неизвестный вариант «отложить»", "Unknown snooze option"))
    n, until = write(c.db, set_snooze, _ids(c.payload), c.payload["preset"])
    return {"updated": n, "until": until}


def _p_event(c):
    if c.payload.get("kind") != "command":
        raise BadRequest(L("Неизвестное событие", "Unknown event"))
    return events.command(c.db, c.payload)


def _p_remind(c):
    at = write(c.db, reminders.add, int(c.payload.get("id")), str(c.payload.get("at") or ""),
               str(c.payload.get("event_at") or ""))
    return {"at": at}


def _p_remind_cancel(c):
    return {"cancelled": write(c.db, reminders.cancel, int(c.payload.get("id")))}


def _p_logwatch_preview(c):
    try:
        return logwatch.preview(dict(c.payload.get("watch") or {}))
    except OSError as e:
        raise BadRequest(L(f"Не открыть: {e}", f"Can't open: {e}")) from None


def _p_scripts_open(_c):
    os.makedirs(scripts.DIR, exist_ok=True)
    if os.name == "nt":
        os.startfile(scripts.DIR)      # noqa: S606 — своя папка настроек
    else:
        subprocess.Popen(["xdg-open", scripts.DIR], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"ok": True}


def _p_mail_channel(c):
    ch = c.payload.get("channel")
    if ch not in ("notify", "imap"):
        raise BadRequest(L("Канал почты — notify или imap", "Mail channel must be notify or imap"))

    def upd(conn):
        # письма, пришедшие, пока почта шла уведомлениями, уже в базе — не дублируем
        if ch == "imap" and mail.channel(conn) != "imap":
            mail.forget(conn)
        rules.set_prefs(conn, {"mail_channel": ch})
    write(c.db, upd)
    return {"channel": ch}


def _p_mail_account(c):
    write(c.db, mail.save_account, c.payload)
    return {"accounts": read(c.db, mail.public_accounts)}


def _p_mail_delete(c):
    write(c.db, mail.delete_account, str(c.payload.get("id") or ""))
    return {"accounts": read(c.db, mail.public_accounts)}


def _p_mail_test(c):
    ok, err, n = mail.test(c.payload)
    return {"ok": ok, "error": err, "count": n}


def _p_mail_check(c):
    return {"new": mail.check_now(c.db, str(c.payload.get("id") or "")),
            "accounts": read(c.db, mail.public_accounts)}


def _p_tg_channel(c):
    ch = c.payload.get("channel")
    if ch not in ("notify", "mtproto"):
        raise BadRequest(L("Канал Telegram — notify или mtproto", "Telegram channel must be notify or mtproto"))
    write(c.db, rules.set_prefs, {"telegram_channel": ch})
    tgdirect.bump_mode()
    tgdirect.wake()
    return read(c.db, tgdirect.public_status)


def _p_tg_send_code(c):
    res = tgdirect.send_code(c.payload.get("api_id"), c.payload.get("api_hash"), c.payload.get("phone"))
    return {**res, **read(c.db, tgdirect.public_status)}


def _p_tg_sign_in(c):
    res = tgdirect.sign_in(c.db, str(c.payload.get("code") or ""), str(c.payload.get("password") or ""))
    return {**res, **read(c.db, tgdirect.public_status)}


def _p_rules(c):
    r = rules.clean_rule(c.payload)

    def save(conn):
        rules.save_rule(conn, r)
        if r["action"] == "move":          # значок своей колонки выбирают в самом правиле
            rules.set_my_icon(conn, r["param"], c.payload.get("ico"))
    write(c.db, save)
    return {"ok": True}


def _p_source_mode(c):
    src, mode = c.payload.get("src"), c.payload.get("mode")
    if not isinstance(src, str) or not src or mode not in rules.VIS_ACTIONS:
        raise BadRequest(L("Нужны источник и режим show/hide", "A source and show/hide mode are needed"))
    write(c.db, rules.set_mode, src, mode)
    return {"ok": True}


def _p_prefs(c):
    write(c.db, rules.set_prefs, c.payload)
    if "quiet" in c.payload:                # луна и раздел настроек — сразу, без ожидания фона
        write(c.db, quiet.step)
    return read(c.db, _prefs_view)


def _p_purge(c):
    days = int(c.payload.get("days"))
    if not 1 <= days <= 36500:
        raise BadRequest(L("Срок — от 1 до 36500 дней", "The period must be between 1 and 36500 days"))
    return {"deleted": write(c.db, purge, days)}


def _p_export(c):
    fmt = c.payload.get("format")
    if fmt not in ("csv", "json"):
        raise BadRequest(L("Формат — csv или json", "Format must be csv or json"))
    days = int(c.payload.get("days") or 0)
    if not 0 <= days <= 36500:
        raise BadRequest(L("Срок — от 0 до 36500 дней", "The period must be between 0 and 36500 days"))
    path, n = export(c.db, fmt, days)
    return {"path": path, "rows": n}


def _p_config_import(c):
    return write(c.db, rules.import_config, c.payload.get("data"), bool(c.payload.get("replace")))


def _p_report_send(c):
    text = read(c.db, report.build)
    ok, err = actions.send(text)
    return {"ok": ok, "error": err, "text": text}


def _p_forward(c):
    actions.save_cfg(str(c.payload.get("token") or ""), str(c.payload.get("chat_id") or ""),
                     str(c.payload.get("thread_id") or ""))
    return actions.public_cfg()


def _p_forward_test(_c):
    ok, err = actions.send(L(f"✅ {version.APP_NAME}: проверка пересылки. Если вы это видите — всё настроено.",
                             f"✅ {version.APP_NAME}: forwarding test. If you see this, it works."))
    return {"ok": ok, "error": err}


def _p_rag_install(c):
    rag.install(c.db, str(c.payload.get("model") or "bge-m3").strip(),
                str(c.payload.get("chat_model") or "").strip())
    return {"ok": True}


def _p_rag_disable(c):
    write(c.db, rag.disable, bool(c.payload.get("drop")))
    return {"ok": True}


def _p_rag_remove_model(c):
    read(c.db, lambda conn: rag.remove_model(str(c.payload.get("model") or ""), conn))
    return {"ok": True}


def _p_rag_search(c):
    q = str(c.payload.get("q") or "").strip()
    if not q:
        raise BadRequest(L("Пустой запрос", "Empty query"))
    return {"rows": rag_rows(c.db, read(c.db, rag.search, q, int(c.payload.get("k") or 30)))}


def _p_rag_ask(c):
    q = str(c.payload.get("q") or "").strip()
    if not q:
        raise BadRequest(L("Пустой вопрос", "Empty question"))
    rows = rag_rows(c.db, read(c.db, rag.search, q, 12))
    answer, model = read(c.db, rag.ask, q, {r["id"]: r for r in rows})
    return {"answer": answer, "model": model, "rows": rows}


def _p_autostart(c):
    return diag.set_autostart(str(c.payload.get("which")), bool(c.payload.get("enabled")))


def _p_restart(c):
    diag.restart_later(str(c.payload.get("which")))
    return {"ok": True}


POST_ROUTES = {
    "/api/read": _p_read,
    "/api/restore": _p_restore,
    "/api/pin": _p_pin,
    "/api/snooze": _p_snooze,
    "/api/ingest": lambda c: ingest.accept_api(c.db, c.payload),
    "/api/event": _p_event,
    "/api/quiet": lambda c: write(c.db, quiet.set_manual, str(c.payload.get("action") or "")),
    "/api/remind": _p_remind,
    "/api/remind/cancel": _p_remind_cancel,
    "/api/logwatch/preview": _p_logwatch_preview,
    "/api/scripts/example": lambda c: {"path": scripts.make_example(), **scripts.info(c.db)},
    "/api/scripts/run": lambda c: scripts.run_now(c.db, str(c.payload.get("name") or "")),
    "/api/scripts/open": _p_scripts_open,
    "/api/logs/clear": lambda c: {"cleared": applog.clear()},
    "/api/logs/export": lambda c: dict(zip(("path", "rows"),
                                           export_logs(str(c.payload.get("level") or "all"),
                                                       str(c.payload.get("q") or "")))),
    "/api/logs/client": lambda c: {"ok": applog.client_error(c.payload)},
    "/api/close-column": lambda c: close_column(c.db, str(c.payload.get("src") or "")),
    "/api/reopen-column": lambda c: reopen_column(c.db, str(c.payload.get("src") or ""), _ids(c.payload)),
    "/api/mail/channel": _p_mail_channel,
    "/api/mail/account": _p_mail_account,
    "/api/mail/delete": _p_mail_delete,
    "/api/mail/test": _p_mail_test,
    "/api/mail/check": _p_mail_check,
    "/api/telegram/channel": _p_tg_channel,
    "/api/telegram/install-lib": lambda c: {**tgdirect.install_lib(), **read(c.db, tgdirect.public_status)},
    "/api/telegram/auth/send-code": _p_tg_send_code,
    "/api/telegram/auth/sign-in": _p_tg_sign_in,
    "/api/telegram/auth/cancel": lambda c: {**tgdirect.cancel_auth(), **read(c.db, tgdirect.public_status)},
    "/api/telegram/settings": lambda c: (tgdirect.save_settings(c.payload), read(c.db, tgdirect.public_status))[1],
    "/api/telegram/reconnect": lambda c: (tgdirect.reconnect(), read(c.db, tgdirect.public_status))[1],
    "/api/telegram/logout": lambda c: {**tgdirect.logout(c.db, bool(c.payload.get("remote", True))),
                                       **read(c.db, tgdirect.public_status)},
    "/api/rules": _p_rules,
    "/api/rules/delete": lambda c: {"ok": True, "deleted": write(c.db, rules.delete_rule, int(c.payload.get("id")))},
    "/api/source-mode": _p_source_mode,
    "/api/prefs": _p_prefs,
    "/api/purge": _p_purge,
    "/api/export": _p_export,
    "/api/config/export": lambda c: dict(zip(("path", "rules"), export_config(c.db))),
    "/api/config/import": _p_config_import,
    "/api/backups/make": lambda c: {"name": backup.make(c.db, "manual"), "backups": backup.list_backups()},
    "/api/backups/restore": lambda c: {"before": backup.restore(c.db, str(c.payload.get("name") or ""))},
    "/api/report/send": _p_report_send,
    "/api/forward": _p_forward,
    "/api/forward/test": _p_forward_test,
    "/api/rag/install": _p_rag_install,
    "/api/rag/retry": lambda c: {"queued": rag.retry_skipped(c.db)},
    "/api/rag/disable": _p_rag_disable,
    "/api/rag/remove-model": _p_rag_remove_model,
    "/api/rag/search": _p_rag_search,
    "/api/rag/ask": _p_rag_ask,
    "/api/ingest/token": lambda c: {"token": ingest.new_token()},
    "/api/session/token": lambda c: {"ok": True, "token": session.rotate()},
    "/api/autostart": _p_autostart,
    "/api/restart": _p_restart,
    "/api/notify-setup/gnome": lambda c: appsetup.set_gnome_app(str(c.payload.get("slug") or ""), bool(c.payload.get("enable"))),
    "/api/notify-setup/open-os": lambda c: appsetup.open_os_settings(str(c.payload.get("kind") or "notifications")),
    "/api/notify-setup/open-browser": lambda c: appsetup.open_browser_settings(str(c.payload.get("browser_id") or "")),
    "/api/notify-setup/test": lambda c: appsetup.send_test(c.db),
}


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
            p = parsed.path

            if p in PAGES:
                name, ctype = PAGES[p]
                return self._file(os.path.join(HERE, "web", name), ctype, {
                    "X-Frame-Options": "DENY", "Content-Security-Policy": "frame-ancestors 'none'",
                    # страница получает токен сеанса cookie - дальше браузер шлёт его сам
                    # (см. session.py); скрипты и curl - заголовком X-Messhub-Token
                    "Set-Cookie": session.cookie_header()})
            if p.startswith("/avatar/"):
                f = avatars.file_for(unquote(p[8:]))
                if not f:
                    return self._send(404, b"not found", "text/plain; charset=utf-8")
                return self._file(f, "image/png" if f.endswith(".png") else "image/jpeg")

            self._lang()
            try:
                route = GET_ROUTES.get(p)
                if route is None:
                    return self._send(404, b"not found", "text/plain; charset=utf-8")
                if p in session.GUARDED_GET and not session.ok(self.headers):
                    return self._json({"error": L("Нужен токен сеанса", "Session token required"),
                                       "token_header": session.HEADER}, 401)
                result = route(Req(db_path, p, qs, {}))
                if isinstance(result, Json):
                    self._json(result.data, result.code, result.headers)
                else:
                    self._json(result)
            except sqlite3.OperationalError as e:
                self._json({"error": str(e)}, 503)
            except (ValueError, TypeError, OverflowError) as e:      # например, /api/search?to=не-дата
                self._json({"error": str(e) or L("Неверный запрос", "Bad request")}, 400)

        def do_POST(self):
            if not self._guard():
                return
            p = urlparse(self.path).path
            self._lang()
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                self._send(415, b"application/json expected", "text/plain; charset=utf-8")
                return
            if p == "/api/ingest":
                if not ingest.authorized(self.headers.get("Authorization")):
                    return self._json({"error": L("Неверный ключ приёма событий", "Bad ingest key")}, 401)
            elif not session.ok(self.headers):
                # токен сеанса: без него любой местный процесс и любая страница в этом браузере
                # могли вызвать POST (удалить базу, сменить настройки, выполнить скрипт).
                # Страница получила токен cookie вместе с собой, скрипт - заголовком.
                return self._json({"error": L("Нужен токен сеанса (см. настройки → «Система»)",
                                              "Session token required (see settings → “System”)"),
                                   "token_header": session.HEADER}, 401)
            try:
                size = int(self.headers.get("Content-Length") or 0)
                if size < 0:
                    raise ValueError("negative Content-Length")
                cap = 1024 * 1024 if p == "/api/config/import" else 65536
                payload = json.loads(self.rfile.read(min(size, cap)) or b"{}")
                if not isinstance(payload, dict):
                    raise BadRequest(L("Ожидался JSON-объект", "Expected a JSON object"))
                route = POST_ROUTES.get(p)
                if route is None:
                    return self._send(404, b"not found", "text/plain; charset=utf-8")
                result = route(Req(db_path, p, {}, payload))
                if isinstance(result, Json):
                    self._json(result.data, result.code, result.headers)
                else:
                    self._json(result)
            except LookupError:
                self._send(404, b"not found", "text/plain; charset=utf-8")
            except Conflict as e:
                self._json(dict(e.data, error=str(e)), 409)
            except (BadRequest, ValueError, TypeError, AttributeError, OverflowError) as e:
                self._json({"error": str(e) or L("Неверный запрос", "Bad request")}, 400)
            except sqlite3.OperationalError as e:
                self._json({"error": str(e)}, 503)
            except OSError as e:          # Ollama/Telegram недоступны, диск и т.п.
                self._json({"error": str(e)}, 502)

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
