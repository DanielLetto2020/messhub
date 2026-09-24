#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Где программа хранит свои файлы — по стандарту XDG, отдельно от кода:

    ~/.local/share/<APP_ID>/messages.db        база (переписка — приватные данные)
    ~/.local/share/<APP_ID>/backups/           резервные копии базы
    ~/.config/<APP_ID>/widget-state.json       место и размер виджета
    ~/.config/<APP_ID>/telegram-forward.json   токен бота для пересылки (права 600)
    ~/.config/<APP_ID>/ingest.json             ключ приёма событий по HTTP (права 600)
    ~/.cache/<APP_ID>/avatars/                 аватары отправителей из уведомлений

Так `git pull` в папке с кодом никогда не лежит рядом с перепиской и токенами.
Уважаются XDG_DATA_HOME / XDG_CONFIG_HOME / XDG_CACHE_HOME; для тестов всё можно
увести в одну папку переменной <APP_ID>_HOME (EXPRESS_MSGS_HOME).

migrate_legacy() переносит файлы версий до 1.1.0, лежавшие рядом с кодом.
"""

import os
import shutil
import sqlite3
from datetime import datetime

from version import APP_ID, LEGACY_IDS

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PREFIX = APP_ID.upper().replace("-", "_")          # EXPRESS_MSGS


def _xdg(var, default, app_id=APP_ID):
    home = os.environ.get(f"{ENV_PREFIX}_HOME")
    if home:                                          # всё в одной папке (тесты)
        return os.path.join(home, default.rsplit("/", 1)[-1])
    base = os.environ.get(var) or os.path.expanduser(default)
    return os.path.join(base, app_id)


DATA_DIR = _xdg("XDG_DATA_HOME", "~/.local/share")
CONFIG_DIR = _xdg("XDG_CONFIG_HOME", "~/.config")
CACHE_DIR = _xdg("XDG_CACHE_HOME", "~/.cache")

DB_PATH = os.path.join(DATA_DIR, "messages.db")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
WIDGET_STATE = os.path.join(CONFIG_DIR, "widget-state.json")
FORWARD_CFG = os.path.join(CONFIG_DIR, "telegram-forward.json")
INGEST_CFG = os.path.join(CONFIG_DIR, "ingest.json")
AVATAR_DIR = os.path.join(CACHE_DIR, "avatars")


def ensure_dirs():
    for d in (DATA_DIR, BACKUP_DIR, CONFIG_DIR, AVATAR_DIR):
        os.makedirs(d, exist_ok=True)
    os.chmod(DATA_DIR, 0o700)
    os.chmod(CONFIG_DIR, 0o700)


def write_private(path, text):
    """Записать файл с правами 600 (токены, ключи)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, 0o600)


def _db_count(path):
    c = sqlite3.connect(path)
    try:
        return c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    finally:
        c.close()


def _merge_dir(old, new):
    """Перенести папку old → new. new ещё нет — просто переименовать; уже есть —
    долить файлы, которых в new нет (ничего не перезаписываем), и убрать old, если опустела."""
    if not os.path.isdir(old):
        return 0
    if not os.path.exists(new):
        os.makedirs(os.path.dirname(new), exist_ok=True)
        shutil.move(old, new)
        return 1
    n = 0
    for name in os.listdir(old):
        src, dst = os.path.join(old, name), os.path.join(new, name)
        if os.path.isdir(src):
            n += _merge_dir(src, dst)
        elif not os.path.exists(dst):
            shutil.move(src, dst)
            n += 1
    try:
        os.rmdir(old)
    except OSError:
        pass
    return n


def migrate_old_app_dirs(log=print):
    """Папки данных прежних имён проекта (LEGACY_IDS) → папки нынешнего APP_ID.
    Зовут install.sh (до запуска сервисов), сбор и виджет при старте."""
    if os.environ.get(f"{ENV_PREFIX}_HOME"):
        return []
    moved = []
    for old_id in LEGACY_IDS:
        for var, default in (("XDG_DATA_HOME", "~/.local/share"), ("XDG_CONFIG_HOME", "~/.config"),
                             ("XDG_CACHE_HOME", "~/.cache")):
            old, new = _xdg(var, default, old_id), _xdg(var, default)
            if os.path.isdir(old) and _merge_dir(old, new):
                moved.append(f"{old} → {new}")
    for m in moved:
        log(f"Перенесено: {m}")
    return moved


def move_legacy_file(name, dst, private=False):
    """Файл версий до 1.1.0 рядом с кодом → новое место (если там ещё пусто)."""
    src = os.path.join(HERE, name)
    if os.path.exists(src) and not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        if private:
            os.chmod(dst, 0o600)
        return True
    return False


def migrate_legacy(log=print):
    """До 1.1.0 база, состояние виджета и токен лежали рядом с кодом. Переносим:
    базу — копией через backup API со сверкой числа записей (старая копия уходит
    в backups/, из папки с кодом файлы убираются), остальное — перемещением.
    Если в новом месте уже есть база — ничего не трогаем. Сначала — папки прежних имён."""
    dirs = migrate_old_app_dirs(log)          # пишет в лог сам
    ensure_dirs()
    moved = []
    old_db = os.path.join(HERE, "messages.db")
    if os.path.exists(old_db) and not os.path.exists(DB_PATH):
        src = sqlite3.connect(old_db)
        dst = sqlite3.connect(DB_PATH)
        src.backup(dst)
        dst.close()
        n_old, n_new = src.execute("SELECT COUNT(*) FROM messages").fetchone()[0], _db_count(DB_PATH)
        src.close()
        if n_old != n_new:
            os.remove(DB_PATH)
            raise RuntimeError(f"перенос базы не сошёлся: было {n_old}, стало {n_new}")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(old_db, os.path.join(BACKUP_DIR, f"legacy-{stamp}.db"))
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(old_db + suffix):
                os.remove(old_db + suffix)
        moved.append(f"база ({n_new} записей) → {DB_PATH}")
    for name, dst in (("widget-state.json", WIDGET_STATE), ("telegram-forward.json", FORWARD_CFG)):
        if move_legacy_file(name, dst, private=name == "telegram-forward.json"):
            moved.append(f"{name} → {dst}")
    for name in os.listdir(HERE):            # резервные копии, сделанные раньше вручную
        if name.startswith("messages-backup") and name.endswith(".db"):
            shutil.move(os.path.join(HERE, name), os.path.join(BACKUP_DIR, name))
            moved.append(f"{name} → {BACKUP_DIR}")
    for m in moved:
        log(f"Перенесено: {m}")
    return dirs + moved
