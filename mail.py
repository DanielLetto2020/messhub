#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Почта напрямую из ящиков (IMAP) — вторая возможность наравне с уведомлениями.

Канал почты один — prefs.mail_channel:
  "notify" (по умолчанию) — как раньше: уведомления почтовых программ (Thunderbird,
           Evolution, Geary) и почтовых сайтов в браузере попадают в колонку «Почта»;
  "imap"   — программа сама забирает новые письма из подключённых ящиков, а уведомления
           почтовых программ и сайтов НЕ записываются (иначе было бы по два экземпляра).

Ящиков сколько угодно. Для каждого фоновый поток раз в N минут (по умолчанию 2):
  EXAMINE папки (только чтение) → письма с UID больше запомненного → BODY.PEEK[]
  (первые 64 КБ; PEEK — письмо на сервере НЕ становится прочитанным) → запись в базу.
При первом подключении ящика запоминается его последнее письмо: старая почта не
заливает виджет, приходит только новая. Состояние — таблица mail_state.

В виджете письмо — это колонка «Почта» (ключ источника "mail"), чат — название ящика,
отправитель — «От», текст — тема и начало письма. Поэтому обычные правила работают:
«из чата «Работа»» = из этого ящика, «от «Иван»», «с текстом «счёт»», звук, пересылка…

