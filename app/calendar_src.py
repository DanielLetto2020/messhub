#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тематическая колонка «Календарь»: события из календарей на этом компьютере.

Откуда: календари GNOME Календаря и Evolution (локальные — ~/.local/share/evolution/calendar/*/
calendar.ics, подключённые учётные записи — кэш ~/.cache/evolution/calendar/*/cache.db) и свои
файлы .ics из настроек (выгрузка, папка синхронизации). Только чтение, сеть не нужна.

Что делает раз в минуту: за N минут до начала события — карточка «через 10 минут · 11:00–11:30»
(место — второй строкой); событие кончилось — карточка сама становится прочитанной. Утром в
заданное время — «план на сегодня» со списком событий. Повторы (RRULE) — простые: каждый
день/неделю (с днями недели)/месяц/год, INTERVAL, COUNT, UNTIL; отменённые (STATUS:CANCELLED) и
исключённые даты (EXDATE) пропускаются.
"""

import glob
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

import catcher
import events
import rules
from i18n import L

try:
    from zoneinfo import ZoneInfo
except ImportError:          # Python без zoneinfo — время с TZID считаем местным
    ZoneInfo = None

HOME = os.path.expanduser("~")
DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
status = {"running": False, "error": "", "sources": 0, "events": 0, "checked": ""}


def sources(extra=()):
    """Файлы календарей: [(путь, вид ics|eds)]."""
    out = []
    for p in sorted(glob.glob(os.path.join(HOME, ".local/share/evolution/calendar/*/calendar.ics"))):
        if "/trash/" not in p:
            out.append((p, "ics"))
    for p in sorted(glob.glob(os.path.join(HOME, ".cache/evolution/calendar/*/cache.db"))):
        if "/trash/" not in p:
            out.append((p, "eds"))
    for p in extra:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            out += [(f, "ics") for f in sorted(glob.glob(os.path.join(p, "*.ics")))]
        elif os.path.isfile(p):
            out.append((p, "ics"))
    return out


def read_texts(path, kind):
    """Текст iCalendar из файла или кэша EDS (каждая строка ECacheOBJ — VEVENT)."""
    if kind == "ics":
        with open(path, encoding="utf-8", errors="replace") as f:
            return [f.read()]
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    try:
        return [r[0] for r in conn.execute("SELECT ECacheOBJ FROM ECacheObjects") if r[0]]
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text).replace("\r", "").split("\n")


def parse_dt(value, params):
    """DTSTART/DTEND → (местное naive datetime, весь день?)."""
    v = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", v):
        return datetime.strptime(v[:8], "%Y%m%d"), True
    dt = datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
    if v.endswith("Z"):
        return dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None), False
    tz = params.get("TZID")
    if tz and ZoneInfo:
        try:
            return dt.replace(tzinfo=ZoneInfo(tz.strip('"'))).astimezone().replace(tzinfo=None), False
        except Exception:  # noqa: BLE001 — неизвестная зона (Windows без tzdata) — как местное
            pass
    return dt, False


def unescape(s):
    return s.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def parse_events(text):
    """VEVENT → [{uid, summary, location, start, end, all_day, rrule, exdates, cancelled}]."""
    out, cur, depth = [], None, 0
    for line in unfold(text):
        if line == "BEGIN:VEVENT":
            cur, depth = {"exdates": set()}, 1
            continue
        if cur is None:
            continue
        if line.startswith("BEGIN:"):
            depth += 1                 # VALARM внутри события — пропускаем
            continue
        if line.startswith("END:"):
            depth -= 1
            if line == "END:VEVENT" and depth <= 0:
                if cur.get("start"):
                    out.append(cur)
                cur = None
            continue
        if depth != 1 or ":" not in line:
            continue
        head, value = line.split(":", 1)
        name, *ps = head.split(";")
        params = dict(p.split("=", 1) for p in ps if "=" in p)
        name = name.upper()
        try:
            if name == "DTSTART":
                cur["start"], cur["all_day"] = parse_dt(value, params)
            elif name == "DTEND":
                cur["end"], _ = parse_dt(value, params)
            elif name == "DURATION":
                m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", value.strip())
                if m:
                    cur["duration"] = timedelta(days=int(m.group(1) or 0), hours=int(m.group(2) or 0),
                                                minutes=int(m.group(3) or 0))
            elif name == "SUMMARY":
                cur["summary"] = unescape(value)[:200]
            elif name == "LOCATION":
                cur["location"] = unescape(value)[:200]
            elif name == "UID":
                cur["uid"] = value.strip()[:200]
            elif name == "RRULE":
                cur["rrule"] = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
            elif name == "EXDATE":
                for v in value.split(","):
                    cur["exdates"].add(parse_dt(v, params)[0])
            elif name == "STATUS":
                cur["cancelled"] = value.strip().upper() == "CANCELLED"
            elif name == "RECURRENCE-ID":
                cur["recurrence_id"] = parse_dt(value, params)[0]
        except ValueError:
            continue
    for e in out:
        e.setdefault("uid", f"{e['start']:%Y%m%dT%H%M}{e.get('summary', '')}")
        if "end" not in e:
            e["end"] = e["start"] + e.get("duration", timedelta(days=1) if e.get("all_day") else timedelta(hours=1))
    return out


def occurrences(e, frm, to):
    """Начала события в [frm, to): само событие или простые повторы."""
    start, length = e["start"], e["end"] - e["start"]
    rr = e.get("rrule")
    if not rr:
        return [start] if start < to and start + length > frm else []
    freq = rr.get("FREQ", "")
    interval = max(1, int(rr.get("INTERVAL", "1") or 1))
    count = int(rr["COUNT"]) if rr.get("COUNT", "").isdigit() else None
    until = None
    if rr.get("UNTIL"):
        try:
            until = parse_dt(rr["UNTIL"], {})[0]
        except ValueError:
            pass
    byday = [DAYS[d[-2:]] for d in rr.get("BYDAY", "").split(",") if d[-2:] in DAYS] if freq == "WEEKLY" else []
    out, n, cur = [], 0, start
    for _ in range(5000):
        cands = [cur] if not byday else [
            (cur - timedelta(days=cur.weekday()) + timedelta(days=d)).replace(hour=start.hour, minute=start.minute)
            for d in sorted(byday)]
        for c in cands:
            if c < start:
                continue
            if (until and c > until) or (count is not None and n >= count) or c >= to:
                return out
            n += 1
            if c + length > frm and c not in e["exdates"]:
                out.append(c)
        if freq == "DAILY":
            cur += timedelta(days=interval)
        elif freq == "WEEKLY":
            cur += timedelta(weeks=interval)
        elif freq == "MONTHLY":
            y, m = divmod(cur.month - 1 + interval, 12)
            try:
                cur = cur.replace(year=cur.year + y, month=m + 1)
            except ValueError:
                return out
        elif freq == "YEARLY":
            try:
                cur = cur.replace(year=cur.year + interval)
            except ValueError:
                return out
        else:
            return out
    return out


def upcoming(extra, frm, to):
    """События в окне [frm, to): [{uid, summary, location, start, end, all_day, calendar}]."""
    res, seen = [], set()
    srcs = sources(extra)
    status["sources"] = len(srcs)
    for path, kind in srcs:
        cal = os.path.basename(os.path.dirname(path)) if kind == "eds" or path.endswith("calendar.ics") \
            else os.path.splitext(os.path.basename(path))[0]
        try:
            texts = read_texts(path, kind)
        except (OSError, sqlite3.Error):
            continue
        evs = [e for t in texts for e in parse_events(t)]
        moved = {(e["uid"], e["recurrence_id"]) for e in evs if e.get("recurrence_id")}
        for e in evs:
            if e.get("cancelled"):
                continue
            for st in occurrences(e, frm, to):
                if not e.get("recurrence_id") and (e["uid"], st) in moved:
                    continue                  # это повторение перенесено отдельной записью
                key = (e["uid"], st)
                if key in seen:
                    continue
                seen.add(key)
                res.append({"uid": e["uid"], "summary": e.get("summary") or L("(без названия)", "(untitled)"),
                            "location": e.get("location", ""), "start": st, "end": st + (e["end"] - e["start"]),
                            "all_day": e.get("all_day", False), "calendar": cal})
    res.sort(key=lambda x: x["start"])
    return res


def _hm(dt):
    return dt.strftime("%H:%M")


def step(conn, cfg, now=None):
    now = now or datetime.now()
    events._lang(conn)
    evs = upcoming(cfg["files"], now - timedelta(hours=12), now + timedelta(hours=36))
    status["events"] = len(evs)
    before = timedelta(minutes=cfg["before"])
    for e in evs:
        if e["all_day"]:
            continue
        key = f"cal:{e['uid']}:{e['start']:%Y%m%dT%H%M}"
        if e["start"] - before <= now < e["start"] and not events.open_problem(conn, key) \
                and not conn.execute("SELECT 1 FROM messages WHERE event_key = ?", (key,)).fetchone():
            mins = max(1, round((e["start"] - now).total_seconds() / 60))
            text = L(f"через {mins} мин · {_hm(e['start'])}–{_hm(e['end'])}",
                     f"in {mins} min · {_hm(e['start'])}–{_hm(e['end'])}") + \
                (f"\n{e['location']}" if e["location"] else "")
            events.emit(conn, "calendar", e["summary"], text, sender=e["calendar"], key=key, urgency=2)
        elif now >= e["end"]:                 # кончилось — карточку можно убрать с доски
            conn.execute("UPDATE messages SET is_read = 1, read_at = ? WHERE event_key = ? AND is_read = 0 "
                         "AND pinned = 0", (catcher.msk_time(), key))
    conn.commit()
    prefs = rules.get_prefs(conn)
    today = now.strftime("%Y-%m-%d")
    if cfg["agenda"] and now.strftime("%H:%M") >= cfg["agenda_time"] and prefs.get("agenda_last") != today:
        todays = [e for e in evs if e["start"].date() == now.date() or (e["all_day"] and e["start"].date() <= now.date() < e["end"].date())]
        rules.set_prefs(conn, {"agenda_last": today})
        conn.commit()
        if todays:
            lines = [(L("весь день", "all day") if e["all_day"] else f"{_hm(e['start'])}–{_hm(e['end'])}") +
                     f"  {e['summary']}" + (f" ({e['location']})" if e["location"] else "") for e in todays]
            events.emit(conn, "calendar", L("План на сегодня", "Today's plan"),
                        L(f"событий: {len(todays)}", f"events: {len(todays)}") + "\n" + "\n".join(lines[:12]),
                        sender=L("календарь", "calendar"), details="\n".join(lines))
    return len(evs)


def start(db_path):
    def loop():
        while True:
            try:
                conn = events.connect(db_path)
                try:
                    cfg = rules.themed(rules.get_prefs(conn))["calendar"]
                    if cfg["enabled"]:
                        was = status["running"]
                        step(conn, cfg)
                        status.update(running=True, error="", checked=time.strftime("%H:%M:%S"))
                        if not was:
                            print(f"Календарь: слежу за событиями ({status['sources']} календарей)", flush=True)
                    elif status["running"]:
                        status.update(running=False)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001
                if status["error"] != str(e)[:300]:
                    print(f"Календарь: ошибка: {e!r}", flush=True)
                status.update(running=False, error=str(e)[:300])
            time.sleep(60)
    threading.Thread(target=loop, name="calendar", daemon=True).start()


def public_status():
    return dict(status)

