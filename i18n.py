#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Язык сообщений сервера (ошибки, отчёты, названия источников) — русский или английский.

Страницы переводятся у себя (i18n.js); здесь — только то, что сервер пишет сам.
Язык выбирается на каждый запрос: настройка prefs.language ("ru" / "en"), а при
"auto" — по заголовку Accept-Language (у окна виджета это язык системы).
Фоновым задачам (отчёт в Telegram) язык ставится из настроек.
"""

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