Для получения писем нужен именно IMAP (SMTP — протокол ОТПРАВКИ). Ящики и пароли —
~/.config/<APP_ID>/mail.json (права 600); пароль в API и на страницу не отдаётся.
Многие почтовые службы (Яндекс, Gmail, Mail.ru) пускают сторонние программы только
по «паролю приложения» — его создают в настройках безопасности почты.
"""

import email
import email.policy
import email.utils
import imaplib
import json
import os
import re
import secrets
import socket
import sqlite3
import ssl
import threading
import time
from datetime import datetime

import catcher
import paths
import rules
from i18n import L

CFG = os.environ.get(f"{paths.ENV_PREFIX}_MAIL_CFG") or os.path.join(paths.CONFIG_DIR, "mail.json")
APP = "mail-imap"                      # app у писем из ящиков → источник «Почта»
FETCH_BYTES = 65536                    # сколько письма забирать (для темы и начала текста)
MAX_PER_CHECK = 50                     # за одну проверку не больше стольких писем
PRESETS = {                            # (сервер, порт, защита)
    "yandex": ("imap.yandex.ru", 993, "ssl"),
    "mailru": ("imap.mail.ru", 993, "ssl"),
    "gmail": ("imap.gmail.com", 993, "ssl"),
    "outlook": ("outlook.office365.com", 993, "ssl"),
    "icloud": ("imap.mail.me.com", 993, "ssl"),
}
SECURITY = ("ssl", "starttls", "none")   # none — только для 127.0.0.1 (локальные мосты вроде Proton Bridge)
# Сертификат проверяется всегда. Исключение — ЯВНАЯ галочка «не проверять сертификат»
# (insecure), и только для сервера на этом же компьютере: локальные мосты работают с
# самоподписанным сертификатом, а перехватить соединение внутри машины снаружи нельзя.
_LOCAL = ("127.0.0.1", "localhost", "::1")

state = {}          # id ящика → {"checked": "ГГГГ-ММ-ДД ЧЧ:ММ:СС", "error": "", "new": n}
_lock = threading.Lock()


# ── настройки ящиков ────────────────────────────────────────────────────────

def load_accounts():
    try:
        with open(CFG, encoding="utf-8") as f:
            data = json.load(f)
        return [a for a in data.get("accounts", []) if isinstance(a, dict) and a.get("id")]
    except (OSError, ValueError):
        return []


def _write(accounts):
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    paths.write_private(CFG, json.dumps({"accounts": accounts}, ensure_ascii=False, indent=1))


def public_accounts():
    out = []
    for a in load_accounts():
        p = {k: a.get(k) for k in ("id", "label", "host", "port", "security", "user", "folder",
                                   "interval", "enabled", "insecure")}
        p["has_password"] = bool(a.get("password"))
        p.update(state.get(a["id"], {}))
        out.append(p)
    return out


def clean_account(d, old=None):
    """Ящик из запроса → проверенный dict. Пустой пароль — оставить прежний."""
    def s(k, limit, default=""):
        v = d.get(k, default)
        if not isinstance(v, str) or len(v) > limit:
            raise ValueError(L(f"Поле «{k}» слишком длинное", f"Field “{k}” is too long"))
        return v.strip()
    a = {"id": (old or {}).get("id") or "m" + secrets.token_hex(4),
         "label": s("label", 40), "host": s("host", 200).lower(), "user": s("user", 200),
         "folder": s("folder", 200, "INBOX") or "INBOX", "security": d.get("security") or "ssl",
         "enabled": bool(d.get("enabled", True)), "insecure": bool(d.get("insecure"))}
    try:
        a["port"] = int(d.get("port") or (993 if a["security"] == "ssl" else 143))
        a["interval"] = min(60, max(1, int(d.get("interval") or 2)))
    except (TypeError, ValueError):
        raise ValueError(L("Порт и интервал — числа", "Port and interval must be numbers"))
    pw = d.get("password")
    a["password"] = pw if isinstance(pw, str) and pw else (old or {}).get("password", "")
    if not a["host"] or not a["user"]:
        raise ValueError(L("Нужны сервер и логин", "Server and login are required"))
    if a["security"] not in SECURITY:
        raise ValueError(L("Неизвестный способ защиты", "Unknown security option"))
    if a["security"] == "none" and a["host"] not in _LOCAL:
        raise ValueError(L("Без шифрования можно только к серверу на этом компьютере (127.0.0.1)",
                           "Unencrypted connections are only allowed to this computer (127.0.0.1)"))
    if a["insecure"] and a["host"] not in _LOCAL:
        raise ValueError(L("Не проверять сертификат можно только для сервера на этом компьютере (127.0.0.1)",
                           "Skipping certificate checks is only allowed for a server on this computer (127.0.0.1)"))
    if not (0 < a["port"] < 65536):
        raise ValueError(L("Неверный порт", "Invalid port"))
    if not a["password"]:
        raise ValueError(L("Нужен пароль (для многих почт — «пароль приложения»)",
                           "A password is required (an “app password” for many providers)"))
    a["label"] = a["label"] or a["user"]
    return a


def save_account(d):
    accounts = load_accounts()
    old = next((a for a in accounts if a["id"] == d.get("id")), None)
    a = clean_account(d, old)
    accounts = [a if x["id"] == a["id"] else x for x in accounts] if old else accounts + [a]
    _write(accounts)
    return a


def delete_account(conn, acc_id):
    _write([a for a in load_accounts() if a["id"] != acc_id])
    conn.execute("DELETE FROM mail_state WHERE account = ?", (acc_id,))
    state.pop(acc_id, None)


def channel(conn):
    return rules.get_prefs(conn).get("mail_channel", "notify")


# ── IMAP ────────────────────────────────────────────────────────────────────

def _connect(a, timeout=20):
    ctx = ssl.create_default_context()
    if a.get("insecure") and a["host"] in _LOCAL:   # только по явной галочке и только локально
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    if a["security"] == "ssl":
        m = imaplib.IMAP4_SSL(a["host"], a["port"], ssl_context=ctx, timeout=timeout)
    else:
        m = imaplib.IMAP4(a["host"], a["port"], timeout=timeout)
        if a["security"] == "starttls":
            m.starttls(ssl_context=ctx)
    m.login(a["user"], a["password"])
    return m


def _examine(m, folder):
    typ, data = m.select(_quote(folder), readonly=True)
    if typ != "OK":
        raise imaplib.IMAP4.error(L(f"Нет папки «{folder}»", f"No folder “{folder}”"))
    uidvalidity = _status_num(m, "UIDVALIDITY")
    return uidvalidity


def _quote(folder):
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _status_num(m, key):
    typ, data = m.response(key)
    try:
        return int(data[0]) if data and data[0] else 0
    except (TypeError, ValueError):
        return 0


def _human(e):
    """Ошибка подключения → текст для человека."""
    if isinstance(e, imaplib.IMAP4.error):
        msg = str(e)
        if "AUTHENTICATE" in msg.upper() or "LOGIN" in msg.upper() or "credentials" in msg.lower():
            return L(f"Сервер не принял логин или пароль ({msg}). Для многих почт нужен «пароль приложения».",
                     f"The server rejected the login or password ({msg}). Many providers need an “app password”.")
        return msg
    if isinstance(e, (socket.timeout, TimeoutError)):
        return L("Сервер не ответил вовремя", "The server did not respond in time")
    if isinstance(e, ssl.SSLError):
        return L(f"Ошибка шифрования: {e}", f"Encryption error: {e}")
    if isinstance(e, OSError):
        return L(f"Не удалось подключиться: {e}", f"Could not connect: {e}")
    return str(e)


def test(d):
    """Проверить ящик (из формы или сохранённый). → (ok, текст, писем в папке)."""
    old = next((a for a in load_accounts() if a["id"] == d.get("id")), None)
    a = clean_account(d, old)
    try:
        m = _connect(a)
        try:
            _examine(m, a["folder"])
            typ, data = m.uid("SEARCH", None, "ALL")
            n = len(data[0].split()) if typ == "OK" and data and data[0] else 0
        finally:
            _logout(m)
        return True, "", n
    except Exception as e:  # сеть, TLS, логин, папка
        return False, _human(e), 0


def _logout(m):
    try:
        m.logout()
    except Exception:
        pass


def _text_of(msg):
    """Начало текста письма: первая text/plain, иначе text/html без тегов."""
    html = None
    for part in msg.walk():
        if part.get_content_maintype() == "multipart" or part.get_content_disposition() == "attachment":
            continue
        try:
            body = part.get_content()
        except Exception:     # обрезанное (мы берём первые 64 КБ) или битое — пропускаем
            continue
        if not isinstance(body, str):
            continue
        if part.get_content_type() == "text/plain":
            return body
        if part.get_content_type() == "text/html" and html is None:
            html = re.sub(r"(?is)<(script|style).*?</\1>|<[^>]+>", " ", body)
    return html or ""


def parse(raw):
    """Письмо (байты) → (от кого, тема, начало текста, есть вложения, время)."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    name, addr = email.utils.parseaddr(str(msg.get("From", "") or ""))
    subject = " ".join(str(msg.get("Subject", "") or "").split())
    snippet = " ".join(_text_of(msg).split())[:240]
    attach = any(p.get_content_disposition() == "attachment" for p in msg.walk())
    try:
        ts = email.utils.parsedate_to_datetime(str(msg.get("Date"))).timestamp()
    except (TypeError, ValueError, IndexError):
        ts = time.time()
    return (name or addr or "—"), subject, snippet, attach, ts


