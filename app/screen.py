#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Идёт ли показ экрана (демонстрация на созвоне) — чтобы доска размылась сама.

Системного флага «сейчас экран показывают» нет, поэтому признаков несколько:
  - окна-индикаторы программ: браузеры на Chromium показывают панельку «Приложению … предоставлен
    доступ к вашему экрану» / «… is sharing your screen», Firefox — индикатор общего доступа,
    Zoom — панель демонстрации (окно as_toolbar); список дополняется в настройках;
  - PipeWire (Wayland и портал): работающий поток захвата экрана (`pw-dump`).
Окна перебирает окно доски (widget.py — через libwnck, winwidget.py — через EnumWindows), здесь —
только сверка заголовков и разбор pw-dump.
"""

import json
import shutil
import subprocess

DEFAULT_PATTERNS = (
    "is sharing your screen", "is sharing a window", "is sharing a chrome tab", "is sharing this tab",
    "предоставлен доступ к вашему экрану", "предоставило доступ к экрану", "демонстрирует окно",
    "предоставило доступ к вкладке", "sharing indicator", "индикатор общего доступа", "as_toolbar",
)


def title_match(titles, extra=()):
    """Первый заголовок окна, похожий на индикатор показа экрана, или ''."""
    pats = [p.lower() for p in (*DEFAULT_PATTERNS, *extra) if p]
    for t in titles:
        low = (t or "").lower()
        if any(p in low for p in pats):
            return t
    return ""


def pipewire_sharing(dump=None):
    """Работает ли поток захвата экрана в PipeWire. dump — готовый вывод pw-dump (для тестов)."""
    if dump is None:
        exe = shutil.which("pw-dump")
        if not exe:
            return False
        try:
            dump = subprocess.run([exe], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return False
    try:
        objs = json.loads(dump or "[]")
    except ValueError:
        return False
    for o in objs:
        if not isinstance(o, dict) or o.get("type") != "PipeWire:Interface:Node":
            continue
        info = o.get("info") or {}
        props = info.get("props") or {}
        blob = " ".join(str(props.get(k, "")) for k in ("node.name", "media.name", "node.description",
                                                         "application.name", "media.role")).lower()
        if info.get("state") == "running" and str(props.get("media.class", "")).startswith(("Video/Source", "Stream/")) \
                and any(w in blob for w in ("screencast", "screen-cast", "screen cast", "xdg-desktop-portal")):
            return True
    return False
