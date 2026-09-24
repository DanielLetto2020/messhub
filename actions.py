#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Действия правил, которые выходят за пределы БД: звук и пересылка в Telegram.

Звук — системный «message-new-instant» (canberra-gtk-play, иначе pw-play/paplay),
не чаще раза в секунду.

Пересылка — Telegram Bot API (sendMessage) в чат/группу пользователя. Это
ЕДИНСТВЕННОЕ, что уходит с компьютера, и только для сообщений, попавших под
правило «переслать в Telegram», которое пользователь создал сам.
Настройки — ~/.config/<APP_ID>/telegram-forward.json (права 600, см. paths.py):
    {"token": "<токен бота>", "chat_id": "<id чата/группы>", "thread_id": "<тема, необяз.>"}
Токен никогда не отдаётся в API и не пишется в лог.
Отправка — в фоновом потоке через очередь, не чаще раза в секунду.
"""

import json
import os
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import paths
from i18n import L

# для тестов можно подменить файл настроек и адрес Bot API (локальный фейковый сервер)
FORWARD_CFG = os.environ.get(f"{paths.ENV_PREFIX}_FORWARD_CFG") or paths.FORWARD_CFG
TG_API = os.environ.get(f"{paths.ENV_PREFIX}_TG_API", "https://api.telegram.org")

SOUND_NAME = "message-new-instant"
SOUND_FILE = "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga"
_last_sound = 0.0


def play_sound():
    global _last_sound
    if time.time() - _last_sound < 1.0:
        return
    _last_sound = time.time()
    if os.name == "nt":                     # Windows: системный звук уведомления
        import winsound
        winsound.PlaySound("SystemNotification", winsound.SND_ALIAS | winsound.SND_ASYNC)
        return
    for cmd in (["canberra-gtk-play", "-i", SOUND_NAME], ["pw-play", SOUND_FILE],
                ["paplay", SOUND_FILE]):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except FileNotFoundError:
            continue


# ── настройки пересылки ─────────────────────────────────────────────────────

def load_cfg():
    try:
        with open(FORWARD_CFG, encoding="utf-8") as f:
            c = json.load(f)
        return {k: str(c.get(k) or "").strip() for k in ("token", "chat_id", "thread_id")}
    except (OSError, ValueError):
        return {"token": "", "chat_id": "", "thread_id": ""}


def save_cfg(token, chat_id, thread_id):
    """token пустой — оставить прежний (страница его не знает и не присылает)."""
    old = load_cfg()
    cfg = {"token": (token or "").strip() or old["token"],
           "chat_id": (chat_id or "").strip(), "thread_id": (thread_id or "").strip()}
    if cfg["thread_id"] and not cfg["thread_id"].lstrip("-").isdigit():
        raise ValueError(L("Номер темы — число", "Topic id must be a number"))
    os.makedirs(os.path.dirname(FORWARD_CFG), exist_ok=True)
    paths.write_private(FORWARD_CFG, json.dumps(cfg))


def public_cfg():
    c = load_cfg()
    return {"configured": bool(c["token"] and c["chat_id"]),
            "token_hint": ("…" + c["token"][-4:]) if c["token"] else "",
            "chat_id": c["chat_id"], "thread_id": c["thread_id"]}


def send(text, cfg=None):
    """Отправить текст. → (ok, ошибка для человека)."""
    cfg = cfg or load_cfg()
    token = cfg["token"]
    if not (token and cfg["chat_id"]):
        return False, L("Пересылка не настроена: нужны токен бота и id чата",
                        "Forwarding is not set up: a bot token and chat id are needed")
    data = {"chat_id": cfg["chat_id"], "text": text[:4000], "disable_web_page_preview": "true"}
    if cfg["thread_id"]:
        data["message_thread_id"] = cfg["thread_id"]
    req = urllib.request.Request(f"{TG_API}/bot{token}/sendMessage",
                                 data=urllib.parse.urlencode(data).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = json.load(r)
        return bool(body.get("ok")), body.get("description", "")
    except urllib.error.HTTPError as e:
        try:
            desc = json.load(e).get("description", "")
        except ValueError:
            desc = ""
        return False, L(f"Telegram ответил {e.code}: {desc}",
                        f"Telegram replied {e.code}: {desc}").replace(token, "***")
    except Exception as e:  # сеть, DNS, таймаут
        return False, L(f"Не удалось связаться с Telegram: {e}",
                        f"Could not reach Telegram: {e}").replace(token, "***")


# ── очередь пересылки ───────────────────────────────────────────────────────

_q = queue.Queue()
_worker = None
_lock = threading.Lock()


def _loop():
    while True:
        text = _q.get()
        ok, err = send(text)
        if not ok:
            print(f"Пересылка в Telegram: {err}", flush=True)
        time.sleep(1.0)          # у Bot API лимиты на частоту — не торопимся


def forward(meta, rec):
    """Поставить уведомление в очередь на пересылку."""
    global _worker
    who = rec.get("sender") or ""
    text = f'{meta["ico"]} {meta["name"]} — {rec.get("chat") or ""}\n' \
           + (f"{who}: " if who and who != rec.get("chat") else "") + (rec.get("message") or "")
    with _lock:
        if _worker is None:
            _worker = threading.Thread(target=_loop, name="tg-forward", daemon=True)
            _worker.start()
    _q.put(text)
