#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Свои источники без правки кода: скрипты в папке <настройки>/sources.d
(~/.config/messhub/sources.d, на Windows — %APPDATA%\\messhub\\sources.d).

Программа запускает каждый скрипт по расписанию (по умолчанию раз в 5 минут; своё — строкой
`# messhub: interval=60` в начале файла или в настройках) и превращает то, что он напечатал,
в карточки. Каждая строка вывода — JSON-объект, как у приёма событий:

    {"source": "Бэкапы", "chat": "nas", "text": "Бэкап не прошёл", "key": "backup:nas", "urgency": 2}
    {"source": "Бэкапы", "key": "backup:nas", "status": "resolved"}
    {"source": "Бэкапы", "text": "…", "details": "длинный лог — в виджете свёрнут"}

Linux и macOS: исполняемые файлы (chmod +x) и *.py (через python3). Windows: *.bat, *.cmd,
*.ps1 (PowerShell) и *.py (через py/python, если установлен). Скрипт работает не дольше минуты;
ошибки и вывод в stderr — в журнал программы. Переменная MESSHUB_SCRIPT_STATE — папка, где
скрипт может хранить своё состояние между запусками.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import events
import ingest
import paths
import rules
from i18n import L

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0
DIR = os.path.join(paths.CONFIG_DIR, "sources.d")
STATE_DIR = os.path.join(paths.DATA_DIR, "sources-state")
DEFAULT_INTERVAL = 300
TIMEOUT = 60
_RE_INTERVAL = re.compile(r"messhub:\s*interval\s*=\s*(\d+)", re.I)

status = {}                     # имя → {last, ok, cards, error, next}
_lock = threading.Lock()

EXAMPLE = '''#!/bin/sh
# Пример своего источника для messhub. Каждая строка вывода — JSON-карточка.
# messhub: interval=300
used=$(df --output=pcent / | tail -1 | tr -dc '0-9')
if [ "$used" -ge 95 ]; then
  echo "{\\"source\\": \\"Мой сервер\\", \\"chat\\": \\"диск /\\", \\"text\\": \\"занято $used%\\", \\"key\\": \\"my:disk\\", \\"urgency\\": 2}"
else
  echo "{\\"source\\": \\"Мой сервер\\", \\"key\\": \\"my:disk\\", \\"status\\": \\"resolved\\"}"
fi
'''


def discover():
    """Скрипты в папке: [(имя, путь, интервал из файла или None)]."""
    if not os.path.isdir(DIR):
        return []
    out = []
    for name in sorted(os.listdir(DIR)):
        path = os.path.join(DIR, name)
        if name.startswith(".") or name.endswith(("~", ".bak", ".swp", ".json", ".md", ".txt")) \
                or not os.path.isfile(path) or not re.match(r"^[\w.\-]{1,80}$", name):
            continue
        if command(path) is None:
            continue
        interval = None
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                m = _RE_INTERVAL.search(f.read(2048))
                interval = int(m.group(1)) if m else None
        except OSError:
            pass
        out.append((name, path, interval))
    return out


