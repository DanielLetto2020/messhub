#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
messhub для Windows 10/11 — одним процессом (так собирается messhub.exe):
сбор уведомлений (wincatcher), страница и API (serve) и окно доски (winwidget).

    messhub.exe                 запустить; второй запуск ничего не ломает — окно уже открыто
    messhub.exe --no-widget     только сбор и страница http://127.0.0.1:8765
    messhub.exe --settings      сразу открыть и окно настроек
    messhub.exe --selftest [--out файл.json]           проверить сборку без окна и выйти (так её проверяет CI)
    messhub.exe --capture-test ТЕКСТ [--out файл.json] дождаться тестового уведомления Windows (CI)
У оконной сборки нет консоли — результат проверок пишется в --out (и в журнал logs\\collect.log).

Переносная версия: файл portable.txt рядом с messhub.exe — данные в папке data рядом с ним
(а не в %LOCALAPPDATA%\\\\messhub), так что всё помещается на флешку.
"""

import argparse
import json
import os
import socket
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
EXE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else HERE


def _portable():
    if os.path.exists(os.path.join(EXE_DIR, "portable.txt")) and not os.environ.get("MESSHUB_HOME"):
        os.environ["MESSHUB_HOME"] = os.path.join(EXE_DIR, "data")


def _streams():
    """Всё, что печатаем, — в журнал программы (настройки → «Логи», файл logs/collect.log в папке
    данных). В оконной сборке консоли нет (sys.stdout is None) — пишем только в журнал; в консоли —
    ещё и на экран, в UTF-8 с заменой непечатного, чтобы русский текст не ронял программу."""
    import applog
    for s in (sys.stdout, sys.stderr):
        if s is not None:
            try:
                s.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, ValueError):
                pass
    applog.setup("collect")


def _port_busy(host, port):
    with socket.socket() as s:
        return s.connect_ex((host, port)) == 0


def _already_running(port):
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/version", timeout=2) as r:
            return json.load(r).get("id") == "messhub"
    except (OSError, ValueError):
        return False


def _message(text):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, "messhub", 0x40)
    except Exception:  # noqa: BLE001 — не Windows (запуск для проверки)
        print(text)


def _report(out, path):
    text = json.dumps(out, ensure_ascii=False, indent=1)
    print(text, flush=True)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def selftest(port, out_path=None):
    """Без окна: сервер отвечает, страницы отдаются, WinRT и pywebview на месте. → код выхода."""
    import urllib.request
    import version
    import wincatcher
    out = {"version": version.__version__, "frozen": bool(getattr(sys, "frozen", False))}
    base = f"http://127.0.0.1:{port}"
    try:
        out["api"] = json.load(urllib.request.urlopen(base + "/api/version", timeout=5))
        out["widget_bytes"] = len(urllib.request.urlopen(base + "/widget?host=pywebview", timeout=5).read())
        out["settings_bytes"] = len(urllib.request.urlopen(base + "/settings", timeout=5).read())
        out["diag"] = {c["id"]: c["state"] for c in
                       json.load(urllib.request.urlopen(base + "/api/diag", timeout=15))["checks"]}
    except Exception as e:  # noqa: BLE001
        out["error"] = repr(e)
    try:
        import webview  # noqa: F401
        from importlib.metadata import version as pkg_version
        try:
            out["pywebview"] = pkg_version("pywebview")
        except Exception:  # noqa: BLE001 — в сборке PyInstaller метаданных пакета может не быть
            out["pywebview"] = "есть"
    except Exception as e:  # noqa: BLE001
        out["pywebview_error"] = repr(e)
    out["winrt"] = wincatcher._winrt() is not None
    out["access"] = wincatcher.access_status()
    ok = "error" not in out and out["api"].get("id") == "messhub" and out["widget_bytes"] > 1000
    out["ok"] = ok
    _report(out, out_path)
    return 0 if ok else 1


def capture_test(db, marker, out_path=None, timeout=40):
    """Дождаться, пока тестовое уведомление с текстом marker окажется в базе. → код выхода."""
    import sqlite3
    t = time.time()
    while time.time() - t < timeout:
        try:
            c = sqlite3.connect(db)
            row = c.execute("SELECT app, chat, message FROM messages WHERE message LIKE ? OR chat LIKE ?",
                            (f"%{marker}%", f"%{marker}%")).fetchone()
            c.close()
            if row:
                import wincatcher
                _report({"captured": row, "status": wincatcher.status}, out_path)
                return 0
        except sqlite3.Error:
            pass
        time.sleep(1)
    import wincatcher
    _report({"captured": None, "status": wincatcher.status, "access": wincatcher.access_status()}, out_path)
    return 2


def main():
    _portable()
    _streams()
    import paths
    import version
    ap = argparse.ArgumentParser(description="messhub для Windows")
    ap.add_argument("--db", default=paths.DB_PATH)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-widget", action="store_true", help="без окна доски")
    ap.add_argument("--settings", action="store_true", help="сразу открыть окно настроек")
    ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--capture-test", metavar="ТЕКСТ", help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    ap.add_argument("--wait-port", action="store_true", help=argparse.SUPPRESS)   # перезапуск из настроек
    ap.add_argument("--version", action="version", version=version.version_line())
    a = ap.parse_args()
    host = "127.0.0.1"

    if a.wait_port:                       # прежний процесс ещё отпускает порт
        for _ in range(60):
            if not _port_busy(host, a.port):
                break
            time.sleep(0.25)
    if not (a.selftest or a.capture_test) and _port_busy(host, a.port):
        if _already_running(a.port):
            _message("messhub уже работает — доска открыта.\nmesshub is already running.")
            return 0
        _message(f"Порт {a.port} занят другой программой — messhub не запустился.")
        return 1
    if a.selftest or a.capture_test:      # проверки — на свободном порту, чтобы не мешать настоящему
        with socket.socket() as s:
            s.bind((host, 0))
            a.port = s.getsockname()[1]

    from http.server import ThreadingHTTPServer
    import calendar_src
    import collect
    import containers
    import logwatch
    import mail
    import quiet
    import reminders
    import resources
    import scripts
    import serve
    import services
    import wincatcher
    print(f"{version.version_line()} — сбор → {a.db}", flush=True)
    serve.prepare(a.db)
    serve.start_background(a.db)
    mail.start(a.db)
    if not a.selftest:
        containers.start(a.db)          # тематические колонки: пока включены в настройках
        services.start(a.db)
        for mod in (resources, logwatch, calendar_src, scripts, quiet, reminders):
            mod.start(a.db)
        collect.start_network_ingest(a.db)      # приём событий из сети, если включён (как на Linux)
    httpd = ThreadingHTTPServer((host, a.port), serve.make_handler(a.db))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if a.selftest:
        return selftest(a.port, a.out)

    if wincatcher.access_status() == "unspecified":       # первый запуск — Windows спросит разрешение
        wincatcher.request_access()
    stop = wincatcher.start(a.db, on_insert=collect.on_insert, skip=collect.make_skip(a.db))
    try:
        if a.capture_test:
            return capture_test(a.db, a.capture_test, a.out)
        if a.no_widget:
            while True:
                time.sleep(3600)
        import winwidget
        winwidget.run(f"http://{host}:{a.port}", open_settings=a.settings)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
