#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сбор уведомлений на Windows 10 (1809+) и 11 — то же, что catcher.py на Linux.

Источник — официальный API Windows «доступ к уведомлениям» (Windows.UI.Notifications.Management,
UserNotificationListener): с разрешения человека программа читает уведомления, которые Windows
показывает в центре уведомлений. В данные самих приложений не заглядываем.

Как устроено:
  • при первом запуске Windows спрашивает «Разрешить messhub доступ к уведомлениям?»
    (request_access — из главного потока). Отказались — «Параметры → Конфиденциальность →
    Уведомления»; самодиагностика подскажет;
  • раз в секунду берём список уведомлений (GetNotificationsAsync) и записываем новые. Событие
    NotificationChanged программам без MSIX-пакета недоступно — поэтому опрос;
  • «новые» — те, что появились позже отметки last (файл win-listener.json в папке данных):
    после перезапуска подтянутся и те, что пришли, пока messhub был выключен, но ещё лежат в
    центре уведомлений (Windows хранит их до 3 дней);
  • уведомление → catcher.record(приложение, заголовок, остальные строки) → тот же конвейер,
    что на Linux (catcher.make_handler: Telegram без ботов, дедуп, правила).

Первый текст всплывашки — заголовок (у мессенджеров это чат), остальные — тело: «Имя: текст»
в групповых чатах разбирается так же, как на Linux. У браузеров строка с сайтом тоже в теле.

