#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Команды, которые доска и окна шлют своему окну («move», «search:», «lock:1»…).

Разбор команд и арифметика перетаскивания одинаковы на всех системах, но лежали в двух
местах: widget.py (GTK+WebKit на Linux) и winwidget.py (pywebview на Windows).
Оба файла — это окно: чтобы открыть его, нужен либо GTK, либо pywebview, и на другой
системе такой модуль не импортируется - значит, разбор команд нельзя было проверить тестом
ни на одной платформе. Здесь только строки и числа: им не нужен ни графический стек,
ни база, и это проверяется везде (tests/test_pagecmd.py).

Пользоваться так:

    verb, arg = pagecmd.parse(msg)
    if verb == "resize":
        ...pagecmd.resize_geom(arg, self._g0, dx, dy, MIN_W, MIN_H)...
"""

import json

EDGES = ("n", "s", "e", "w", "ne", "nw", "se", "sw")

# verb → что делать с аргументом; None — команда не наша
VERBS = ("geom-start", "geom", "geom-end", "move", "resize", "lock", "settings", "share",
         "search", "search-nav", "search-close", "strip", "message", "close",
         "open", "opacity")


def parse(cmd):
    """Строка от страницы → (verb, аргумент) либо (None, None), если это не команда окна.

    Аргументы приводятся к тому типу, в котором их удобно употреблять: geom — пара чисел,
    opacity — число, message — id, open/share/search/strip — разобранный JSON."""
    if not isinstance(cmd, str) or not cmd:
        return None, None
    verb, _, tail = cmd.partition(":")
    if verb not in VERBS:
        return None, None
    if verb in ("geom-start", "lock", "search-nav", "settings"):
        return verb, tail.strip()
    if verb == "geom":                       # сдвиг мыши: «dx,dy»
        try:
            dx, dy = (float(v) for v in tail.split(","))
        except ValueError:
            return None, None
        return verb, (dx, dy)
    if verb == "opacity":
        try:
            return verb, float(tail)
        except ValueError:
            return None, None
    if verb == "message":
        return (verb, int(tail)) if tail.isdigit() else (None, None)
    if verb == "resize":
        return (verb, tail.strip()) if tail.strip() in EDGES else (None, None)
    if verb in ("share", "search", "strip", "open"):
        try:
            v = json.loads(tail)
        except ValueError:
            return None, None
        # ожидаем объект: «search:[1,2]» - не команда, а мусор со страницы
        return (verb, v) if isinstance(v, dict) else (None, None)
    return verb, None


def resize_geom(edge, g0, dx, dy, min_w, min_h):
    """Новое положение и размер при перетаскивании за край. g0 — (x, y, w, h) до мыши.

    → (x, y, w, h) или None, если это не край. Размер не меньше минимума. Тянем за
    север или запад - край уезжает, поэтому противоположный угол должен остаться на месте,
    иначе окно уедет из-под курсора."""
    if edge not in EDGES or g0 is None:
        return None
    x0, y0, w0, h0 = g0
    w = max(min_w, w0 + (dx if "e" in edge else -dx if "w" in edge else 0))
    h = max(min_h, h0 + (dy if "s" in edge else -dy if "n" in edge else 0))
    return (x0 + w0 - w if "w" in edge else x0,
            y0 + h0 - h if "n" in edge else y0,
            w, h)


def fix_points(edge):
    """За какие края держаться при изменении размера — pywebview (FixPoint из webview.window).

    Здесь только названия, чтобы не тянуть webview в тесты: "e" — держим левый край и т. п.
    Возвращает (west, north) — что зафиксировано."""
    if edge not in EDGES:
        return None
    return "w" in edge, "n" in edge


def locked_on(cmd):
    """«lock:1» → True, «lock:0» → False, другое — None (команда не про замок)."""
    verb, arg = parse(cmd)
    return {"1": True, "0": False}.get(arg) if verb == "lock" else None


def is_drag(cmd):
    """Команда перетаскивания, которую страница шлёт при движении мышью."""
    return parse(cmd)[0] in ("move", "resize")
