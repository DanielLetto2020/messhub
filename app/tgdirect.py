#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Прямой канал Telegram (MTProto через Telethon) — вторая возможность наравне с уведомлениями.

Зачем нужен: Telegram Desktop и веб-клиент обрезают текст в системных уведомлениях ОС
примерно на 255 символах. При включении прямого канала программа подключается напрямую к
аккаунту Telegram (ТОЛЬКО ЧТЕНИЕ входящих сообщений через MTProto) и получает полный текст
сообщений (до 4096 символов) без отправки отметки «прочитано» собеседнику.

Канал Telegram один — prefs.telegram_channel:
  "notify"  (по умолчанию) — как раньше: уведомления Telegram Desktop / web.telegram.org;
  "mtproto" — прямой поток входящих через Telethon; пока активна авторизованная сессия,
              системные уведомления Telegram не дублируются (collect.make_skip).

Конфигурация и StringSession хранятся строго локально в ~/.config/<APP_ID>/telegram-direct.json
с правами 600; api_hash и session никогда не отдаются наружу через HTTP API.
"""

import asyncio
import collections
import importlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime

import avatars
import catcher
import paths
import rules
import version
from i18n import L

CFG = os.environ.get(f"{paths.ENV_PREFIX}_TG_CFG") or paths.TG_DIRECT_CFG
LIB_DIR = os.environ.get(f"{paths.ENV_PREFIX}_PYLIBS") or paths.PYLIBS_DIR
APP = "telegram-mtproto"

DEFAULT_SETTINGS = {
    "chats": True,
    "groups": True,
    "channels": False,
    "bots": False,
    "include_muted": False,
    "download_avatars": True,
}

state = {
    "connected": False,
    "running": False,
    "error": "",
    "received": 0,
    "last_at": "",
    "installing_lib": False,
    "install_error": "",
}

_lock = threading.RLock()
_ver = 0
_sess_cache = {"sig": None, "ok": False}

_loop = None
_loop_ready = threading.Event()
_auth = None          # {"client", "api_id", "api_hash", "phone", "phone_code_hash", "step"}
_client = None        # активный фоновый клиент
_wake_evt = threading.Event()
_stop_evt = threading.Event()
_RE_HASH = re.compile(r"^[0-9a-fA-F]{16,64}$")
_RE_PHONE = re.compile(r"^\+\d{7,15}$")


# ── опциональная библиотека Telethon ─────────────────────────────────────────

def _ensure_lib_path():
    if os.path.isdir(LIB_DIR) and LIB_DIR not in sys.path:
        sys.path.insert(0, LIB_DIR)


def _import_telethon():
    try:
        return importlib.import_module("telethon")
    except ImportError:
        _ensure_lib_path()
        importlib.invalidate_caches()
        return importlib.import_module("telethon")


def lib_info():
    frozen = bool(getattr(sys, "frozen", False))
    try:
        mod = _import_telethon()
        return {
            "installed": True,
            "version": str(getattr(mod, "__version__", "")),
            "frozen": frozen,
            "can_install": False,
        }
    except ImportError:
        return {
            "installed": False,
            "version": "",
            "frozen": frozen,
            "can_install": (not frozen) and bool(sys.executable),
        }


def install_lib():
    """Установить telethon в ~/.local/share/<APP_ID>/pylibs в фоне (для Linux без sudo)."""
    info = lib_info()
    if info["installed"]:
        return {"ok": True, "already": True, "lib": info}
    if not info["can_install"]:
        raise ValueError(L("Автоустановка недоступна в этой сборке",
                           "Automatic installation is not available in this build"))
    with _lock:
        if state["installing_lib"]:
            return {"ok": True, "installing": True, "lib": info}
        state["installing_lib"] = True
        state["install_error"] = ""

    def worker():
        try:
            os.makedirs(LIB_DIR, exist_ok=True)
            cmd = [sys.executable, "-m", "pip", "install", "--no-input",
                   "--upgrade", "--target", LIB_DIR, "telethon>=1.36,<2"]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if p.returncode != 0:
                tail = (p.stderr or p.stdout or "").strip().splitlines()[-3:]
                raise RuntimeError(" | ".join(tail) or f"pip exit {p.returncode}")
            _ensure_lib_path()
            importlib.invalidate_caches()
            _import_telethon()
            wake()
        except Exception as e:  # noqa: BLE001 — ошибка pip не роняет сервер
            state["install_error"] = str(e)[:400]
        finally:
            with _lock:
                state["installing_lib"] = False

    threading.Thread(target=worker, name="tg-pip", daemon=True).start()
    return {"ok": True, "installing": True}


# ── конфигурация и секреты (строго локально, права 600) ───────────────────────

def cfg_path():
    return os.environ.get(f"{paths.ENV_PREFIX}_TG_CFG") or CFG


def load_cfg():
    try:
        with open(cfg_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_cfg(cfg):
    global _ver
    p = cfg_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    paths.write_private(p, json.dumps(cfg, ensure_ascii=False, indent=1))
    with _lock:
        _ver += 1
        _sess_cache["sig"] = None


def clean_settings(v):
    cur = dict(DEFAULT_SETTINGS)
    if isinstance(v, dict):
        for k in DEFAULT_SETTINGS:
            if k in v:
                cur[k] = bool(v[k])
    return cur


def save_settings(patch):
    with _lock:
        cfg = load_cfg()
        merged = {**clean_settings(cfg.get("settings")), **({k: patch[k] for k in DEFAULT_SETTINGS if k in (patch or {})})}
        cfg["settings"] = clean_settings(merged)
        _save_cfg(cfg)
        return cfg["settings"]


def has_session():
    p = cfg_path()
    try:
        st = os.stat(p)
        sig = (p, st.st_mtime_ns, st.st_size)
    except OSError:
        sig = (p, None, 0)
    with _lock:
        if _sess_cache["sig"] == sig:
            return _sess_cache["ok"]
    cfg = load_cfg()
    ok = bool(cfg.get("api_id") and cfg.get("api_hash") and cfg.get("session"))
    with _lock:
        _sess_cache.update(sig=sig, ok=ok)
    return ok


def mode_version():
    return _ver


def bump_mode():
    global _ver
    with _lock:
        _ver += 1


def channel(conn):
    return rules.get_prefs(conn)["telegram_channel"]


def _mask_phone(p):
    s = re.sub(r"\s+", "", str(p or ""))
    if len(s) <= 6:
        return s
    return s[:4] + "***" + s[-4:]


def public_status(conn=None):
    cfg = load_cfg()
    ch = channel(conn) if conn is not None else "notify"
    ah = str(cfg.get("api_hash") or "")
    acc = cfg.get("account") if isinstance(cfg.get("account"), dict) else None
    step = _auth["step"] if _auth else ""
    auth_phone = _mask_phone(_auth["phone"]) if _auth else ""
    return {
        "channel": ch,
        "lib": lib_info(),
        "installing_lib": state["installing_lib"],
        "install_error": state["install_error"],
        "api_id": cfg.get("api_id") or "",
        "has_api_hash": bool(ah),
        "api_hash_hint": ("…" + ah[-4:]) if len(ah) >= 4 else "",
        "authorized": bool(cfg.get("api_id") and ah and cfg.get("session")),
        "account": {
            "name": str(acc.get("name") or ""),
            "username": str(acc.get("username") or ""),
            "phone": _mask_phone(acc.get("phone") or ""),
        } if acc else None,
        "auth_step": step,
        "auth_phone": auth_phone,
        "settings": clean_settings(cfg.get("settings")),
        "connected": state["connected"],
        "running": state["running"],
        "error": state["error"],
        "received": state["received"],
        "last_at": state["last_at"],
    }


# ── единый цикл asyncio в фоновом потоке ──────────────────────────────────────

def _ensure_loop():
    global _loop
    with _lock:
        if _loop is not None and not _loop.is_closed():
            return _loop
        _loop_ready.clear()

        def run():
            global _loop
            lp = asyncio.new_event_loop()
            asyncio.set_event_loop(lp)
            _loop = lp
            _loop_ready.set()
            try:
                lp.run_forever()
            finally:
                lp.close()

        threading.Thread(target=run, name="tg-asyncio", daemon=True).start()
    _loop_ready.wait(timeout=5)
    return _loop


def _run_coro(coro, timeout=30):
    lp = _ensure_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, lp)
    return fut.result(timeout=timeout)


def _human(e):
    name = type(e).__name__
    s = str(e)
    if name == "ApiIdInvalidError":
        return L("Неверный api_id или api_hash (проверь на my.telegram.org)",
                 "Invalid api_id or api_hash (check on my.telegram.org)")
    if name == "PhoneNumberInvalidError":
        return L("Неверный номер телефона (нужен формат +79991234567)",
                 "Invalid phone number (use format +15551234567)")
    if name == "PhoneCodeInvalidError":
        return L("Неверный код подтверждения", "Invalid verification code")
    if name == "PhoneCodeExpiredError":
        return L("Код устарел — запроси новый", "The code has expired — request a new one")
    if name == "PasswordHashInvalidError":
        return L("Неверный облачный пароль (2FA)", "Invalid two-factor password")
    if name == "FloodWaitError":
        sec = getattr(e, "seconds", 0)
        return L(f"Telegram просит подождать {sec} с", f"Telegram asks to wait {sec}s")
    if name in ("AuthKeyUnregisteredError", "SessionRevokedError", "UserDeactivatedBanError"):
        return L("Сессия Telegram завершена — войди заново", "Telegram session ended — sign in again")
    return s[:300] or name


# ── пошаговая авторизация ────────────────────────────────────────────────────

async def _disconnect_quiet(client):
    if client is None:
        return
    try:
        await client.disconnect()
    except Exception:  # noqa: BLE001
        pass


def send_code(api_id_raw, api_hash_raw, phone_raw):
    global _auth
    mod = _import_telethon()
    from telethon.sessions import StringSession

    cfg = load_cfg()
    try:
        api_id = int(str(api_id_raw or cfg.get("api_id") or "").strip())
    except ValueError as e:
        raise ValueError(L("api_id должен быть целым числом", "api_id must be an integer")) from e
    if api_id <= 0:
        raise ValueError(L("api_id должен быть положительным числом", "api_id must be a positive integer"))

    api_hash = str(api_hash_raw or "").strip() or str(cfg.get("api_hash") or "").strip()
    if not _RE_HASH.match(api_hash):
        raise ValueError(L("api_hash — строка из 32 hex-символов с my.telegram.org",
                           "api_hash must be a 32-char hex string from my.telegram.org"))

    phone = re.sub(r"[\s\-()]+", "", str(phone_raw or "").strip())
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    if not _RE_PHONE.match(phone):
        raise ValueError(L("Укажи номер в международном формате, например +79991234567",
                           "Enter the phone in international format, e.g. +15551234567"))

    cancel_auth()

    async def step():
        c = mod.TelegramClient(
            StringSession(), api_id, api_hash,
            device_model="messhub", app_version=version.__version__,
        )
        try:
            await c.connect()
            sent = await c.send_code_request(phone)
            return c, sent.phone_code_hash
        except Exception:
            await _disconnect_quiet(c)
            raise

    try:
        client, pch = _run_coro(step(), timeout=35)
    except Exception as e:
        raise ValueError(_human(e)) from e

    cfg.update({"api_id": api_id, "api_hash": api_hash, "settings": clean_settings(cfg.get("settings"))})
    _save_cfg(cfg)
    _auth = {
        "client": client,
        "api_id": api_id,
        "api_hash": api_hash,
        "phone": phone,
        "phone_code_hash": pch,
        "step": "code",
    }
    return {"step": "code", "phone": _mask_phone(phone)}


def sign_in(db_path, code="", password=""):
    global _auth
    if not _auth:
        raise ValueError(L("Сначала нажми «Отправить код»", "Click “Send code” first"))
    cur = _auth
    from telethon.errors import SessionPasswordNeededError

    async def finish():
        c = cur["client"]
        if cur["step"] == "code":
            clean_code = re.sub(r"[\s\-]+", "", str(code or ""))
            if not clean_code:
                raise ValueError(L("Введи код из Telegram", "Enter the code from Telegram"))
            try:
                await c.sign_in(phone=cur["phone"], code=clean_code, phone_code_hash=cur["phone_code_hash"])
            except SessionPasswordNeededError:
                cur["step"] = "password"
                return {"need_password": True}
        elif cur["step"] == "password":
            pw = str(password or "")
            if not pw:
                raise ValueError(L("Введи облачный пароль (2FA)", "Enter the two-factor password"))
            await c.sign_in(password=pw)
        else:
            raise ValueError(L("Неверное состояние входа", "Invalid sign-in state"))

        me = await c.get_me()
        sess_str = c.session.save()
        name = " ".join(x for x in (getattr(me, "first_name", ""), getattr(me, "last_name", "")) if x).strip()
        acc = {
            "id": getattr(me, "id", 0),
            "name": name or (getattr(me, "username", "") or cur["phone"]),
            "username": getattr(me, "username", "") or "",
            "phone": getattr(me, "phone", "") or cur["phone"],
        }
        return {"need_password": False, "session": sess_str, "account": acc}

    try:
        res = _run_coro(finish(), timeout=35)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(_human(e)) from e

    if res.get("need_password"):
        return {"ok": False, "need_password": True, "auth_step": "password"}

    _run_coro(_disconnect_quiet(cur["client"]), timeout=10)
    _auth = None
    cfg = load_cfg()
    cfg.update({
        "api_id": cur["api_id"],
        "api_hash": cur["api_hash"],
        "session": res["session"],
        "account": res["account"],
        "settings": clean_settings(cfg.get("settings")),
    })
    _save_cfg(cfg)

    conn = sqlite3.connect(db_path, timeout=5)
    try:
        rules.set_prefs(conn, {"telegram_channel": "mtproto"})
        conn.commit()
    finally:
        conn.close()
    state["error"] = ""
    bump_mode()
    wake()
    return {"ok": True, "need_password": False}


def cancel_auth():
    global _auth
    if _auth:
        c = _auth.get("client")
        _auth = None
        if c is not None and _loop is not None and not _loop.is_closed():
            try:
                _run_coro(_disconnect_quiet(c), timeout=5)
            except Exception:  # noqa: BLE001
                pass
    return {"ok": True}


def logout(db_path, remote=True):
    cancel_auth()
    cfg = load_cfg()
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        rules.set_prefs(conn, {"telegram_channel": "notify"})
        conn.commit()
    finally:
        conn.close()

    old_session = cfg.get("session")
    api_id, api_hash = cfg.get("api_id"), cfg.get("api_hash")
    for k in ("session", "account"):
        cfg.pop(k, None)
    _save_cfg(cfg)
    state.update(connected=False, error="", received=0, last_at="")
    reconnect()

    if remote and old_session and api_id and api_hash:
        try:
            mod = _import_telethon()
            from telethon.sessions import StringSession

            async def _drop():
                c = mod.TelegramClient(StringSession(old_session), int(api_id), api_hash,
                                       device_model="messhub", app_version=version.__version__)
                try:
                    await c.connect()
                    if await c.is_user_authorized():
                        await c.log_out()
                finally:
                    await _disconnect_quiet(c)

            _run_coro(_drop(), timeout=15)
        except Exception:  # noqa: BLE001 — локальная сессия в любом случае удалена
            pass
    return {"ok": True}


# ── обработка входящего события (чистая, без сети, строго только чтение) ───

def _media_label(msg):
    if getattr(msg, "photo", None):
        return "📷 " + L("Фото", "Photo")
    if getattr(msg, "voice", None):
        return "🎤 " + L("Голосовое сообщение", "Voice message")
    if getattr(msg, "video_note", None):
        return "🎥 " + L("Видеосообщение", "Video note")
    if getattr(msg, "sticker", None):
        alt = ""
        doc = getattr(msg, "document", None)
        for attr in (getattr(doc, "attributes", None) or ()):
            alt = getattr(attr, "alt", "") or alt
        return f"{alt or '🙂'} " + L("Стикер", "Sticker")
    if getattr(msg, "video", None) or getattr(msg, "gif", None):
        return "🎬 " + L("Видео", "Video")
    if getattr(msg, "audio", None):
        return "🎵 " + L("Аудио", "Audio")
    if getattr(msg, "document", None):
        name = getattr(getattr(msg, "file", None), "name", "") or ""
        return "📎 " + (name or L("Файл", "File"))
    if getattr(msg, "poll", None):
        q = getattr(getattr(msg.poll, "poll", None), "question", "")
        if hasattr(q, "text"):
            q = q.text
        return "📊 " + (str(q or "") or L("Опрос", "Poll"))
    if getattr(msg, "geo", None) or getattr(msg, "venue", None):
        return "📍 " + L("Геопозиция", "Location")
    if getattr(msg, "contact", None):
        return "👤 " + L("Контакт", "Contact")
    return ""


def _entity_name(ent):
    if ent is None:
        return ""
    title = getattr(ent, "title", None)
    if title:
        return str(title).strip()
    name = " ".join(x for x in (getattr(ent, "first_name", ""), getattr(ent, "last_name", "")) if x).strip()
    return name or str(getattr(ent, "username", "") or "").strip()


def process_event(conn, cfg, info, muted_peers=None):
    """Сохранить входящее сообщение из MTProto по фильтрам настроек. → message_id или None.
    Никогда не отправляет отметку прочтения на сервер Telegram."""
    s = clean_settings((cfg or {}).get("settings"))
    is_private = bool(info.get("is_private"))
    is_group = bool(info.get("is_group"))
    is_channel = bool(info.get("is_channel")) and not is_group
    is_bot = bool(info.get("is_bot"))

    if is_channel and not s["channels"]:
        return None
    if is_group and not s["groups"]:
        return None
    if is_private:
        if not s["chats"]:
            return None
        if is_bot and not s["bots"]:
            return None

    chat_id = info.get("chat_id")
    if not s["include_muted"] and muted_peers and chat_id in muted_peers:
        return None

    text = str(info.get("text") or "").strip()
    ml = str(info.get("media_label") or "").strip()
    full = f"{ml}\n{text}" if (ml and text) else (text or ml)
    if not full:
        return None

    chat = str(info.get("chat_title") or "").strip() or "Telegram"
    sender = str(info.get("sender_name") or "").strip() or chat
    ts = float(info.get("ts") or time.time())
    rec = {
        "app": APP,
        "chat": chat,
        "sender": sender,
        "is_bot": 1 if is_bot else 0,
        "message": full,
        "notification_id": int(info.get("msg_id") or 0),
        "urgency": 1,
        "has_media": 1 if info.get("has_media") else 0,
        "event_ts": ts,
        "event_iso": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
        "raw_summary": chat,
        "raw_body": full,
        "site": "",
        "avatar": info.get("avatar"),
        "fmt": None,
    }
    rec["id"] = catcher.insert(conn, rec)
    conn.commit()
    try:
        rules.apply_on_insert(conn, rec)
    except Exception as e:  # noqa: BLE001 — сбой правила не роняет приём Telegram
        print(f"Telegram MTProto: действия правил: {e!r}", flush=True)
    return rec["id"]


# ── фоновый слушатель (в процессе сбора) ──────────────────────────────────────

def wake():
    _wake_evt.set()


def reconnect():
    _stop_evt.set()
    c = _client
    if c is not None and _loop is not None and not _loop.is_closed():
        try:
            _loop.call_soon_threadsafe(lambda: asyncio.ensure_future(_disconnect_quiet(c)))
        except Exception:  # noqa: BLE001
            pass
    _wake_evt.set()


def _need_run(db_path):
    if not has_session():
        return False
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        return channel(conn) == "mtproto"
    finally:
        conn.close()


async def _refresh_muted(client):
    muted = set()
    now = time.time()
    try:
        async for dlg in client.iter_dialogs(limit=200):
            ns = getattr(getattr(dlg, "dialog", None), "notify_settings", None)
            until = getattr(ns, "mute_until", None)
            if until:
                ts = until.timestamp() if hasattr(until, "timestamp") else float(until)
                if ts > now:
                    muted.add(dlg.id)
    except Exception:  # noqa: BLE001
        pass
    return muted


async def _run_session(db_path, mod, cfg, seen, avatar_cache):
    global _client
    from telethon import events as tg_events
    from telethon.sessions import StringSession

    muted = {"ids": set(), "at": 0.0}
    c = mod.TelegramClient(
        StringSession(cfg["session"]), int(cfg["api_id"]), cfg["api_hash"],
        device_model="messhub", app_version=version.__version__,
    )
    _client = c
    state.update(running=True, error="")
    try:
        await c.connect()
        if not await c.is_user_authorized():
            state.update(connected=False, error=L("Сессия Telegram больше не активна — войди заново",
                                                  "Telegram session is no longer valid — sign in again"))
            return "unauth"
        state.update(connected=True, error="")
        muted["ids"] = await _refresh_muted(c)
        muted["at"] = time.time()

        @c.on(tg_events.NewMessage(incoming=True))
        async def on_new(ev):
            key = (ev.chat_id, ev.id)
            if key in seen:
                return
            seen.append(key)
            msg = ev.message
            chat = await ev.get_chat()
            sender = await ev.get_sender()
            is_priv = bool(ev.is_private)
            is_grp = bool(ev.is_group)
            is_ch = bool(ev.is_channel) and not is_grp
            is_bot = bool(getattr(sender, "bot", False) or getattr(chat, "bot", False))

            chat_title = _entity_name(chat) or _entity_name(sender) or "Telegram"
            sender_name = chat_title if (is_priv or is_ch) else (_entity_name(sender) or chat_title)

            cur_cfg = load_cfg()
            av_name = None
            if clean_settings(cur_cfg.get("settings")).get("download_avatars"):
                ent = sender if (not is_priv and sender is not None) else chat
                pid = getattr(ent, "id", None)
                if pid is not None and pid in avatar_cache:
                    av_name = avatar_cache[pid]
                elif ent is not None and getattr(ent, "photo", None):
                    try:
                        raw = await asyncio.wait_for(c.download_profile_photo(ent, file=bytes, download_big=False), 5)
                        if raw:
                            av_name = avatars._save(raw, "jpg")
                        if pid is not None:
                            avatar_cache[pid] = av_name
                    except Exception:  # noqa: BLE001
                        if pid is not None:
                            avatar_cache[pid] = None

            if not clean_settings(cur_cfg.get("settings")).get("include_muted") and time.time() - muted["at"] > 600:
                muted["ids"] = await _refresh_muted(c)
                muted["at"] = time.time()

            info = {
                "chat_id": ev.chat_id,
                "msg_id": ev.id,
                "is_private": is_priv,
                "is_group": is_grp,
                "is_channel": is_ch,
                "is_bot": is_bot,
                "chat_title": chat_title,
                "sender_name": sender_name,
                "text": getattr(msg, "raw_text", "") or getattr(msg, "message", "") or "",
                "media_label": _media_label(msg),
                "has_media": bool(getattr(msg, "media", None)),
                "ts": msg.date.timestamp() if getattr(msg, "date", None) else time.time(),
                "avatar": av_name,
            }
            conn = sqlite3.connect(db_path, timeout=5)
            try:
                if process_event(conn, cur_cfg, info, muted["ids"]):
                    state["received"] += 1
                    state["last_at"] = catcher.msk_time()
            finally:
                conn.close()

        async def watchdog():
            while c.is_connected():
                await asyncio.sleep(3)
                if _stop_evt.is_set() or not _need_run(db_path):
                    await _disconnect_quiet(c)
                    return

        wd = asyncio.ensure_future(watchdog())
        try:
            await c.run_until_disconnected()
        finally:
            wd.cancel()
        return "ok"
    finally:
        state["connected"] = False
        if _client is c:
            _client = None
        await _disconnect_quiet(c)


def start(db_path):
    """Запустить фоновый приём сообщений через MTProto (один на процесс)."""
    if getattr(start, "_started", False):
        return
    start._started = True

    def supervisor():
        seen = collections.deque(maxlen=500)
        avatar_cache = {}
        backoff = 5

        while True:
            _wake_evt.clear()
            _stop_evt.clear()
            try:
                if not _need_run(db_path):
                    state.update(connected=False, running=False)
                    _wake_evt.wait(10)
                    continue
                mod = _import_telethon()
            except ImportError:
                state.update(connected=False, running=False,
                             error=L("Библиотека Telethon не установлена", "Telethon library is not installed"))
                _wake_evt.wait(15)
                continue
            except sqlite3.Error as e:
                state["error"] = str(e)
                _wake_evt.wait(10)
                continue

            cfg = load_cfg()
            try:
                res = _run_coro(_run_session(db_path, mod, cfg, seen, avatar_cache), timeout=None)
                if res == "unauth":
                    _wake_evt.wait(60)
                else:
                    backoff = 5
                    if not _stop_evt.is_set() and _need_run(db_path):
                        _wake_evt.wait(3)
            except Exception as e:  # noqa: BLE001 — сеть отвалилась или клиент остановлен
                state.update(connected=False, error="" if _stop_evt.is_set() else _human(e))
                if _stop_evt.is_set():
                    backoff = 5
                else:
                    _wake_evt.wait(backoff)
                    backoff = min(60, backoff * 2)
            state["running"] = False

    threading.Thread(target=supervisor, name="tg-direct", daemon=True).start()
