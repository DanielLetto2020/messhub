#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
messhub — читатель собственных desktop-уведомлений на своей машине.

Идея: слушаем СИСТЕМНЫЙ поток desktop-уведомлений (D-Bus,
org.freedesktop.Notifications). Всё, что приложение (eXpress и др.) выводит
как всплывающее уведомление, мы разбираем и складываем в локальную SQLite —
для дальнейшей обработки локальной LLM (саммари + напоминания о важном).

Почему именно этот канал:
  - во внутренние данные приложений не заглядываем — только штатные уведомления ОС;
  - читаем ровно то, что ОС и так показывает пользователю на его же экране;
  - источник общий для всех приложений, не только eXpress.

Зависимостей нет — только стандартная библиотека + внешняя утилита
`dbus-monitor` (пакет dbus / dbus-tools, обычно уже стоит).

Запуск:
    python3 catcher.py                 # ловит все приложения, пишет в базу (см. paths.py)
    python3 catcher.py --verbose       # печатать пойманное в консоль
    python3 catcher.py --from-file LOG # разобрать сохранённый вывод dbus-monitor (тест парсера)

Формат вывода dbus-monitor для одного уведомления (аргументы метода Notify):
    method call ... interface=org.freedesktop.Notifications; member=Notify
       string "<app_name>"          # 0
       uint32 <replaces_id>         # 1
       string "<app_icon>"          # 2
       string "<summary>"           # 3  ← чат / имя собеседника
       string "<body>"              # 4  ← "Отправитель: текст" или просто текст
       array [ ...actions... ]      # 5
       array [ ...hints... ]        # 6  ← desktop-entry, urgency, image-data
       int32 <expire_timeout>       # 7