def command(path):
    """Как запустить файл, или None — не скрипт."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".py":
        py = sys.executable if not getattr(sys, "frozen", False) else (
            shutil.which("py") or shutil.which("python3") or shutil.which("python"))
        return [py, path] if py else None
    if WINDOWS:
        if ext in (".bat", ".cmd"):
            return ["cmd", "/c", path]
        if ext == ".ps1":
            return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path]
        return None
    return [path] if os.access(path, os.X_OK) else None


def run_one(db_path, name, path):
    """Запустить скрипт и записать его карточки. → (карточек, ошибка)."""
    os.makedirs(os.path.join(STATE_DIR, name), exist_ok=True)
    env = dict(os.environ, MESSHUB_SCRIPT_STATE=os.path.join(STATE_DIR, name))
    try:
        r = subprocess.run(command(path), capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=TIMEOUT, env=env, cwd=DIR, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return 0, L(f"не уложился в {TIMEOUT} с", f"did not finish in {TIMEOUT}s")
    except OSError as e:
        return 0, str(e)
    if r.stderr.strip():
        print(f"Свои источники: {name}: {r.stderr.strip().splitlines()[-1][:300]}", flush=True)
    cards, bad = 0, 0
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ingest.accept_api(db_path, json.loads(line))
            cards += 1
        except (ValueError, TypeError) as e:
            bad += 1
            last_err = str(e)
    err = "" if r.returncode == 0 else L(f"код выхода {r.returncode}", f"exit code {r.returncode}")
    if bad:
        err = (err + "; " if err else "") + L(f"строк с ошибкой: {bad}", f"bad lines: {bad}") + f" ({last_err[:120]})"
    return cards, err


def start(db_path):
    """Раз в 10 с: какие скрипты пора запустить (каждый — в своём потоке, без наложения)."""
    running = set()

    def worker(name, path):
        try:
            n, err = run_one(db_path, name, path)
        except Exception as e:  # noqa: BLE001
            n, err = 0, repr(e)
        with _lock:
            status.setdefault(name, {}).update(last=time.strftime("%Y-%m-%d %H:%M:%S"), ok=not err,
                                               cards=n, error=err[:300])
            running.discard(name)

    def loop():
        last = {}
        while True:
            try:
                conn = events.connect(db_path)
                try:
                    cfg = rules.get_prefs(conn)["scripts"]
                finally:
                    conn.close()
                if cfg["enabled"]:
                    now = time.time()
                    for name, path, file_interval in discover():
                        item = cfg["items"].get(name, {})
                        if not item.get("enabled", True):
                            continue
                        interval = item.get("interval") or file_interval or DEFAULT_INTERVAL
                        with _lock:
                            status.setdefault(name, {})["next"] = time.strftime(
                                "%H:%M:%S", time.localtime(last.get(name, now) + interval))
                        if name in running or now - last.get(name, 0) < interval:
                            continue
                        last[name] = now
                        with _lock:
                            running.add(name)
                        threading.Thread(target=worker, args=(db_path, name, path), name=f"script-{name}",
                                         daemon=True).start()
            except Exception as e:  # noqa: BLE001
                print(f"Свои источники: ошибка: {e!r}", flush=True)
            time.sleep(10)
    threading.Thread(target=loop, name="scripts", daemon=True).start()


def info(db_path):
    """Для настроек: папка, скрипты, их расписание и итог последнего запуска."""
    conn = events.connect(db_path)
    try:
        cfg = rules.get_prefs(conn)["scripts"]
    finally:
        conn.close()
    items = []
    for name, _path, file_interval in discover():
        it = cfg["items"].get(name, {})
        items.append({"name": name, "enabled": it.get("enabled", True),
                      "interval": it.get("interval") or file_interval or DEFAULT_INTERVAL,
                      "file_interval": file_interval, **status.get(name, {})})
    return {"enabled": cfg["enabled"], "dir": DIR, "exists": os.path.isdir(DIR), "items": items,
            "platform": "windows" if WINDOWS else "linux"}


def make_example():
    """Создать папку и пример (если папки ещё нет). → путь к примеру."""
    os.makedirs(DIR, exist_ok=True)
    if WINDOWS:
        path = os.path.join(DIR, "example.bat.off")
        with open(path, "w", encoding="utf-8") as f:
            f.write('@echo off\nrem Пример своего источника для messhub (переименуй в example.bat, чтобы включить)\n'
                    'echo {"source": "Мой компьютер", "chat": "пример", "text": "Скрипт работает"}\n')
        return path
    path = os.path.join(DIR, "example.sh.off")
    with open(path, "w", encoding="utf-8") as f:
        f.write(EXAMPLE)
    return path


def run_now(db_path, name):
    for n, path, _ in discover():
        if n == name:
            cards, err = run_one(db_path, n, path)
            with _lock:
                status.setdefault(n, {}).update(last=time.strftime("%Y-%m-%d %H:%M:%S"), ok=not err,
                                                cards=cards, error=err[:300])
            return {"cards": cards, "error": err}
    raise ValueError(L("Нет такого скрипта", "No such script"))
