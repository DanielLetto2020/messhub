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
import os
import sqlite3
import threading
import time
from http.server import ThreadingHTTPServer

import applog
import calendar_src
import catcher
import containers
import ingest
import logwatch
import mail
import quiet
import reminders
import resources
import rules
import scripts
import serve
import services
import version

_mode = {"t": 0.0, "imap": False, "commands": False}


def make_skip(db_path):
    """Что не записывать:
      - когда почта берётся из ящиков (IMAP), — уведомления почтовых программ и сайтов,
        иначе каждое письмо было бы дважды;
      - когда колонка «Команды» выключена, — уведомления хука терминала (messhub-commands).
    Режимы перечитываем раз в 20 с."""
    def skip(rec):
        if time.time() - _mode["t"] > 20:
            try:
                conn = sqlite3.connect(db_path, timeout=5)
                try:
                    _mode["imap"] = mail.channel(conn) == "imap"
                    _mode["commands"] = rules.themed(rules.get_prefs(conn))["commands"]["enabled"]
                finally:
                    conn.close()
            except sqlite3.Error:
                pass                     # база занята — пока живём с прежним режимом
            _mode["t"] = time.time()
        key = rules.source_of(rec["app"], rec.get("site", ""))["key"]
        return (_mode["imap"] and key == "mail") or (key == "commands" and not _mode["commands"])
    return skip


def start_network_ingest(db_path):
    """Приём событий из сети — отдельный сервер только для /api/ingest, если он включён
    (настройка ingest_bind). Зовут collect.py и messhub_win.py."""
    conn = sqlite3.connect(db_path)
    try:
        bind = rules.get_prefs(conn)["ingest_bind"]
    finally:
        conn.close()
    if bind:
        try:
            ingest.serve_network(db_path, bind)
            print(f"Приём событий из сети: http://{bind}/api/ingest", flush=True)
        except OSError as e:
            print(f"Приём событий из сети не поднялся ({bind}): {e}", flush=True)


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

    applog.setup("collect")          # всё, что печатаем, — ещё и в журнал (настройки → «Логи»)
    # перенести файлы старых версий в XDG-папки и досоздать схему — до старта сервера
    serve.prepare(args.db)
    # фон: авто-прочтение, срок хранения, копии, недельный отчёт, векторы умного поиска
    serve.start_background(args.db)
    # почта из ящиков (IMAP) — работает, только если выбран такой канал почты
    mail.start(args.db)
    # тематические колонки: контейнеры (docker/podman) и упавшие службы — пока включены в настройках
    containers.start(args.db)
    services.start(args.db)
    resources.start(args.db)
    logwatch.start(args.db)
    calendar_src.start(args.db)
    scripts.start(args.db)          # свои источники: скрипты в <настройки>/sources.d
    quiet.start(args.db)            # тихие часы: переходы, «Не беспокоить» GNOME, сводка
    reminders.start(args.db)        # напоминания по сообщениям
    start_network_ingest(args.db)

    # веб-сервер — в фоновом потоке
    httpd = ThreadingHTTPServer((args.host, args.port), serve.make_handler(args.db))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    url = f"http://{args.host}:{args.port}"
    print(f"{version.version_line()} — сбор → {args.db}")
    print(f"Веб-страница: {url}   (Ctrl+C — остановить всё)")

    # чтение уведомлений — в главном потоке (ставит обработчики сигналов, блокирует);
    # на Windows вместо D-Bus — центр уведомлений (wincatcher), а окно доски даёт messhub_win.py
    try:
        if os.name == "nt":
            import wincatcher
            if wincatcher.access_status() == "unspecified":
                wincatcher.request_access()
            wincatcher.run(args.db, verbose=not args.quiet, on_insert=on_insert, skip=make_skip(args.db))
        else:
            catcher.run(args.db, verbose=not args.quiet, from_file=None,
                        on_insert=on_insert, skip=make_skip(args.db))
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()


if __name__ == "__main__":
    main()