"""

import argparse
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import avatars
import paths

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = paths.DB_PATH            # ~/.local/share/<APP_ID>/messages.db (см. paths.py)
SCHEMA_PATH = os.path.join(HERE, "schema.sql")

# well-known имя сервиса уведомлений — по нему отсекаем «эхо»-пересылки,
# оставляя только исходный вызов приложения.
NOTIFY_DEST = "org.freedesktop.Notifications"

# Время записи в БД (received_at) и отметки «прочитано» (read_at) — явно по Москве,
# чтобы окно «старше 24 ч» не зависело от часового пояса машины.
# Москва живёт в UTC+3 без перехода на летнее время (с 2014 г.).
MSK = timezone(timedelta(hours=3), "MSK")


def msk_time(hours_ago=0):
    """Московское время (минус hours_ago часов) строкой как в received_at."""
    return (datetime.now(MSK) - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


# ── Telegram: сохраняем только личные/групповые ЧАТЫ, отсекаем каналы и ботов.
#    Относится ТОЛЬКО к Telegram; eXpress и прочие источники — как есть.
#    Боты определяются по "bot" в имени. Каналы в desktop-уведомлении структурно
#    не отличаются от личных чатов (маркера «канал» нет), поэтому отсекаются по
#    списку названий — при необходимости заполнить руками:
TELEGRAM_MARK = "telegram"
TELEGRAM_CHANNEL_NAMES = ()   # напр.: ("Хабр", "РБК", "Точное название канала")

# ── границы D-Bus сообщения в потоке dbus-monitor ──────────────────────────
_MSG_START = re.compile(r"^(method call|signal|error) ")
_RE_TIME = re.compile(r"\btime=([\d.]+)")
_RE_SENDER = re.compile(r"\bsender=(\S+)")
_RE_DEST = re.compile(r"\bdestination=(\S+)")

# top-level значение = ровно 3 ведущих пробела + тип D-Bus + значение
_RE_TOP = re.compile(
    r"^   (string|uint32|int32|uint64|int64|double|boolean|byte|"
    r"object path|signature|variant|array|struct)\b ?(.*)$"
)

# hints вытаскиваем прямым поиском по сырому телу (надёжнее, чем по индексу)
_RE_DESKTOP_ENTRY = re.compile(r'"desktop-entry".*?variant\s+string "([^"]*)"', re.S)
_RE_URGENCY = re.compile(r'"urgency".*?variant\s+byte (\d+)', re.S)


def parse_message_block(header, body_lines):
    """Разобрать один блок dbus-monitor в dict или вернуть None, если это не то."""
    if "member=Notify" not in header:
        return None
    # Одно уведомление dbus-monitor нередко показывает дважды: исходный вызов
    # приложения и пересылку демона. destination при этом бывает то well-known
    # именем, то unique (:1.46) — по нему фильтровать нельзя. Поэтому парсим все,
    # а задвоение снимаем дедупом по (app, summary, body) в окне времени (см. run).
    m_time = _RE_TIME.search(header)
    event_ts = float(m_time.group(1)) if m_time else time.time()
    m_sender = _RE_SENDER.search(header)
    bus_sender = m_sender.group(1) if m_sender else ""

    body_raw_all = "\n".join(body_lines)

    # ── извлекаем top-level строки и первый uint32 ──
    strings = []
    replaces_id = None
    i = 0
    n = len(body_lines)
    while i < n:
        line = body_lines[i]
        mt = _RE_TOP.match(line)
        if not mt:
            i += 1
            continue
        typ, rest = mt.group(1), mt.group(2)

        if typ == "string":
            # многострочная строка: копим, пока строка не закончится на "
            val = rest
            if val.startswith('"'):
                val = val[1:]
            if val.endswith('"') and len(rest) >= 2:
                strings.append(val[:-1])
                i += 1
                continue
            # продолжение на следующих сырых строках
            acc = [val]
            i += 1
            while i < n:
                cont = body_lines[i]
                if cont.endswith('"'):
                    acc.append(cont[:-1])
                    i += 1
                    break
                acc.append(cont)
                i += 1
            strings.append("\n".join(acc))
            continue

        if typ == "uint32" and replaces_id is None:
            try:
                replaces_id = int(rest.strip())
            except ValueError:
                pass
            i += 1
            continue

        if typ == "array":
            # пропускаем весь массив до закрывающей "   ]" (top-level)
            i += 1
            while i < n and body_lines[i] != "   ]":
                i += 1
            i += 1
            continue

        i += 1

    if len(strings) < 4:
        return None

    app_name = strings[0]
    summary = strings[2]
    body = strings[3]

    # desktop-entry надёжнее, чем app_name (у Electron бывает generic)
    m_de = _RE_DESKTOP_ENTRY.search(body_raw_all)
    desktop_entry = m_de.group(1) if m_de else ""
    app = desktop_entry or app_name or "unknown"

    m_ur = _RE_URGENCY.search(body_raw_all)
    urgency = int(m_ur.group(1)) if m_ur else None

    has_media = 1 if ("image-data" in body_raw_all
                      or "image-path" in body_raw_all
                      or "image_path" in body_raw_all) else 0

    chat, sender, message, site = parse_fields(app, summary, body)

    return {
        "app": app,
        "chat": chat,
        "sender": sender,
        "is_bot": guess_is_bot(sender),
        "message": message,
        "notification_id": replaces_id,
        "urgency": urgency,
        "has_media": has_media,
        "event_ts": event_ts,
        "event_iso": datetime.fromtimestamp(event_ts).isoformat(timespec="seconds"),
        "raw_summary": summary,
        "raw_body": body,
        "site": site,
        "avatar": avatars.extract(body_lines),
        "bus_sender": bus_sender,
    }


# ── разбор по типу приложения: браузер (сайт в теле), почта (От/Тема), остальное ──
BROWSER_MARKS = ("yandex", "chrome", "chromium", "firefox", "brave", "opera", "vivaldi", "edge")
MAIL_MARKS = ("thunderbird", "geary", "evolution")
CALENDAR_MARKS = ("alarm-notify", "reminder", "calendar")   # evolution-alarm-notify — календарь
_RE_DOMAIN = re.compile(r"^(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?::\d+)?/?$", re.I)
_RE_MAIL_FROM = re.compile(r"^(?:From|От|Отправитель)\s*:\s*(.+)$", re.I | re.M)
_RE_MAIL_SUBJ = re.compile(r"^(?:Subject|Тема)\s*:\s*(.+)$", re.I | re.M)


def app_kind(app):
    a = (app or "").lower()
    if any(m in a for m in CALENDAR_MARKS):
        return "calendar"
    if any(m in a for m in MAIL_MARKS):
        return "mail"
    if any(m in a for m in BROWSER_MARKS):
        return "browser"
    return "app"


def split_site(body):
    """Веб-уведомление браузера: сайт отдельной строкой — первой (Chromium/Яндекс:
    "web.max.ru\n\nтекст") или последней. → (сайт, тело без этой строки)."""
    lines = (body or "").split("\n")
    for idx in (0, len(lines) - 1):
        m = _RE_DOMAIN.match(lines[idx].strip())
        if m:
            return m.group(1).lower(), "\n".join(lines[:idx] + lines[idx + 1:]).strip("\n")
    return "", body


def split_mail(summary, body):
    """Почта: в теле «От: …» / «Тема: …» (Evolution и др.) — отправитель и тема;
    иначе summary — отправитель, тело — тема/текст. Чат = отправитель (как личка)."""
    body = body or ""
    mf, ms = _RE_MAIL_FROM.search(body), _RE_MAIL_SUBJ.search(body)
    if mf:
        sender = mf.group(1).strip()
        return sender, sender, (ms.group(1).strip() if ms else body.strip())
    s = (summary or "").strip()
    return s, s, body.strip()


def parse_fields(app, summary, body):
    """(chat, sender, message, site) по типу приложения."""
    kind = app_kind(app)
    if kind == "browser":
        site, rest = split_site(body)
        return (*split_sender(summary, rest), site)
    if kind == "mail":
        return (*split_mail(summary, body), "")
    return (*split_sender(summary, body), "")


def split_sender(summary, body):
    """
    Групповой чат eXpress: summary = название группы, body = "Имя Фамилия: текст".
    Личный чат:            summary = имя собеседника,   body = текст без префикса.
    Возвращаем (chat, sender, message).
    """
    body = (body or "").rstrip("\n")
    chat = (summary or "").strip()
    # префикс "Имя: " — только в первой строке и разумной длины
    first_line = body.split("\n", 1)[0]
    m = re.match(r"^(.{1,60}?): (.*)$", first_line)
    if m and not m.group(1).endswith((" ", ",")):
        sender = m.group(1).strip()
        rest = m.group(2)
        tail = body.split("\n", 1)
        message = rest if len(tail) == 1 else rest + "\n" + tail[1]
        return chat, sender, message.strip()
    # префикса нет — это личка: отправитель = собеседник (= summary)
    return chat, chat, body.strip()


def guess_is_bot(sender):
    """Эвристика: боты eXpress часто содержат bot/бот в имени. Уточняется вручную."""
    s = (sender or "").lower()
    return 1 if ("bot" in s or "бот" in s) else 0


def telegram_should_skip(rec):
    """
    Только для Telegram: True, если уведомление НЕ из личного/группового чата,
    то есть от бота или из канала — такие не сохраняем.
    eXpress и другие источники этой проверкой не затрагиваются.
    """
    if TELEGRAM_MARK not in (rec.get("app") or "").lower():
        return False
    name = (rec.get("sender") or rec.get("chat") or "").lower()
    if "bot" in name:                       # бот
        return True
    chat = (rec.get("chat") or "").lower()  # канал — по ручному списку названий
    if any(c and c.lower() in chat for c in TELEGRAM_CHANNEL_NAMES):
        return True
    return False


NEW_COLUMNS = (("is_read", "INTEGER DEFAULT 0"), ("read_at", "TEXT"),
               ("pinned", "INTEGER DEFAULT 0"), ("snooze_until", "TEXT"), ("site", "TEXT"),
               ("avatar", "TEXT"))
RULES_NEWEST = ("text", "profile")    # колонки последней версии таблицы rules


def migrate(conn):
    """
    ДО schema.sql: досоздать колонки, появившиеся после первой версии схемы (на
    старой таблице индексы из schema.sql по новым колонкам упали бы), и отодвинуть
    старую таблицу правил, если в ней нет колонок последней версии (UNIQUE в SQLite
    не поменять без пересоздания) — schema.sql создаст новую, а migrate_after()
    перенесёт в неё правила. Свежую БД не трогаем.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
    if cols:
        for name, ddl in NEW_COLUMNS:
            if name not in cols:
                conn.execute(f"ALTER TABLE messages ADD COLUMN {name} {ddl}")
    rcols = {r[1] for r in conn.execute("PRAGMA table_info(rules)")}
    if rcols and not all(c in rcols for c in RULES_NEWEST):
        conn.execute("DROP TABLE IF EXISTS rules_old")
        conn.execute("ALTER TABLE rules RENAME TO rules_old")


