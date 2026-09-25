#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
messhub для macOS (Apple Silicon, macOS 14 и новее; бета) — одним процессом, как на Windows
(так собирается messhub.app): сбор уведомлений (maccatcher), страница и API (serve) и окно доски
(winwidget — то же окно pywebview, на Mac это WKWebView).

    messhub.app                                   запустить (Finder, Launchpad, Dock)
    …/messhub.app/Contents/MacOS/messhub --no-widget      только сбор и страница http://127.0.0.1:8765
    …/messhub.app/Contents/MacOS/messhub --settings       сразу открыть и окно настроек
    … --selftest [--out файл.json]                        проверить сборку без окна и выйти (CI)
    … --capture-test ТЕКСТ [--out файл.json]              дождаться тестового уведомления (CI)

Программа без платной подписи Apple (Developer ID): при первом запуске macOS спросит разрешения
(«Конфиденциальность и безопасность» → «Всё равно открыть»), а для чтения уведомлений нужен
«Полный доступ к диску» — если его нет, программа сама откроет нужный раздел настроек.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _streams():
    """Всё, что печатаем, — в журнал программы (настройки → «Логи»); у программы из Finder консоли нет."""
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


def _dialog(text):
    """Окно с сообщением (osascript) — не ждём, пока его закроют."""
    script = 'display dialog {} with title "messhub" buttons {{"OK"}} default button 1 with icon note'.format(
        json.dumps(text))
    try:
        subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        print(text, flush=True)


def _report(out, path):
    text = json.dumps(out, ensure_ascii=False, indent=1)
    print(text, flush=True)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)


def selftest(port, out_path=None):
    """Без окна: сервер отвечает, страницы отдаются, pywebview на месте. → код выхода."""
    import urllib.request
    import maccatcher
    import version
    out = {"version": version.__version__, "frozen": bool(getattr(sys, "frozen", False)),
           "macos": maccatcher.macos_major()}
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
        import webview  # noqa: F401 — окно доски: pywebview (WKWebView)
        from importlib.metadata import version as pkg_version
        try:
            out["pywebview"] = pkg_version("pywebview")
        except Exception:  # noqa: BLE001 — в сборке PyInstaller метаданных пакета может не быть
            out["pywebview"] = "есть"
    except Exception as e:  # noqa: BLE001
        out["pywebview_error"] = repr(e)
    out["notify_db"] = maccatcher.db_path().replace(os.path.expanduser("~"), "~")
    out["access"] = maccatcher.access_status()
    ok = "error" not in out and out["api"].get("id") == "messhub" and out["widget_bytes"] > 1000 \
        and "pywebview_error" not in out
    out["ok"] = ok
    _report(out, out_path)
    return 0 if ok else 1


def capture_test(db, marker, out_path=None, timeout=40):
    """Дождаться, пока тестовое уведомление с текстом marker окажется в базе. → код выхода."""
    import sqlite3
    import maccatcher
    t = time.time()
    while time.time() - t < timeout:
        try:
            c = sqlite3.connect(db)
            row = c.execute("SELECT app, chat, message, site FROM messages WHERE message LIKE ? OR chat LIKE ?",
                            (f"%{marker}%", f"%{marker}%")).fetchone()
            c.close()
            if row:
                _report({"captured": row, "status": maccatcher.status}, out_path)
                return 0
        except sqlite3.Error:
            pass
        time.sleep(1)
    _report({"captured": None, "status": maccatcher.status, "access": maccatcher.access_status()}, out_path)
    return 2


def main():
    _streams()
    import paths
    import version
    ap = argparse.ArgumentParser(description="messhub для macOS")
    ap.add_argument("--db", default=paths.DB_PATH)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-widget", action="store_true", help="без окна доски")
    ap.add_argument("--settings", action="store_true", help="сразу открыть окно настроек")
    ap.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--capture-test", metavar="ТЕКСТ", help=argparse.SUPPRESS)
    ap.add_argument("--out", help=argparse.SUPPRESS)
    ap.add_argument("--wait-port", action="store_true", help=argparse.SUPPRESS)   # перезапуск из настроек
    ap.add_argument("--version", action="version", version=version.version_line())
    a, _unknown = ap.parse_known_args()          # Finder иногда добавляет свои (-psn_…)
    host = "127.0.0.1"

    if a.wait_port:                       # прежний процесс ещё отпускает порт
        for _ in range(60):
            if not _port_busy(host, a.port):
                break
            time.sleep(0.25)
    if not (a.selftest or a.capture_test) and _port_busy(host, a.port):
        if _already_running(a.port):
            return 0                      # уже работает — окно одно (Finder второй раз и не запустит)
        _dialog(f"Порт {a.port} занят другой программой — messhub не запустился.")
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
    import maccatcher
    import mail
    import quiet
    import reminders
    import resources
    import scripts
    import serve
    print(f"{version.version_line()} — сбор → {a.db}", flush=True)
    serve.prepare(a.db)
    serve.start_background(a.db)
    mail.start(a.db)
    if not a.selftest:
        containers.start(a.db)          # тематические колонки: пока включены в настройках
        for mod in (resources, logwatch, calendar_src, scripts, quiet, reminders):
            mod.start(a.db)
        collect.start_network_ingest(a.db)
    httpd = ThreadingHTTPServer((host, a.port), serve.make_handler(a.db))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    if a.selftest:
        return selftest(a.port, a.out)

    access = maccatcher.access_status()
    print(f"Уведомления macOS: {maccatcher.db_path()} — доступ: {access}", flush=True)
    if access == "denied" and not a.capture_test:
        maccatcher.open_access_settings()
        _dialog("Чтобы собирать уведомления, messhub нужен «Полный доступ к диску»: macOS хранит "
                "уведомления в защищённой базе, messhub её только читает.\n\n"
                "Системные настройки → Конфиденциальность и безопасность → Полный доступ к диску → "
                "включи messhub (или «+» и выбери его в Программах), затем перезапусти messhub.")
    stop = maccatcher.start(a.db, on_insert=collect.on_insert, skip=collect.make_skip(a.db))
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
