#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Приём событий по HTTP — чтобы скрипты, CI, Home Assistant или другой компьютер
клали события в виджет напрямую, без notify-send:

    curl -X POST http://127.0.0.1:8765/api/ingest \\
         -H "Authorization: Bearer <ключ>" -H "Content-Type: application/json" \\
         -d '{"source": "Сборки", "chat": "CI: main", "text": "Сборка #413 прошла"}'

Поля: source (обязательно — это колонка), text (обязательно), chat, sender,
urgency (0/1/2), details (длинный хвост лога — в виджете свёрнут, в Telegram не уходит).
Дальше работают обычные правила (подсветить, закрепить, звук, переслать).

«Проблема → починилось» (как у тематических колонок, events.py): key — ключ проблемы
(например "backup:nas"). Новое событие с тем же ключом заменяет прежнюю карточку, а
{"source": …, "key": "backup:nas", "status": "resolved"} без текста отмечает её
«починилось» и новой карточки не создаёт. Ключ — в ~/.config/<APP_ID>/ingest.json (права 600), выдаётся и
меняется в настройках. Без ключа запрос отклоняется.

Из сети (с других машин) приём включается отдельно — настройка ingest_bind
("0.0.0.0:8766"): поднимается ОТДЕЛЬНЫЙ сервер, который умеет только этот
эндпоинт; остальной API остаётся только на 127.0.0.1.
"""

import hmac
import json
import secrets
import sqlite3
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import catcher
import events
import paths
import rules
from i18n import L


def load_token():
    try:
        with open(paths.INGEST_CFG, encoding="utf-8") as f:
            return str(json.load(f).get("token") or "")
    except (OSError, ValueError):
        return ""


def new_token():
    token = secrets.token_urlsafe(24)
    paths.ensure_dirs()
    paths.write_private(paths.INGEST_CFG, json.dumps({"token": token}))
    return token


def authorized(header):
    token = load_token()
    got = (header or "").removeprefix("Bearer ").strip()
    # байтами: строки с не-ASCII compare_digest не сравнивает (TypeError вместо 401)
    return bool(token) and hmac.compare_digest(got.encode(), token.encode())


def _s(payload, key, limit, required=False):
    v = payload.get(key, "")
    if not isinstance(v, str) or len(v) > limit or (required and not v.strip()):
        raise ValueError(L(f"Поле «{key}»: нужна строка до {limit} символов",
                           f"Field “{key}”: a string up to {limit} characters is required"))
    return v.strip()


def accept_api(db_path, payload):
    """Приём события (см. докстринг): карточка → {"id"}, status=resolved → {"resolved": n}."""
    if not isinstance(payload, dict):
        raise ValueError(L("Ожидался JSON-объект", "Expected a JSON object"))
    key = _s(payload, "key", 200)
    status = payload.get("status", "problem")
    if status not in ("problem", "resolved"):
        raise ValueError(L("status — problem или resolved", "status must be problem or resolved"))
    if status == "resolved":
        if not key:
            raise ValueError(L("Для status: resolved нужен key", "status: resolved needs a key"))
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            return {"resolved": events.resolve(conn, "ingest:" + key)}
        finally:
            conn.close()
    return {"id": accept(db_path, payload, key=key)}


def accept(db_path, payload, key=""):
    """Записать событие как уведомление и выполнить действия правил. → id записи."""
    if not isinstance(payload, dict):
        raise ValueError(L("Ожидался JSON-объект", "Expected a JSON object"))
    source, text = _s(payload, "source", 60, True), _s(payload, "text", 4000, True)
    details = _s(payload, "details", 20000)
    chat = _s(payload, "chat", 200) or source
    sender = _s(payload, "sender", 200) or chat
    urgency = payload.get("urgency", 1)
    if urgency not in (0, 1, 2):
        raise ValueError(L("urgency — 0, 1 или 2", "urgency must be 0, 1 or 2"))
    ts = time.time()
    rec = {"app": source, "chat": chat, "sender": sender, "is_bot": catcher.guess_is_bot(sender),
           "message": text, "notification_id": 0, "urgency": urgency, "has_media": 0,
           "event_ts": ts, "event_iso": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
           "raw_summary": chat, "raw_body": text, "site": "", "avatar": None,
           "event_key": ("ingest:" + key) if key else None, "details": details[-events.DETAILS_MAX:] or None}
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        if key:                      # одна проблема — одна карточка: прежнюю с тем же ключом прочитать
            conn.execute("UPDATE messages SET is_read = 1, read_at = ? WHERE event_key = ? AND is_read = 0 "
                         "AND pinned = 0", (catcher.msk_time(), rec["event_key"]))
        rec["id"] = catcher.insert(conn, rec)
        rules.apply_on_insert(conn, rec)
        return rec["id"]
    finally:
        conn.close()


def serve_network(db_path, bind):
    """Отдельный сервер для приёма из сети: только POST /api/ingest с ключом."""
    host, port = bind.rsplit(":", 1)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _reply(self, code, data):
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != "/api/ingest":
                return self._reply(404, {"error": "not found"})
            if not authorized(self.headers.get("Authorization")):
                return self._reply(401, {"error": "bad token"})
            try:
                size = min(int(self.headers.get("Content-Length") or 0), 65536)
                self._reply(200, accept_api(db_path, json.loads(self.rfile.read(size) or b"{}")))
            except (ValueError, TypeError) as e:
                self._reply(400, {"error": str(e)})
            except sqlite3.Error as e:          # база занята — пусть отправитель повторит
                self._reply(503, {"error": str(e)})

    httpd = ThreadingHTTPServer((host.strip("[]"), int(port)), H)
    threading.Thread(target=httpd.serve_forever, name="ingest-net", daemon=True).start()
    return httpd
