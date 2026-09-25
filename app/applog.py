#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Журнал работы программы — то, что видно в настройках → «Логи».

Каждый процесс пишет свой файл в <данные>/logs/ (сбор и сервер — collect.log, окно доски на
Linux — widget.log), строка = JSON {"t", "lvl", "src", "msg"}. Файл больше MAX_BYTES
переименовывается в .1 (старый .1 — в .2, ещё старше удаляется), так что журнал не растёт
бесконечно. Всё остаётся на этом компьютере.

setup("collect") в начале процесса: всё, что программа печатает (print), попадает и в
журнал, и туда, куда шло раньше (journald у сервиса, консоль); необработанные ошибки
(в том числе в потоках) пишутся одной записью с трассировкой. Тексты сообщений из
уведомлений в журнал не попадают: сбор работает с --quiet.

Уровень строки угадывается по словам («ошибка», «не удалось», error, failed …) —
новые места могут звать error()/warn()/info() явно.
"""

import json
import os
import re
import sys
import threading
import time
import traceback

import paths

MAX_BYTES = 512 * 1024
KEEP = 2                        # сколько старых файлов (.1, .2) хранить
LEVELS = ("info", "warn", "error")
_lock = threading.Lock()
_proc = {"src": "collect", "file": None}
_ERR = re.compile(r"ошибк|не удалось|не поднял|не запуст|упал|traceback|exception|error|failed|fatal", re.I)
_WARN = re.compile(r"предупрежд|недоступ|нет доступа|не отвеч|таймаут|warning|timeout|denied|refused", re.I)


def file_for(src):
    return os.path.join(paths.LOG_DIR, f"{src}.log")


def guess_level(text):
    if _ERR.search(text):
        return "error"
    if _WARN.search(text):
        return "warn"
    return "info"


def _rotate(path):
    try:
        if os.path.getsize(path) < MAX_BYTES:
            return
    except OSError:
        return
    for i in range(KEEP, 0, -1):
        older = f"{path}.{i}"
        newer = path if i == 1 else f"{path}.{i - 1}"
        try:
            if i == KEEP and os.path.exists(older):
                os.remove(older)
            if os.path.exists(newer):
                os.replace(newer, older)
        except OSError:
            pass


def write(msg, lvl=None, src=None):
    """Одна запись в журнал своего процесса (src — чья: collect, widget, page)."""
    msg = str(msg).rstrip()
    if not msg:
        return
    rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "lvl": lvl if lvl in LEVELS else guess_level(msg),
           "src": src or _proc["src"], "msg": msg[:8000]}
    path = _proc["file"] or file_for(_proc["src"])
    with _lock:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            _rotate(path)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass                     # журнал не должен ронять программу


def info(msg):
    write(msg, "info")


def warn(msg):
    write(msg, "warn")


def error(msg):
    write(msg, "error")


class _Tee:
    """Поток вывода, который заодно пишет законченные строки в журнал."""

    def __init__(self, orig, stream, bump=True):
        self.orig, self.stream = orig, stream
        self.bump = bump and stream == "stderr"      # обычная строка в stderr — предупреждение
        # недописанная строка — своя у каждого потока: print() пишет текст и "\n" двумя вызовами,
        # и с общим буфером строки разных потоков слипались в одну запись
        self._local = threading.local()

    def write(self, s):
        if self.orig is not None:
            try:
                self.orig.write(s)
            except (OSError, ValueError, UnicodeError):
                pass
        buf = getattr(self._local, "buf", "") + s
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if line.strip():
                lvl = guess_level(line)
                if self.bump and lvl == "info":
                    lvl = "warn"
                write(line, lvl)
        self._local.buf = buf
        return len(s)

    def flush(self):
        if self.orig is not None:
            try:
                self.orig.flush()
            except (OSError, ValueError):
                pass

    def isatty(self):
        return bool(self.orig is not None and getattr(self.orig, "isatty", lambda: False)())

    def reconfigure(self, **kw):
        if self.orig is not None and hasattr(self.orig, "reconfigure"):
            self.orig.reconfigure(**kw)

    @property
    def encoding(self):
        return getattr(self.orig, "encoding", "utf-8") or "utf-8"


def _hook(kind):
    def log_exc(exc_type, exc, tb, where=""):
        text = "".join(traceback.format_exception(exc_type, exc, tb)).rstrip()
        write((f"Необработанная ошибка{where}:\n" if where else "Необработанная ошибка:\n") + text, "error")
    if kind == "sys":
        prev = sys.excepthook

        def h(t, e, tb):
            if not issubclass(t, KeyboardInterrupt):
                log_exc(t, e, tb)
            prev(t, e, tb)
        return h
    prev_t = threading.excepthook

    def th(args):
        if args.exc_type is not SystemExit:
            log_exc(args.exc_type, args.exc_value, args.exc_traceback,
                    f" в потоке {args.thread.name if args.thread else '?'}")
        prev_t(args)
    return th


def setup(src="collect", stderr_is_info=False):
    """Писать вывод процесса в журнал (см. докстринг модуля). Повторный вызов ничего не ломает.
    stderr_is_info — процесс пишет свои обычные сообщения в stderr (окно доски)."""
    _proc["src"], _proc["file"] = src, file_for(src)
    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout, "stdout")
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr, "stderr", bump=not stderr_is_info)
    sys.excepthook = _hook("sys")
    threading.excepthook = _hook("thread")


# ── чтение для раздела «Логи» ───────────────────────────────────────────────

def _files():
    try:
        names = os.listdir(paths.LOG_DIR)
    except OSError:
        return []
    return sorted(os.path.join(paths.LOG_DIR, n) for n in names if re.match(r"^[\w-]+\.log(\.\d+)?$", n))


def entries():
    """Все записи всех журналов, по времени (старые первыми)."""
    out = []
    for p in _files():
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(r, dict) and r.get("msg"):
                        out.append({"t": str(r.get("t", "")), "lvl": r.get("lvl") if r.get("lvl") in LEVELS else "info",
                                    "src": str(r.get("src", "")), "msg": str(r["msg"])})
        except OSError:
            continue
    out.sort(key=lambda r: r["t"])          # сортировка устойчивая — внутри секунды порядок файла
    return out


def query(level="all", q="", src="", limit=1000):
    """Записи для страницы: новые первыми. level — all | warn (и ошибки) | error."""
    rows = entries()
    counts = {k: 0 for k in LEVELS}
    day_ago = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - 86400))
    errors_day = 0
    for r in rows:
        counts[r["lvl"]] += 1
        if r["lvl"] == "error" and r["t"] >= day_ago:
            errors_day += 1
    want = {"all": LEVELS, "warn": ("warn", "error"), "error": ("error",)}.get(level, LEVELS)
    ql = q.casefold()
    sel = [r for r in rows if r["lvl"] in want and (not src or r["src"] == src)
           and (not ql or ql in r["msg"].casefold())]
    sel.reverse()
    size = sum(os.path.getsize(p) for p in _files() if os.path.exists(p))
    return {"rows": sel[:limit], "total": len(sel), "counts": counts, "errors_day": errors_day,
            "sources": sorted({r["src"] for r in rows}), "bytes": size,
            "max_bytes": MAX_BYTES * (KEEP + 1) * max(1, len({os.path.basename(p).split(".")[0] for p in _files()})),
            "dir": paths.LOG_DIR}


def errors_last_day():
    return query(limit=0)["errors_day"]


def clear():
    """Очистить журналы (все процессы, со старыми файлами). → сколько файлов тронули."""
    n = 0
    with _lock:
        for p in _files():
            try:
                if re.search(r"\.\d+$", p):
                    os.remove(p)
                else:
                    open(p, "w", encoding="utf-8").close()
                n += 1
            except OSError:
                pass
    return n


def mask(text):
    """Домашняя папка и имя пользователя → «~» и «<user>»: выгрузку можно приложить к issue."""
    home = os.path.expanduser("~")
    user = os.path.basename(home.rstrip("/\\"))
    if home and home not in ("/", "~"):
        text = text.replace(home, "~")
    if len(user) >= 3:
        text = re.sub(rf"(?<![\w]){re.escape(user)}(?![\w])", "<user>", text)
    return text


def as_text(rows):
    return "\n".join(f"{r['t']}  {r['lvl'].upper():5}  {r['src']:8}  {r['msg']}" for r in rows)


_client = {"t": 0.0, "n": 0}


def client_error(payload):
    """Ошибка JavaScript со страницы виджета/настроек (не больше 30 в минуту)."""
    now = time.time()
    if now - _client["t"] > 60:
        _client.update(t=now, n=0)
    _client["n"] += 1
    if _client["n"] > 30:
        return False
    page = str(payload.get("page") or "")[:40]
    msg = str(payload.get("msg") or "")[:1000]
    where = str(payload.get("where") or "")[:200]
    if msg:
        write(f"Ошибка на странице {page}: {msg}" + (f" ({where})" if where else ""), "error", "page")
    return True
