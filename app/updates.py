#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Есть ли новая версия. Раз в 12 часов — один запрос к GitHub за номером последнего выпуска
(https://api.github.com/repos/<владелец>/messhub/releases/latest). О тебе и твоих сообщениях
ничего не отправляется: это обычный запрос страницы, как при открытии сайта в браузере.
Выключается в настройках («Система» → «Проверять новые версии»), тогда запросов нет вовсе.

Запрос идёт в фоновом потоке: страница получает то, что уже известно, и не ждёт сеть.
"""

import json
import os
import re
import threading
import time
import urllib.request

import version

API = os.environ.get("MESSHUB_UPDATE_URL") or \
    "https://api.github.com/repos/DanielLetto2020/messhub/releases/latest"
INTERVAL = 12 * 3600
_state = {"at": 0.0, "latest": "", "url": "", "error": "", "busy": False}
_lock = threading.Lock()


def parse(v):
    """«v1.0.12» / «1.0.12+unknown» → (1, 0, 12); непонятное → ()."""
    m = re.match(r"^v?(\d+(?:\.\d+)*)", (v or "").strip())
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def newer(latest, current):
    a, b = parse(latest), parse(current)
    return bool(a and b and a > b)


def _fetch():
    try:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": version.version_line().replace(" ", "/")})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.load(r)
        _state.update(latest=str(data.get("tag_name") or "").lstrip("v"),
                      url=str(data.get("html_url") or ""), error="")
    except (OSError, ValueError) as e:
        _state["error"] = str(e)
    finally:
        _state["at"] = time.time()
        _state["busy"] = False


def refresh(force=False):
    """Обновить сведения в фоне, если они устарели (или force)."""
    with _lock:
        if _state["busy"] or (not force and time.time() - _state["at"] < INTERVAL):
            return
        _state["busy"] = True
    threading.Thread(target=_fetch, name="updates", daemon=True).start()


def status(enabled=True, force=False):
    cur = version.__version__
    out = {"enabled": bool(enabled), "current": cur, "repo": version.REPO_URL,
           "releases": version.REPO_URL + "/releases/latest"}
    if not enabled:
        return out
    refresh(force)
    out.update(latest=_state["latest"], newer=newer(_state["latest"], cur),
               url=_state["url"] or out["releases"], checked=_state["at"], error=_state["error"])
    return out