Нужны пакеты winrt-* (requirements-windows.txt); без них модуль импортируется, но status()
скажет «unavailable» — так работают тесты на Linux (логика Poller проверяется без Windows).
"""

import asyncio
import json
import os
import threading
import time

import catcher
import paths

POLL = 1.0
STATE_FILE = os.path.join(paths.DATA_DIR, "win-listener.json")
APPS_FILE = os.path.join(paths.DATA_DIR, "win-apps.json")      # приложение → AUMID (для «перейти»)
EPOCH_1601 = 116444736000000000                                   # 1601-01-01 в сотнях нс до 1970-01-01

status = {"running": False, "access": "unknown", "last_poll": 0.0, "seen": 0, "error": ""}


# ── WinRT: имена в пакетах winrt (pywinrt 2+) и старом winsdk немного отличаются ───────

def _winrt():
    """→ (UserNotificationListener, AccessStatus, NotificationKinds, KnownNotificationBindings) или None."""
    try:
        from winrt.windows.ui.notifications.management import (UserNotificationListener,
                                                                UserNotificationListenerAccessStatus)
        from winrt.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
    except ImportError:
        try:
            from winsdk.windows.ui.notifications.management import (UserNotificationListener,
                                                                     UserNotificationListenerAccessStatus)
            from winsdk.windows.ui.notifications import NotificationKinds, KnownNotificationBindings
        except ImportError:
            return None
    return UserNotificationListener, UserNotificationListenerAccessStatus, NotificationKinds, KnownNotificationBindings


def _static(cls, name):
    """Статическое свойство WinRT: cls.current (winrt) или cls.get_current() (winsdk)."""
    v = getattr(cls, name, None)
    if v is not None and not callable(v):
        return v
    getter = getattr(cls, "get_" + name, None)
    return getter() if getter else v


def _enum(e, name):
    return getattr(e, name.upper(), None) or getattr(e, name.capitalize(), None) or getattr(e, name)


def listener():
    w = _winrt()
    return (_static(w[0], "current"), w) if w else (None, None)


def _access_name(value, w):
    for n in ("allowed", "denied", "unspecified"):
        if value == _enum(w[1], n):
            return n
    return str(value)


def access_status():
    """allowed | denied | unspecified | unavailable (нет winrt или Windows старше 1809)."""
    try:
        lst, w = listener()
        if not lst:
            return "unavailable"
        return _access_name(lst.get_access_status(), w)
    except Exception as e:  # noqa: BLE001 — на старой Windows API нет вовсе
        status["error"] = str(e)
        return "unavailable"


def request_access():
    """Спросить разрешение (окно Windows). Звать из главного потока до запуска окна виджета."""
    lst, w = listener()
    if not lst:
        return "unavailable"
    try:
        return _access_name(asyncio.run(lst.request_access_async()), w)
    except Exception as e:  # noqa: BLE001
        status["error"] = str(e)
        return access_status()


# ── разбор одного уведомления ─────────────────────────────────────────────────

def _ts(t):
    """creation_time: datetime (winrt) или DateTime со universal_time (winsdk) → unix-время."""
    if t is None:
        return time.time()
    if hasattr(t, "timestamp"):
        return t.timestamp()
    ut = getattr(t, "universal_time", None)
    return (ut - EPOCH_1601) / 1e7 if ut else time.time()


def item_of(un, w):
    """UserNotification → (id, время, приложение, AUMID, [тексты]) или None."""
    try:
        info = un.app_info
        app = info.display_info.display_name or info.app_user_model_id or "Windows"
        aumid = getattr(info, "app_user_model_id", "") or ""
    except Exception:  # noqa: BLE001 — у системных уведомлений AppInfo бывает пустым
        app, aumid = "Windows", ""
    texts = []
    try:
        binding = un.notification.visual.get_binding(_static(w[3], "toast_generic"))
        if binding is not None:
            texts = [t.text for t in binding.get_text_elements() if t.text]
    except Exception:  # noqa: BLE001
        pass
    return (int(un.id), _ts(getattr(un, "creation_time", None)), app, aumid, texts) if texts else None


def to_record(item):
    nid, ts, app, aumid, texts = item
    summary, body = texts[0], "\n".join(texts[1:])
    if not body:                         # одна строка — это и есть текст, заголовка нет
        summary, body = app, texts[0]
    return catcher.record(app, summary, body, event_ts=ts, notification_id=nid)


# ── что уже записано: отметка времени + id за этот запуск ────────────────────────

class Poller:
    """Отбор новых уведомлений из очередного списка. Без WinRT — чтобы проверять тестами."""

    def __init__(self, handle, state_file=STATE_FILE, apps_file=APPS_FILE, now=None):
        self.handle, self.state_file, self.apps_file = handle, state_file, apps_file
        self.seen = set()
        self.apps = _load(apps_file, {})
        st = _load(state_file, None)
        # первый запуск: старое из центра уведомлений не тащим — только то, что придёт дальше
        self.last = float(st["last"]) if st and "last" in st else (now or time.time())
        self.last_ids = set(st.get("ids", [])) if st else set()     # записанные ровно в момент last
        if not st:
            self._save()

    def _is_new(self, i):
        return i and i[0] not in self.seen and (i[1] > self.last or (i[1] == self.last and i[0] not in self.last_ids))

    def feed(self, items):
        new = sorted((i for i in items if self._is_new(i)), key=lambda i: (i[1], i[0]))
        for item in new:
            self.seen.add(item[0])
            if item[3] and self.apps.get(item[2]) != item[3]:
                self.apps[item[2]] = item[3]
                _dump(self.apps_file, self.apps)
            try:
                self.handle(to_record(item))
            except Exception as e:  # noqa: BLE001 — одно кривое уведомление не роняет сбор
                print(f"Уведомление Windows не записано: {e!r}", flush=True)
        if new:
            top = new[-1][1]
            self.last_ids = ({i[0] for i in new if i[1] == top} |
                             (self.last_ids if top == self.last else set()))
            self.last = max(self.last, top)
            self._save()
        status["seen"] = len(self.seen)
        return len(new)

    def _save(self):
        _dump(self.state_file, {"last": self.last, "ids": sorted(self.last_ids)})


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _dump(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass


def aumid_for(app):
    """AUMID приложения по его имени (для «перейти в приложение»)."""
    return _load(APPS_FILE, {}).get(app, "")


# ── цикл сбора ─────────────────────────────────────────────────────────────────

def run(db_path, verbose=False, on_insert=None, skip=None, stop=None):
    """Опрашивать центр уведомлений до stop.set(). Зовётся в отдельном потоке."""
    conn = catcher.init_db(db_path)
    poller = Poller(catcher.make_handler(conn, verbose, on_insert, skip))
    lst, w = listener()
    status["running"] = True
    status["access"] = access_status()
    if verbose:
        print(f"Слушаю уведомления Windows → {db_path} (доступ: {status['access']})", flush=True)

    async def loop():
        kinds = _enum(w[2], "toast")
        while not (stop and stop.is_set()):
            try:
                if status["access"] != "allowed":
                    status["access"] = access_status()
                if status["access"] == "allowed":
                    notes = await lst.get_notifications_async(kinds)
                    poller.feed([item_of(n, w) for n in notes])
                status["last_poll"] = time.time()
                status["error"] = ""
            except Exception as e:  # noqa: BLE001 — сбой одного опроса не останавливает сбор
                status["error"] = str(e)
            await asyncio.sleep(POLL if status["access"] == "allowed" else 5)
    try:
        if lst:
            asyncio.run(loop())
        else:
            status["access"] = "unavailable"
            while not (stop and stop.is_set()):
                time.sleep(5)
    finally:
        status["running"] = False
        conn.close()


def start(db_path, on_insert=None, skip=None, verbose=False):
    """Сбор в фоновом потоке. → Event, которым его останавливают."""
    stop = threading.Event()
    threading.Thread(target=run, args=(db_path, verbose, on_insert, skip, stop),
                     name="wincatcher", daemon=True).start()
    return stop
