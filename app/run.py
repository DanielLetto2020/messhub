#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
messhub run — выполнить команду и положить итог в колонку «Команды»:

    messhub run -- make build                 # из пакета .deb/.rpm
    python3 app/run.py -- pytest -x           # из папки с исходниками
    messhub-run.exe -- npm run build          # Windows (лежит рядом с messhub.exe)

Команда работает как обычно: вывод идёт в терминал, код выхода сохраняется (можно
ставить в скрипты). На Linux/macOS команда видит настоящий терминал (цвета, прогресс,
ввод пароля), остальное — через обычные каналы. По окончании на 127.0.0.1 уходит
итог: команда, папка, код выхода, сколько шла и последние строки вывода (их сервер
покажет только при ошибке). Удачный запуск той же команды в той же папке гасит
прошлую карточку с ошибкой. Сервер не запущен или колонка выключена — команда всё
равно выполнится, будет только подсказка.

MESSHUB_PORT — порт сервера (по умолчанию 8765). Зависимостей нет.
"""

import collections
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

TAIL = 50


class Tail:
    """Последние строки вывода (байты → текст по концу строки)."""

    def __init__(self, n=TAIL):
        self.lines = collections.deque(maxlen=n)
        self.part = b""

    def feed(self, data):
        self.part += data
        *done, self.part = self.part.replace(b"\r\n", b"\n").split(b"\n")
        for ln in done:
            self._add(ln)

    def _add(self, ln):
        text = ln.decode("utf-8", "replace")
        text = text.rsplit("\r", 1)[-1]                     # прогресс-бары перерисовывают строку через \r
        text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07", "", text)[:300]
        if text.strip():
            self.lines.append(text)

    def text(self):
        if self.part:
            self._add(self.part)
            self.part = b""
        return "\n".join(self.lines)


def run_pty(argv, tail):
    """Через псевдотерминал (как script): у команды настоящий терминал, мы видим вывод."""
    import pty

    def read(fd):
        data = os.read(fd, 65536)
        tail.feed(data)
        return data
    try:
        import fcntl
        import termios
        size = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
    except (OSError, ImportError):
        size = None

    def read_first(fd):
        nonlocal size
        if size:                                           # размер окна — как у нашего терминала
            try:
                import fcntl
                import termios
                fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
            except OSError:
                pass
            size = None
        return read(fd)
    status = pty.spawn(argv, read_first)
    return os.waitstatus_to_exitcode(status) if hasattr(os, "waitstatus_to_exitcode") else (status >> 8)


def run_pipe(argv, tail):
    """Обычные каналы (Windows, вывод не в терминал): строки идут на экран и в хвост."""
    try:
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except OSError as e:
        print(f"messhub run: {e}", file=sys.stderr)
        return 127
    out = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else None
    try:
        for chunk in iter(lambda: p.stdout.read1(65536) if hasattr(p.stdout, "read1") else p.stdout.read(4096), b""):
            tail.feed(chunk)
            if out:
                out.write(chunk)
                out.flush()
    except KeyboardInterrupt:
        pass
    finally:
        p.stdout.close()
    return p.wait()


def report(cmd, code, seconds, tail_text, port):
    body = json.dumps({"kind": "command", "cmd": cmd, "code": code, "seconds": round(seconds, 1),
                       "cwd": os.getcwd(), "tail": tail_text}).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/event", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            res = json.load(r)
        if res.get("skipped"):
            print(f"messhub: {res.get('reason')}", file=sys.stderr)
    except (OSError, ValueError, urllib.error.URLError) as e:
        print(f"messhub: итог не записан — сервер на 127.0.0.1:{port} не отвечает ({e})", file=sys.stderr)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip().split("\n\n")[1] if __doc__ else "messhub run -- команда")
        return 0 if argv else 2
    port = int(os.environ.get("MESSHUB_PORT") or 8765)
    cmd = subprocess.list2cmdline(argv) if os.name == "nt" else " ".join(
        a if a and all(c.isalnum() or c in "-_./=:,+@%" for c in a) else "'" + a.replace("'", "'\\''") + "'"
        for a in argv)
    tail = Tail()
    t0 = time.time()
    if not shutil.which(argv[0]):
        # до запуска: иначе в режиме терминала ошибку поймал бы дочерний процесс
        print(f"messhub run: команда не найдена: {argv[0]}", file=sys.stderr)
        report(cmd, 127, 0, "", port)
        return 127
    try:
        if os.name != "nt" and sys.stdin.isatty() and sys.stdout.isatty():
            code = run_pty(argv, tail)
        else:
            code = run_pipe(argv, tail)
    except FileNotFoundError:
        print(f"messhub run: команда не найдена: {argv[0]}", file=sys.stderr)
        code = 127
    except KeyboardInterrupt:
        code = 130
    report(cmd, code, time.time() - t0, tail.text(), port)
    return code


if __name__ == "__main__":
    sys.exit(main())
