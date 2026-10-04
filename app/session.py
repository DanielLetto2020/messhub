#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Токен локального API: кто может менять состояние, а кто только читать.

Зачем. Сервер слушает 127.0.0.1 и проверяет Host/Origin (serve.host_allowed), но любой
местный процесс - и любая страница, которую открыли в этом же браузере, - могла вызвать
POST без пароля: /api/purge, /api/prefs, /api/backups/restore, /api/scripts/run (он
выполняет скрипты), /api/mail/account (пишет пароль ящика). Данные у программы местные,
значит и доступ к ним должен быть не «всем, кто умеет открыть сокет».

Как. При первом запуске генерируется случайный токен (~/.config/<APP_ID>/session.json,
права 600). Он нужен двум способам:
  * страница получает его cookie (сервер ставит её, когда отдаёт страницу) - браузер
    подставляет её сам, человеку делать ничего не надо;
  * скрипт и curl передают его заголовком X-Messhub-Token: значение лежит в том же
    session.json, поэтому «как раньше» не получается - скрипт надо один раз поправить.

Что защищаем. Токен обязателен для всех POST и для GET /api/ingest/config (он отдаёт
ключ приёма событий). Чтение (/api/messages и прочее GET) остаётся доступным без токена:
виджет и страницы и так работают у пользователя, а посторонний процесс на этой машине
сообщения прочитать может и через файлы базы - токен защищает от вызова из чужой
страницы в браузере, а не от локального чтения файла.

Проверка Host/Origin/Sec-Fetch-Site остаётся вторым слоем: токен не отменяет её.
"""

import hmac
import json
import os
import secrets

import paths

COOKIE = "messhub_session"
HEADER = "X-Messhub-Token"

# Пути, которые меняют состояние или отдают секрет: без токена - 401.
# Список выводится из POST_ROUTES, поэтому новый POST нельзя забыть (см. serve.py).
GUARDED_GET = ("/api/ingest/config",)

_lock = None


def _token_lock():
    global _lock
    if _lock is None:
        import threading
        _lock = threading.Lock()
    return _lock


def token():
    """Токен этой установки; создаётся при первом обращении."""
    try:
        with open(paths.SESSION_CFG, encoding="utf-8") as f:
            t = str(json.load(f).get("token") or "")
        if t:
            return t
    except (OSError, ValueError):
        pass
    with _token_lock():
        # второй раз проверяем: пока писали, токен мог создать другое подключение
        try:
            with open(paths.SESSION_CFG, encoding="utf-8") as f:
                return str(json.load(f).get("token") or "")
        except (OSError, ValueError):
            pass
        t = secrets.token_urlsafe(32)
        paths.ensure_dirs()
        paths.write_private(paths.SESSION_CFG, json.dumps({"token": t}))
        return t


def rotate():
    """Новый токен (старый перестаёт работать - открытые страницы надо перезагрузить)."""
    t = secrets.token_urlsafe(32)
    paths.ensure_dirs()
    paths.write_private(paths.SESSION_CFG, json.dumps({"token": t}))
    return t


def _equal(a, b):
    # байтами: строки с не-ASCII compare_digest не сравнивает (TypeError вместо 403)
    return hmac.compare_digest((a or "").encode(), (b or "").encode())


def from_cookie(header):
    """Токен из заголовка Cookie: messhub_session=…"""
    for part in (header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE:
            return value.strip()
    return ""


def given(headers):
    """Что прислал клиент: заголовок или cookie."""
    return headers.get(HEADER, "") or from_cookie(headers.get("Cookie", ""))


def ok(headers):
    got = given(headers)
    return bool(got) and _equal(got, token())


def cookie_header():
    """Set-Cookie для ответа со страницей: Strict, без HttpOnly (странице он не мешает,
    но и читать его из JS не нужно - он и так подставляется браузером)."""
    # SameSite=Strict - cookie не уходит, даже если пользователь пришёл по ссылке с
    # чужого сайта; Path=/ - на все страницы; Max-Age до перезапуска программы.
    return f"{COOKIE}={token()}; Path=/; SameSite=Strict; Max-Age=86400"


def script_help():
    """Подсказка для раздела «Система»: как скрипту или curl передать токен."""
    path = os.path.abspath(paths.SESSION_CFG)
    home = os.path.expanduser("~")
    # внутри домашней папки - коротко («~/.config/…»), иначе полный путь: не «~/../..»
    shown = ("~/" + os.path.relpath(path, home).replace(os.sep, "/")
             if path.startswith(home + os.sep) else path)
    return {"header": HEADER, "file": shown,
            "how": f'токен лежит в {shown} (поле "token"); передать его: '
                   f'curl -H "{HEADER}: $(python3 -m json.tool {shown} | grep -m1 token | cut -d\\" -f4)" …'}