def check(db_path, a, conn=None):
    """Забрать новые письма ящика и записать их. → сколько новых."""
    own = conn is None
    conn = conn or catcher.init_db(db_path)
    try:
        m = _connect(a)
        try:
            uidvalidity = _examine(m, a["folder"])
            row = conn.execute("SELECT uidvalidity, last_uid FROM mail_state WHERE account = ?",
                               (a["id"],)).fetchone()
            typ, data = m.uid("SEARCH", None, "ALL")
            uids = [int(x) for x in (data[0].split() if typ == "OK" and data and data[0] else [])]
            top = max(uids, default=0)
            if not row or row[0] != uidvalidity:
                # первое подключение (или ящик пересоздан) — старые письма не тащим
                conn.execute("INSERT OR REPLACE INTO mail_state (account, uidvalidity, last_uid, checked_at) "
                             "VALUES (?,?,?,?)", (a["id"], uidvalidity, top, catcher.msk_time()))
                conn.commit()
                return 0
            new = sorted(u for u in uids if u > row[1])[:MAX_PER_CHECK]
            n = 0
            for uid in new:
                typ, data = m.uid("FETCH", str(uid), f"(BODY.PEEK[]<0.{FETCH_BYTES}>)")
                raw = next((p[1] for p in data if isinstance(p, tuple)), None) if typ == "OK" else None
                if raw:
                    _store(conn, a, uid, raw)
                    n += 1
                conn.execute("UPDATE mail_state SET last_uid = ?, checked_at = ? WHERE account = ?",
                             (uid, catcher.msk_time(), a["id"]))
                conn.commit()
            conn.execute("UPDATE mail_state SET checked_at = ? WHERE account = ?", (catcher.msk_time(), a["id"]))
            conn.commit()
            return n
        finally:
            _logout(m)
    finally:
        if own:
            conn.close()


def _store(conn, a, uid, raw):
    sender, subject, snippet, attach, ts = parse(raw)
    text = subject + ("\n" + snippet if snippet else "")
    rec = {"app": APP, "chat": a["label"], "sender": sender, "is_bot": catcher.guess_is_bot(sender),
           "message": text or L("(без темы)", "(no subject)"), "notification_id": uid, "urgency": 1,
           "has_media": 1 if attach else 0, "event_ts": ts,
           "event_iso": datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
           "raw_summary": subject, "raw_body": f"{a['label']}\n{sender}\n{subject}", "site": "", "avatar": None}
    rec["id"] = catcher.insert(conn, rec)
    try:
        rules.apply_on_insert(conn, rec)
    except Exception as e:  # правило не должно ронять почту
        print(f"Почта: действия правил: {e!r}", flush=True)


def check_now(db_path, acc_id):
    a = next((x for x in load_accounts() if x["id"] == acc_id), None)
    if not a:
        raise ValueError(L("Нет такого ящика", "No such mailbox"))
    return _run_one(db_path, a)


def _run_one(db_path, a):
    with _lock:
        try:
            n = check(db_path, a)
            state[a["id"]] = {"checked": catcher.msk_time(), "error": "", "new": n}
            if n:
                print(f"Почта «{a['label']}»: новых писем {n}", flush=True)
            return n
        except Exception as e:
            state[a["id"]] = {"checked": catcher.msk_time(), "error": _human(e), "new": 0}
            raise ValueError(state[a["id"]]["error"])


def start(db_path):
    """Фоновый поток (в процессе сбора): раз в 30 с — ящики, у которых подошёл срок."""
    last = {}

    def loop():
        while True:
            try:
                conn = sqlite3.connect(db_path, timeout=5)
                try:
                    on = channel(conn) == "imap"
                finally:
                    conn.close()
                if on:
                    for a in load_accounts():
                        if a.get("enabled", True) and time.time() - last.get(a["id"], 0) >= a.get("interval", 2) * 60:
                            last[a["id"]] = time.time()
                            try:
                                _run_one(db_path, a)
                            except ValueError as e:
                                print(f"Почта «{a.get('label')}»: {e}", flush=True)
            except sqlite3.Error as e:
                print(f"Почта: ошибка базы: {e}", flush=True)
            time.sleep(30)
    threading.Thread(target=loop, name="mail", daemon=True).start()
