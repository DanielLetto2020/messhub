#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тематическая колонка «Журналы»: строки логов по своему шаблону.

Наблюдение — файл (как tail -F: ждём новые строки, переживаем ротацию) или служба journald
(`journalctl [--user] -u <служба> -f -n 0`, только Linux) плюс регулярное выражение. Совпадения
собираются в одну карточку на наблюдение за час: «47 совпадений за час, последнее: …», в
логе под карточкой — последние совпавшие строки. Карточка обновляется не чаще раза в минуту,
чтобы шумный лог не завалил доску. Ключ logwatch:<id>. Только чтение.
"""

import collections
import os
import re
import shutil
import subprocess
import threading
import time

import events
import rules
from i18n import L

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0
WINDOW_S = 3600              # совпадения копятся в одну карточку за час
EVERY_S = 60                 # карточку обновляем не чаще раза в минуту
KEEP = 30                    # строк в логе карточки

status = {}                  # id наблюдения → {running, error, matches, last}
_threads = {}                # id → (конфиг, Event остановки, запущенные journalctl)


class Bucket:
    """Совпадения одного наблюдения за текущий час и когда карточку обновляли последний раз."""

    def __init__(self):
        self.lines = collections.deque(maxlen=KEEP)
        self.count, self.start, self.flushed, self.pending = 0, 0.0, 0.0, False

    def add(self, line, now):
        if now - self.start > WINDOW_S:
            self.lines.clear()
            self.count, self.start = 0, now
        self.count += 1
        self.lines.append(line[:400])
        self.pending = True


def card(db_path, w, b):
    conn = events.connect(db_path)
    try:
        events._lang(conn)
        last = b.lines[-1] if b.lines else ""
        text = (L(f"{b.count} совпадений за час, последнее:", f"{b.count} matches in an hour, the latest:")
                if b.count > 1 else L("совпадение:", "match:")) + "\n" + last
        where = w["target"] if w["kind"] == "file" else (w["target"] + (" (user)" if w["scope"] == "user" else ""))
        events.emit(conn, "logwatch", w["name"], text, sender=where, details="\n".join(b.lines),
                    key=f"logwatch:{w['id']}", urgency=1)
    finally:
        conn.close()


def _follow_file(path, stop):
    """Новые строки файла (как tail -F): с конца, после ротации — с начала нового файла."""
    f, ino, pos = None, None, 0
    while not stop.is_set():
        try:
            st = os.stat(path)
            if f is None or st.st_ino != ino or st.st_size < pos:
                if f:
                    f.close()
                f = open(path, "r", encoding="utf-8", errors="replace")
                if ino is None:
                    f.seek(0, os.SEEK_END)          # первое открытие — только новое
                ino = st.st_ino
                pos = f.tell()
            while True:
                line = f.readline()
                if not line:
                    break
                pos = f.tell()
                if line.endswith("\n"):
                    yield line.rstrip("\n")
        except OSError as e:
            yield OSError(str(e))
            if f:
                f.close()
            f = None                             # ino помним: появится новый файл — читаем с начала
            stop.wait(10)
        stop.wait(2)
    if f:
        f.close()


def _follow_unit(w, stop, procs):
    args = ["journalctl"] + (["--user"] if w["scope"] == "user" else []) + \
        ["-u", w["target"], "-f", "-n", "0", "-o", "cat", "--no-pager"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                         errors="replace", bufsize=1, creationflags=NO_WINDOW)
    procs.append(p)
    for line in p.stdout:
        if stop.is_set():
            break
        yield line.rstrip("\n")
    err = (p.stderr.read() or "").strip()
    p.wait()                                     # без этого завершённый journalctl висел бы зомби
    procs.remove(p)
    if err and not stop.is_set():
        yield OSError(err.splitlines()[-1][:300])


def watch(db_path, w, stop, procs):
    st = status.setdefault(w["id"], {})
    st.update(running=True, error="", matches=0, last="")
    rx = re.compile(w["pattern"], re.I if w["icase"] else 0)
    b = Bucket()

    def flusher():
        while not stop.wait(5):
            if b.pending and time.time() - b.flushed >= EVERY_S:
                b.pending, b.flushed = False, time.time()
                try:
                    card(db_path, w, b)
                except Exception as e:  # noqa: BLE001 — база занята: попробуем в следующий раз
                    b.pending = True
                    st["error"] = str(e)[:300]
    threading.Thread(target=flusher, name=f"logwatch-{w['id']}-flush", daemon=True).start()
    while not stop.is_set():
        if w["kind"] == "unit" and (WINDOWS or not shutil.which("journalctl")):
            st.update(running=False, error=L("journald есть только на Linux", "journald is Linux-only"))
            return
        src = _follow_file(os.path.expanduser(w["target"]), stop) if w["kind"] == "file" else _follow_unit(w, stop, procs)
        for line in src:
            if isinstance(line, OSError):
                st.update(error=str(line))
                continue
            st["error"] = ""
            if rx.search(line):
                b.add(line, time.time())
                st["matches"] += 1
                st["last"] = time.strftime("%H:%M:%S")
                if b.count == 1:                 # первое совпадение за час — сразу, дальше не чаще раза в минуту
                    b.flushed = 0.0
        if not stop.is_set():
            stop.wait(15)                        # journalctl завершился — перезапустим
    for p in procs:
        try:
            p.terminate()
        except OSError:
            pass
    st["running"] = False


def start(db_path):
    """Раз в 10 с: запустить новые наблюдения, остановить удалённые или изменённые."""
    def loop():
        while True:
            try:
                conn = events.connect(db_path)
                try:
                    cfg = rules.themed(rules.get_prefs(conn))["logwatch"]
                finally:
                    conn.close()
                want = {w["id"]: w for w in cfg["watches"]} if cfg["enabled"] else {}
                for wid, (old, stop, procs) in list(_threads.items()):
                    if want.get(wid) != old:
                        stop.set()
                        for p in procs:           # journalctl ждёт новую строку — без этого жил бы до неё
                            try:
                                p.terminate()
                            except OSError:
                                pass
                        del _threads[wid]
                        status.pop(wid, None)
                for wid, w in want.items():
                    if wid not in _threads:
                        stop, procs = threading.Event(), []
                        _threads[wid] = (w, stop, procs)
                        threading.Thread(target=watch, args=(db_path, w, stop, procs), name=f"logwatch-{wid}",
                                         daemon=True).start()
                        print(f"Журналы: слежу за «{w['name']}»", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"Журналы: ошибка: {e!r}", flush=True)
            time.sleep(10)
    threading.Thread(target=loop, name="logwatch", daemon=True).start()


def preview(w, n=500):
    """Проверка шаблона в настройках: сколько из последних n строк совпало и какие (до 20)."""
    w = rules.clean_watch(w)
    rx = re.compile(w["pattern"], re.I if w["icase"] else 0)
    lines = []
    if w["kind"] == "file":
        path = os.path.expanduser(w["target"])
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 256 * 1024))
            lines = f.read().decode("utf-8", "replace").splitlines()[-n:]
    else:
        if WINDOWS or not shutil.which("journalctl"):
            raise ValueError(L("journald есть только на Linux", "journald is Linux-only"))
        r = subprocess.run(["journalctl"] + (["--user"] if w["scope"] == "user" else []) +
                           ["-u", w["target"], "-n", str(n), "-o", "cat", "--no-pager"],
                           capture_output=True, text=True, timeout=20)
        lines = r.stdout.splitlines()
    hits = [ln[:300] for ln in lines if rx.search(ln)]
    return {"checked": len(lines), "matches": len(hits), "sample": hits[-20:]}


def public_status():
    return {k: dict(v) for k, v in status.items()}
