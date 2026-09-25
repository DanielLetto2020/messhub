#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Язык сообщений сервера (ошибки, отчёты, названия источников) — русский или английский.

Страницы переводятся у себя (i18n.js); здесь — только то, что сервер пишет сам.
Язык выбирается на каждый запрос: настройка prefs.language ("ru" / "en"), а при
"auto" — по заголовку Accept-Language (у окна виджета это язык системы).
Фоновым задачам (отчёт в Telegram) язык ставится из настроек.
"""

import locale
import os
import subprocess
import sys
import threading

_local = threading.local()


def set_lang(lang):
    _local.lang = "en" if lang == "en" else "ru"


def lang():
    return getattr(_local, "lang", "ru")


def L(ru, en):
    """Строка на текущем языке."""
    return en if lang() == "en" else ru


def pick(pref, accept_language=""):
    if pref in ("ru", "en"):
        return pref
    first = (accept_language or "").split(",")[0].strip().lower()
    return "ru" if first.startswith(("ru", "uk", "be", "kk")) or not first else "en"


def system_lang():
    """Язык системы — для фоновых задач, когда в настройках «авто» (запроса с Accept-Language нет)."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(var, "")
        if v and v not in ("C", "POSIX") and not v.startswith("C."):
            return "ru" if v.lower().startswith(("ru", "uk", "be", "kk")) else "en"
    try:
        loc = (locale.getlocale()[0] or "").lower()
    except (ValueError, TypeError):
        loc = ""
    if not loc and sys.platform == "darwin":        # программе из Finder LANG не задают — язык из настроек Mac
        try:
            loc = subprocess.run(["defaults", "read", "-g", "AppleLocale"], capture_output=True, text=True,
                                 timeout=3).stdout.strip().lower()
        except (OSError, subprocess.SubprocessError):
            loc = ""
    return "ru" if loc.startswith(("ru", "uk", "be", "kk", "russian", "ukrainian")) else "en" if loc else "ru"


def background(pref):
    """Язык для фоновых задач: из настроек, при «авто» — язык системы."""
    return pref if pref in ("ru", "en") else system_lang()
