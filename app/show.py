#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Быстрый просмотр перехваченных сообщений из локальной БД.

    python3 show.py                # последние 20
    python3 show.py -n 50          # последние 50
    python3 show.py --app express  # только eXpress
    python3 show.py --chat "Проект"  # чат по подстроке
    python3 show.py --stats        # сводка по чатам
"""

import argparse
import os
import sqlite3

import paths

DEFAULT_DB = paths.DB_PATH


def main():
    ap = argparse.ArgumentParser(description="Просмотр перехваченных сообщений")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("-n", type=int, default=20, help="сколько последних показать")
    ap.add_argument("--app", help="фильтр по приложению (подстрока)")
    ap.add_argument("--chat", help="фильтр по чату (подстрока)")
    ap.add_argument("--stats", action="store_true", help="сводка по чатам вместо списка")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        print(f"БД не найдена: {args.db}. Сначала запустите catcher.py.")
        return

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    if args.stats:
        rows = conn.execute(
            """SELECT app, chat, COUNT(*) n, MAX(event_iso) last
               FROM messages GROUP BY app, chat ORDER BY n DESC LIMIT 40"""
        ).fetchall()
        print(f'{"сообщ.":>6}  {"последнее":<19}  приложение / чат')
        for r in rows:
            print(f'{r["n"]:>6}  {r["last"] or "":<19}  {r["app"]} / {r["chat"]}')
        return

    where, params = [], []
    if args.app:
        where.append("app LIKE ?"); params.append(f"%{args.app}%")
    if args.chat:
        where.append("chat LIKE ?"); params.append(f"%{args.chat}%")
    sql = "SELECT * FROM messages"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(args.n)

    rows = conn.execute(sql, params).fetchall()
    for r in reversed(rows):
        bot = " [бот]" if r["is_bot"] else ""
        media = " 📎" if r["has_media"] else ""
        text = (r["message"] or "").replace("\n", " ⏎ ")
        print(f'#{r["id"]} [{r["event_iso"]}] {r["app"]} · {r["chat"]}')
        print(f'    {r["sender"]}{bot}{media}: {text}')


if __name__ == "__main__":
    main()