def migrate_after(conn):
    """ПОСЛЕ schema.sql: перенести правила из старой таблицы и разобрать заново
    сайт/почту у записей, сохранённых до появления этого разбора (site IS NULL)."""
    for old in ("rules_v1", "rules_old"):          # rules_v1 — имя из версии 1.0.0
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (old,)).fetchone():
            new_cols = {r[1] for r in conn.execute("PRAGMA table_info(rules)")}
            common = [r[1] for r in conn.execute(f"PRAGMA table_info({old})") if r[1] in new_cols]
            cols = ", ".join(common)
            conn.execute(f"INSERT OR IGNORE INTO rules ({cols}) SELECT {cols} FROM {old}")
            conn.execute(f"DROP TABLE {old}")
    for id_, app, summ, body in conn.execute(
            "SELECT id, app, raw_summary, raw_body FROM messages WHERE site IS NULL").fetchall():
        chat, sender, message, site = parse_fields(app, summ, body)
        if site or app_kind(app) == "mail":
            conn.execute("UPDATE messages SET chat = ?, sender = ?, message = ?, site = ? "
                         "WHERE id = ?", (chat, sender, message, site, id_))
        else:
            conn.execute("UPDATE messages SET site = '' WHERE id = ?", (id_,))


def init_db(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    migrate(conn)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    migrate_after(conn)
    conn.commit()
    return conn


def insert(conn, rec):
    """Записать уведомление; вернуть id новой строки."""
    cur = conn.execute(
        """INSERT INTO messages
           (app, chat, sender, is_bot, message, notification_id, urgency,
            has_media, event_ts, event_iso, received_at, raw_summary, raw_body, site, avatar)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (rec["app"], rec["chat"], rec["sender"], rec["is_bot"], rec["message"],
         rec["notification_id"], rec["urgency"], rec["has_media"],
         rec["event_ts"], rec["event_iso"], msk_time(), rec["raw_summary"], rec["raw_body"],
         rec.get("site", ""), rec.get("avatar")),
    )
    conn.commit()
    return cur.lastrowid


def blocks_from_stream(lines):
    """Итератор: (header, body_lines) по границам D-Bus сообщений."""
    header = None
    body = []
    for raw in lines:
        line = raw.rstrip("\n")
        if _MSG_START.match(line):
            if header is not None:
                yield header, body
            header = line
            body = []
        elif header is not None:
            body.append(line)
    if header is not None:
        yield header, body


def run(db_path, verbose, from_file, on_insert=None, skip=None):
    """on_insert(conn, rec) — вызывается после записи (rec["id"] уже есть): так
    collect.py применяет действия правил (сразу прочитано, закрепить, звук, пересылка).
    skip(rec) → True — не записывать (так collect.py отбрасывает уведомления почтовых
    программ, когда почта берётся напрямую из ящиков по IMAP)."""
    conn = init_db(db_path)

    # дедуп «эхо» и мгновенных повторов: (app, summary, body) в окне 2 сек
    last_key = None
    last_t = 0.0

    def handle(rec):
        nonlocal last_key, last_t
        if skip and skip(rec):
            return
        if telegram_should_skip(rec):        # Telegram: только чаты, без ботов/каналов
            return
        key = (rec["app"], rec["raw_summary"], rec["raw_body"])
        now = rec["event_ts"]
        if key == last_key and (now - last_t) < 2.0:
            return
        last_key, last_t = key, now
        rec["id"] = insert(conn, rec)
        if on_insert:
            try:
                on_insert(conn, rec)
            except Exception as e:          # правило не должно ронять сбор
                print(f"Действия правил: ошибка: {e!r}", flush=True)
        if verbose:
            bot = " [бот]" if rec["is_bot"] else ""
            print(f'[{rec["event_iso"]}] {rec["app"]} | {rec["chat"]} | '
                  f'{rec["sender"]}{bot}: {rec["message"]!r}', flush=True)

    if from_file:
        with open(from_file, "r", encoding="utf-8", errors="replace") as f:
            for header, body in blocks_from_stream(f):
                rec = parse_message_block(header, body)
                if rec:
                    handle(rec)
        print(f"Готово. Записей в БД: "
              f"{conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]}")
        conn.close()
        return

    cmd = [
        "dbus-monitor", "--session",
        f"type='method_call',interface='{NOTIFY_DEST}',member='Notify'",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, bufsize=1)

    stopping = {"v": False}

    def stop(*_):
        stopping["v"] = True
        try:
            proc.terminate()
        except Exception:
            pass

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    if verbose:
        print(f"Слушаю уведомления → {db_path}. Ctrl+C для остановки.", flush=True)

    try:
        for header, body in blocks_from_stream(proc.stdout):
            if stopping["v"]:
                break
            rec = parse_message_block(header, body)
            if rec:
                handle(rec)
    finally:
        conn.close()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


def main():
    ap = argparse.ArgumentParser(description="Читатель desktop-уведомлений → SQLite")
    ap.add_argument("--db", default=DEFAULT_DB, help=f"путь к БД (по умолчанию {DEFAULT_DB})")
    ap.add_argument("--verbose", action="store_true", help="печатать пойманное в консоль")
    ap.add_argument("--version", action="version",
                    version=__import__("version").version_line())
    ap.add_argument("--from-file", metavar="LOG",
                    help="разобрать сохранённый вывод dbus-monitor вместо живого потока")
    args = ap.parse_args()
    run(args.db, args.verbose, args.from_file)


if __name__ == "__main__":
    main()
