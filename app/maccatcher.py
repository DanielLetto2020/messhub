#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сбор уведомлений на macOS (Apple Silicon, macOS 14 и новее) — то же, что catcher.py на Linux.

Источник — база Центра уведомлений: macOS сама записывает туда каждое уведомление, которое
показывает на экране (пока оно лежит в Центре уведомлений). В данные самих приложений не заглядываем.
  macOS 15 и новее: ~/Library/Group Containers/group.com.apple.usernoted/db2/db
  macOS 14:         $(getconf DARWIN_USER_DIR)/com.apple.notificationcenter/db2/db
База защищена: читать её можно только с «Полным доступом к диску» (Системные настройки →
Конфиденциальность и безопасность → Полный доступ к диску → messhub). Без него status["access"]
= "denied", а самодиагностика подскажет, что сделать.

Как устроено (только чтение): раз в 2 секунды смотрим, поменялись ли файлы базы (db, db-wal); если
да — копируем их во временную папку и читаем копию, файлы системы не открываем на запись вовсе.
Новые строки — те, у которых rec_id больше запомненного (mac-listener.json в папке данных). Первый
запуск только запоминает последнюю запись: старое из Центра уведомлений не тащим.

Схема (одинакова в macOS 14–27): app(app_id, identifier — bundle id приложения) и record(rec_id,
app_id, data — двоичный plist, delivered_date — секунды от 2001-01-01). В plist: req.titl (заголовок),
req.subt (подзаголовок), req.body (текст), app (bundle id, если уведомление послано от имени другого
приложения), date. Уведомление → catcher.record → тот же конвейер, что на Linux (catcher.make_handler:
Telegram без ботов, дедуп, правила).
"""

import json
import os
import platform
import plistlib
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import time
from datetime import datetime

import catcher
import paths

POLL = 2.0
EPOCH_2001 = 978307200                     # 2001-01-01 в секундах unix — начало отсчёта дат macOS
STATE_FILE = os.path.join(paths.DATA_DIR, "mac-listener.json")
BATCH = 500
FDA_PANE = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
_RE_DOMAIN = catcher._RE_DOMAIN               # сайт в подзаголовке у браузеров (и кириллический)

status = {"running": False, "access": "unknown", "last_poll": 0.0, "seen": 0, "error": "", "db": ""}


def macos_major():
    try:
        return int((platform.mac_ver()[0] or "0").split(".")[0])
    except ValueError:
        return 0


def db_path():
    """Где лежит база Центра уведомлений (переменная MESSHUB_MAC_NOTIFY_DB — для тестов)."""
    env = os.environ.get(f"{paths.ENV_PREFIX}_MAC_NOTIFY_DB")
    if env:
        return env
    new = os.path.expanduser("~/Library/Group Containers/group.com.apple.usernoted/db2/db")
    if macos_major() >= 15 or macos_major() == 0:
        return new
    try:
        d = subprocess.run(["getconf", "DARWIN_USER_DIR"], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        d = ""
    return os.path.join(d, "com.apple.notificationcenter", "db2", "db") if d else new


def access_status(path=None):
    """allowed | denied (нет «Полного доступа к диску») | missing (базы нет — нет и уведомлений)."""
    path = path or db_path()
    try:
        with open(path, "rb") as f:
            f.read(16)
        return "allowed"
    except FileNotFoundError:
        return "missing"
    except OSError:                        # EPERM «Operation not permitted» — защита TCC
        return "denied"


def open_access_settings():
    """Открыть в Системных настройках раздел «Полный доступ к диску»."""
    try:
        subprocess.Popen(["open", FDA_PANE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


# ── чтение базы ────────────────────────────────────────────────────────────────

def _signature(path):
    """Размер и время изменения файлов базы — по ним видно, что пора читать."""
    sig = []
    for suffix in ("", "-wal"):
        try:
            st = os.stat(path + suffix)
            sig.append((st.st_size, st.st_mtime_ns))
        except OSError:
            sig.append(None)
    return tuple(sig)


def snapshot(path, tmpdir):
    """Копия базы с журналом WAL во временной папке — чтобы не трогать файлы системы. Индекс журнала
    (-shm) не копируем: чужой, он мог бы спрятать свежие записи, а без него SQLite строит его заново
    по самому журналу и видит всё, что в нём записано."""
    dst = os.path.join(tmpdir, "db")
    for suffix in ("-wal", "-shm", ""):
        try:
            os.remove(dst + suffix)
        except OSError:
            pass
    for suffix in ("", "-wal"):
        if os.path.exists(path + suffix):
            shutil.copyfile(path + suffix, dst + suffix)
    return dst


def read_records(db, after, limit=BATCH):
    """Строки базы с rec_id > after → [(rec_id, bundle id, data, delivered_date)]."""
    conn = sqlite3.connect(db, timeout=5)
    try:
        return conn.execute("SELECT r.rec_id, a.identifier, r.data, r.delivered_date FROM record r "
                            "JOIN app a ON a.app_id = r.app_id WHERE r.rec_id > ? ORDER BY r.rec_id LIMIT ?",
                            (after, limit)).fetchall()
    finally:
        conn.close()


def max_rec_id(db):
    conn = sqlite3.connect(db, timeout=5)
    try:
        return conn.execute("SELECT COALESCE(MAX(rec_id), 0) FROM record").fetchone()[0]
    finally:
        conn.close()


def _text(v):
    return v.strip() if isinstance(v, str) else ""


def parse(rec_id, identifier, data, delivered):
    """Строка базы → (rec_id, bundle id, заголовок, подзаголовок, текст, время unix) или None."""
    try:
        root = plistlib.loads(bytes(data or b""))
    except Exception:  # noqa: BLE001 — битый или незнакомый plist: пропускаем одну строку
        return None
    if not isinstance(root, dict):
        return None
    req = root.get("req") if isinstance(root.get("req"), dict) else root
    title = _text(req.get("titl")) or _text(req.get("title"))
    sub = _text(req.get("subt")) or _text(req.get("subtitle"))
    body = _text(req.get("body"))
    if not (title or sub or body):
        return None                        # служебная запись без текста
    app = _text(root.get("app")) or identifier or "macOS"
    if isinstance(delivered, (int, float)) and delivered:
        ts = delivered + EPOCH_2001
    elif isinstance(root.get("date"), datetime):
        ts = root["date"].timestamp()
    elif isinstance(root.get("date"), (int, float)):
        ts = root["date"] + EPOCH_2001
    else:
        ts = time.time()
    return rec_id, app, title, sub, body, ts


def to_record(item):
    """Уведомление Mac → запись для catcher (заголовок — чат, подзаголовок — автор или сайт)."""
    rec_id, app, title, sub, body, ts = item
    summary, text = title or sub or app, body
    if title and sub:
        if _RE_DOMAIN.match(sub):                         # браузер: сайт — отдельной строкой, как на Linux
            text = sub + ("\n\n" + body if body else "")
        elif catcher.app_kind(app) == "mail":             # почта: подзаголовок — тема письма
            text = sub + ("\n" + body if body else "")
        else:                                             # мессенджер: подзаголовок — автор в группе
            text = f"{sub}: {body}" if body else sub
    return catcher.record(app, summary, text, event_ts=ts, notification_id=rec_id)


# ── что уже записано ─────────────────────────────────────────────────────────────

class Poller:
    """Отбор новых строк базы. Без macOS — чтобы проверять тестами на поддельной базе."""

    def __init__(self, handle, state_file=STATE_FILE):
        self.handle, self.state_file = handle, state_file
        st = _load(state_file)
        self.last = int(st["last"]) if st and isinstance(st.get("last"), int) else None
        self.seen = 0

    def step(self, db):
        """Прочитать новые строки копии базы db. → сколько записано."""
        top = max_rec_id(db)
        if self.last is None or top < self.last:
            # первый запуск — только запомнить; база пересоздана (номера меньше) — начать с её конца
            self.last = top
            self._save()
            return 0
        n = 0
        while True:
            rows = read_records(db, self.last)
            for rec_id, identifier, data, delivered in rows:
                self.last = rec_id
                item = parse(rec_id, identifier, data, delivered)
                if not item:
                    continue
                try:
                    if self.handle(to_record(item)):
                        n += 1
                except Exception as e:  # noqa: BLE001 — одно кривое уведомление не роняет сбор
                    print(f"Уведомление macOS не записано: {e!r}", flush=True)
            if rows:
                self._save()
            if len(rows) < BATCH:
                break
        self.seen += n
        status["seen"] = self.seen
        return n

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({"last": self.last}, f)
        except OSError:
            pass


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ── цикл сбора ─────────────────────────────────────────────────────────────────

def run(db_path_, verbose=False, on_insert=None, skip=None, stop=None, source=None):
    """Следить за базой Центра уведомлений до stop.set(). Зовётся в отдельном потоке."""
    conn = catcher.init_db(db_path_)
    poller = Poller(catcher.make_handler(conn, verbose, on_insert, skip))
    src = source or db_path()
    status.update(running=True, db=src, access=access_status(src))
    if verbose:
        print(f"Слушаю уведомления macOS → {db_path_} (доступ: {status['access']})", flush=True)
    sig = None
    try:
        with tempfile.TemporaryDirectory(prefix="messhub-nc-") as tmp:
            while not (stop and stop.is_set()):
                try:
                    status["access"] = access_status(src)
                    if status["access"] == "allowed":
                        cur = _signature(src)
                        if cur != sig:
                            poller.step(snapshot(src, tmp))
                            sig = cur
                    status["last_poll"] = time.time()
                    status["error"] = ""
                except (OSError, sqlite3.Error) as e:
                    status["error"] = str(e)[:300]
                    sig = None                           # в следующий раз — прочитать заново
                if stop:
                    stop.wait(POLL if status["access"] == "allowed" else 5)
                else:
                    time.sleep(POLL if status["access"] == "allowed" else 5)
    finally:
        status["running"] = False
        conn.close()


def start(db_path_, on_insert=None, skip=None, verbose=False):
    """Сбор в фоновом потоке. → Event, которым его останавливают."""
    stop = threading.Event()
    threading.Thread(target=run, args=(db_path_, verbose, on_insert, skip, stop),
                     name="maccatcher", daemon=True).start()
    return stop
