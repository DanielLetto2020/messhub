#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Даты и время в тексте сообщения — для кнопки «напомнить» на плашке (reminders.py).

Без ИИ, регулярными выражениями, по-русски и по-английски:
  «в 15:00», «к 9.30», «сегодня в 18», «завтра в 10», «послезавтра», «в пятницу в 11», «к пятнице»,
  «25.09 в 14:00», «25.09.2026», «30 сентября в 11:30», «через 2 часа», «через 30 минут»,
  "at 3 pm", "at 15:00", "tomorrow at 10", "on Friday", "in 2 hours", "2026-09-30 14:00".
Отсчёт — от времени сообщения (base). Берём только будущее (относительно now) и не дальше
60 дней. Без часа («завтра», «в пятницу», дата) — 09:00 того дня, с пометкой date_only.
"""

import re
from datetime import datetime, timedelta

MONTHS = {"январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6, "июл": 7, "август": 8,
          "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12}
RU_DAYS = {"понедельник": 0, "вторник": 1, "сред": 2, "четверг": 3, "пятниц": 4, "суббот": 5, "воскресень": 6}
EN_DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
DEFAULT_HOUR = 9

_T = r"(?:\s*(?:в|во|к|на|at)\s*(\d{1,2})(?:[:.](\d{2}))?(?:\s*(am|pm))?)?"
PATTERNS = (
    ("iso", re.compile(r"\b(20\d\d)-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?\b")),
    ("dmy", re.compile(r"(?<![\d.:])(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?(?![\d:])" + r"(?:\s*(?:в|к|at)?\s*(\d{1,2})[:.](\d{2}))?")),
    ("month", re.compile(r"\b(\d{1,2})\s+(январ[яь]|феврал[яь]|марта?|апрел[яь]|ма[яй]|июн[яь]|июл[яь]|августа?|"
                         r"сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])(?:\s+(20\d\d))?" + _T, re.I)),
    ("relday", re.compile(r"\b(сегодня|завтра|послезавтра|today|tomorrow)" + _T, re.I)),
    ("weekday", re.compile(r"\b(?:в|во|on|к|ко|до|by)\s+(понедельник[ау]?|вторник[ау]?|сред[уеы]|четверг[ау]?|"
                           r"пятниц[уеы]|суббот[уеы]|воскресень[еюя]|"
                           r"monday|tuesday|wednesday|thursday|friday|saturday|sunday)" + _T, re.I)),
    ("in", re.compile(r"\b(?:через|in)\s+(\d{1,3}|полчаса|час|пару часов|an hour|half an hour)\s*"
                      r"(минут[уы]?|мин|час(?:а|ов)?|дн(?:я|ей)|день|minutes?|mins?|hours?|days?)?", re.I)),
    ("time", re.compile(r"(?:\b(?:в|во|к|до|на|at|by)\s*)(\d{1,2})[:.](\d{2})(?:\s*(am|pm))?(?![\d.:])|"
                        r"\bat\s+(\d{1,2})\s*(am|pm)\b", re.I)),
)


def _hm(h, m, ampm=None):
    h, m = int(h), int(m or 0)
    if ampm:
        a = ampm.lower()
        h = (h % 12) + (12 if a == "pm" else 0)
    return (h, m) if 0 <= h <= 23 and 0 <= m <= 59 else None


def _at(day, hm):
    if hm is None:
        return day.replace(hour=DEFAULT_HOUR, minute=0, second=0, microsecond=0), True
    return day.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0), False


def find(text, base, now=None, limit=3):
    """[{at: 'ГГГГ-ММ-ДД ЧЧ:ММ', text: найденное, date_only}] — будущие моменты из текста."""
    now = now or datetime.now()
    text = text or ""
    out, spans = [], []

    def add(dt, m, date_only=False):
        if dt is None or not (now < dt <= now + timedelta(days=60)):
            return
        if any(s <= m.start() < e or m.start() <= s < m.end() for s, e in spans):
            return                          # это место уже разобрано более точным шаблоном
        spans.append((m.start(), m.end()))
        key = dt.strftime("%Y-%m-%d %H:%M")
        if all(o["at"] != key for o in out):
            out.append({"at": key, "text": m.group(0).strip(), "date_only": date_only})

    for kind, rx in PATTERNS:
        for m in rx.finditer(text):
            g = m.groups()
            try:
                if kind == "iso":
                    day = datetime(int(g[0]), int(g[1]), int(g[2]))
                    dt, only = _at(day, _hm(g[3], g[4]) if g[3] else None)
                    add(dt, m, only)
                elif kind == "dmy":
                    d, mo = int(g[0]), int(g[1])
                    if not (1 <= d <= 31 and 1 <= mo <= 12):
                        continue
                    y = int(g[2]) if g[2] else base.year
                    y = y + 2000 if y < 100 else y
                    day = datetime(y, mo, d)
                    if not g[2] and day.date() < base.date():
                        day = day.replace(year=y + 1)
                    dt, only = _at(day, _hm(g[3], g[4]) if g[3] else None)
                    add(dt, m, only)
                elif kind == "month":
                    mo = next(v for k, v in MONTHS.items() if g[1].lower().startswith(k))
                    y = int(g[2]) if g[2] else base.year
                    day = datetime(y, mo, int(g[0]))
                    if not g[2] and day.date() < base.date():
                        day = day.replace(year=y + 1)
                    dt, only = _at(day, _hm(g[3], g[4], g[5]) if g[3] else None)
                    add(dt, m, only)
                elif kind == "relday":
                    w = g[0].lower()
                    shift = {"сегодня": 0, "today": 0, "завтра": 1, "tomorrow": 1, "послезавтра": 2}[w]
                    day = base + timedelta(days=shift)
                    dt, only = _at(day, _hm(g[1], g[2], g[3]) if g[1] else None)
                    add(dt, m, only)
                elif kind == "weekday":
                    w = g[0].lower()
                    wd = EN_DAYS.get(w)
                    if wd is None:
                        wd = next(v for k, v in RU_DAYS.items() if w.startswith(k))
                    ahead = (wd - base.weekday()) % 7 or 7
                    dt, only = _at(base + timedelta(days=ahead), _hm(g[1], g[2], g[3]) if g[1] else None)
                    add(dt, m, only)
                elif kind == "in":
                    n_raw, unit = g[0].lower(), (g[1] or "").lower()
                    if n_raw in ("полчаса", "half an hour"):
                        delta = timedelta(minutes=30)
                    elif n_raw in ("час", "an hour"):
                        delta = timedelta(hours=1)
                    elif n_raw == "пару часов":
                        delta = timedelta(hours=2)
                    else:
                        n = int(n_raw)
                        if unit.startswith(("мин", "min")):
                            delta = timedelta(minutes=n)
                        elif unit.startswith(("час", "hour")):
                            delta = timedelta(hours=n)
                        elif unit.startswith(("дн", "ден", "day")):
                            delta = timedelta(days=n)
                        else:
                            continue
                    add((base + delta).replace(second=0, microsecond=0), m)
                elif kind == "time":
                    hm = _hm(g[0], g[1], g[2]) if g[0] else _hm(g[3], 0, g[4])
                    if hm is None:
                        continue
                    dt = base.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
                    if dt < base:                 # «в 9:00», написанное в 18:00, — это завтра
                        dt += timedelta(days=1)
                    add(dt, m)
            except (ValueError, StopIteration):
                continue
        if len(out) >= limit:
            break
    out.sort(key=lambda o: o["at"])
    return out[:limit]
