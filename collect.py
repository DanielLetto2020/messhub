#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Команда 2 — СБОР + ПРОСМОТР В ОДНОМ.

Читает ВСЕ desktop-уведомления, сохраняет их в SQLite и одновременно
отдаёт живую веб-страницу. То есть один процесс = и читатель, и веб-сервер.

    python3 collect.py                    # собирать всё, http://127.0.0.1:8765
    python3 collect.py --port 9000 --db messages.db
    python3 collect.py --quiet            # не печатать пойманное в консоль

Как устроено: HTTP-сервер крутится в фоновом (daemon) потоке, а чтение
уведомлений — в главном потоке (он же ловит Ctrl+C и корректно всё гасит).
Обе части работают с одним файлом БД: catcher пишет (WAL), сервер читает.
"""

import argparse
import sqlite3
import threading
import time
from http.server import ThreadingHTTPServer

import catcher
import ingest
import mail
import rules
import serve
import version

_mail_mode = {"t": 0.0, "imap": False}


def make_skip(db_path):
    """Когда почта берётся из ящиков (IMAP), уведомления почтовых программ и почтовых
    сайтов не записываем — иначе каждое письмо было бы дважды. Режим перечитываем раз в 20 с."""
    def skip(rec):
        if time.time() - _mail_mode["t"] > 20:
            conn = sqlite3.connect(db_path, timeout=5)
            try:
                _mail_mode["imap"] = mail.channel(conn) == "imap"
            finally:
                conn.close()
            _mail_mode["t"] = time.time()
        return _mail_mode["imap"] and rules.source_of(rec["app"], rec.get("site", ""))["key"] == "mail"
    return skip


def on_insert(conn, rec):
    """После записи уведомления — действия правил (сразу прочитано, закрепить,
    звук, переслать в Telegram)."""
    done = rules.apply_on_insert(conn, rec)
    if done:
        print(f"Правила для #{rec['id']}: {', '.join(done)}", flush=True)


def main():
    ap = argparse.ArgumentParser(
        description="Сбор всех уведомлений в БД + живая веб-страница (одна команда)")
    ap.add_argument("--db", default=catcher.DEFAULT_DB)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--quiet", action="store_true",
                    help="не печатать пойманное в консоль")
    ap.add_argument("--version", action="version", version=version.version_line())
    args = ap.parse_args()

    # перенести файлы старых версий в XDG-папки и досоздать схему — до старта сервера
    serve.prepare(args.db)
    # фон: авто-прочтение, срок хранения, копии, недельный отчёт, векторы умного поиска
    serve.start_background(args.db)
    # почта из ящиков (IMAP) — работает, только если выбран такой канал почты
    mail.start(args.db)
    # приём событий из сети — отдельный сервер только для /api/ingest, если включён
    conn = sqlite3.connect(args.db)
    bind = rules.get_prefs(conn)["ingest_bind"]
    conn.close()
    if bind:
        try:
            ingest.serve_network(args.db, bind)
            print(f"Приём событий из сети: http://{bind}/api/ingest", flush=True)
        except OSError as e:
            print(f"Приём событий из сети не поднялся ({bind}): {e}", flush=True)

    # веб-сервер — в фоновом потоке
    httpd = ThreadingHTTPServer((args.host, args.port), serve.make_handler(args.db))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    url = f"http://{args.host}:{args.port}"
    print(f"{version.version_line()} — сбор → {args.db}")
    print(f"Веб-страница: {url}   (Ctrl+C — остановить всё)")

    # чтение уведомлений — в главном потоке (ставит обработчики сигналов, блокирует)
    try:
        catcher.run(args.db, verbose=not args.quiet, from_file=None,
                    on_insert=on_insert, skip=make_skip(args.db))
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
