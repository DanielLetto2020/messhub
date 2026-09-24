#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Резервные копии базы в ~/.local/share/<APP_ID>/backups/.

  messages-ГГГГММДД-ЧЧММСС-auto.db            — ежедневная (если включено), хранятся N последних
  messages-…-manual.db                        — «Сделать копию сейчас», не удаляются сами
  messages-…-before-restore.db                — снимок перед восстановлением
  legacy-….db, messages-backup-….db           — копии времён до переезда в XDG

Копия делается через backup API SQLite — согласованный снимок даже во время записи.
Восстановление копирует выбранную копию поверх живой базы (тем же API) — сбор и
виджет продолжают работать; перед этим всегда делается снимок before-restore.
"""

import os
import re
import sqlite3
from datetime import datetime

import catcher
import paths
import rules
from i18n import L

_RE_NAME = re.compile(r"^[\w.-]{1,120}\.db$")


def _copy(src_path, dst_path):
    src = sqlite3.connect(src_path, timeout=10)
    dst = sqlite3.connect(dst_path, timeout=10)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def make(db_path, label="manual"):
    os.makedirs(paths.BACKUP_DIR, exist_ok=True)
    name = f"messages-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{label}.db"
    _copy(db_path, os.path.join(paths.BACKUP_DIR, name))
    return name


def _kind(name):
    for k in ("auto", "manual", "before-restore"):
        if name.endswith(f"-{k}.db"):
            return k
    return "legacy"


def list_backups():
    if not os.path.isdir(paths.BACKUP_DIR):
        return []
    out = []
    for n in os.listdir(paths.BACKUP_DIR):
        p = os.path.join(paths.BACKUP_DIR, n)
        if n.endswith(".db") and os.path.isfile(p):
            st = os.stat(p)
            out.append({"name": n, "bytes": st.st_size, "kind": _kind(n),
                        "at": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")})
    return sorted(out, key=lambda b: b["at"], reverse=True)


def rotate(keep):
    """Оставить keep последних ежедневных копий; ручные и прочие не трогаем."""
    autos = [b for b in list_backups() if b["kind"] == "auto"]
    for b in autos[keep:]:
        os.remove(os.path.join(paths.BACKUP_DIR, b["name"]))
    return max(0, len(autos) - keep)


def restore(db_path, name):
    if not _RE_NAME.match(name or "") or name not in {b["name"] for b in list_backups()}:
        raise ValueError(L("Нет такой резервной копии", "No such backup"))
    before = make(db_path, "before-restore")
    _copy(os.path.join(paths.BACKUP_DIR, name), db_path)
    catcher.init_db(db_path).close()          # копия могла быть со старой схемой — досоздать
    return before


def daily(db_path):
    """Из фонового цикла: раз в сутки — копия и чистка старых. → имя копии или None."""
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        prefs = rules.get_prefs(conn)
        today = catcher.msk_time()[:10]
        if not prefs["backup"]["enabled"] or prefs["backup_last"] == today:
            return None
        name = make(db_path, "auto")
        rotate(prefs["backup"]["keep"])
        rules.set_prefs(conn, {"backup_last": today})
        conn.commit()
        return name
    finally:
        conn.close()
