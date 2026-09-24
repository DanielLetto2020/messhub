#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тематическая колонка «Службы»: упавшие службы системы.

Linux (systemd): раз в 30 с `systemctl [--user] list-units --state=failed` — системные
службы и службы пользователя. Новая упавшая служба → карточка (что случилось — из
`systemctl show`, хвост — из journalctl, если журнал доступен); служба больше не failed
(перезапустилась, reset-failed) → «починилось». Ключ unit:<system|user>:<имя>. Уже
показанная и не починившаяся служба после перезапуска программы второй раз не приходит.

Windows: раз в 60 с журнал событий System, источник Service Control Manager: служба
завершилась неожиданно (7031, 7034), с ошибкой (7023, 7024) или не запустилась (7000).
Первый запуск только запоминает последнюю запись — старые события не тащим. Если в
событии есть имя службы, раз в минуту спрашиваем `sc query`; снова RUNNING — «починилось».
Ключ svc:win:<служба>. Всё — только чтение.
"""

import os
import re
import shutil
import subprocess
import threading
import time
import xml.etree.ElementTree as ET

import events
import rules

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0
POLL = 60 if WINDOWS else 30
WIN_IDS = (7000, 7023, 7024, 7031, 7034)
_NS = {"e": "http://schemas.microsoft.com/win/2004/08/events/event"}

status = {"found": False, "running": False, "error": "", "failed": 0, "checked": ""}


def _run(args, timeout=10):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, creationflags=NO_WINDOW)


# ── Linux ───────────────────────────────────────────────────────────────────

def failed_units(scope):
    """Имена упавших служб: scope — system | user."""
    args = ["systemctl"] + (["--user"] if scope == "user" else []) + \
        ["list-units", "--state=failed", "--no-legend", "--plain", "--no-pager", "--full"]
    r = _run(args)
    if r.returncode not in (0, 1):
        raise OSError((r.stderr or r.stdout or f"exit {r.returncode}").strip()[:300])
    return parse_failed(r.stdout)


def parse_failed(out):
    names = []
    for line in out.splitlines():
        parts = line.replace("●", " ").split()
        if parts and "." in parts[0]:
            names.append(parts[0])
    return names


def unit_info(scope, unit):
    """(описание, итог) из systemctl show."""
    args = ["systemctl"] + (["--user"] if scope == "user" else []) + \
        ["show", unit, "-p", "Description,Result,ExecMainStatus", "--no-pager"]
    try:
        r = _run(args)
    except (OSError, subprocess.SubprocessError):
        return "", "", ""
    kv = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
    return kv.get("Description", ""), kv.get("Result", ""), kv.get("ExecMainStatus", "")


def journal_tail(scope, unit, n):
    if n <= 0 or not shutil.which("journalctl"):
        return ""
    args = ["journalctl"] + (["--user"] if scope == "user" else []) + \
        ["-u", unit, "-n", str(n), "--no-pager", "-o", "short-iso"]
    try:
        r = _run(args, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    lines = [ln[:300] for ln in r.stdout.splitlines() if ln.strip() and not ln.startswith("-- ")]
    return "\n".join(lines[-n:])


def linux_step(conn, cfg):
    from i18n import L
    events._lang(conn)
    total = 0
    for scope in ("system", "user"):
        if not cfg[scope]:
            continue
        prefix = f"unit:{scope}:"
        now_failed = set(failed_units(scope))
        total += len(now_failed)
        for unit in sorted(now_failed):
            key = prefix + unit
            if events.open_problem(conn, key):
                continue                         # уже показана и ещё не починилась
            desc, result, code = unit_info(scope, unit)
            why = {"exit-code": L(f"завершилась с кодом {code}", f"exited with code {code}"),
                   "signal": L("убита сигналом", "killed by a signal"),
                   "timeout": L("не уложилась во время", "timed out"),
                   "core-dump": L("упала (core dump)", "crashed (core dump)"),
                   "oom-kill": L("не хватило памяти (OOM)", "out of memory (OOM)"),
                   "start-limit-hit": L("слишком часто перезапускалась", "restarted too often")}.get(
                       result, L("упала", "failed") + (f" ({result})" if result and result != "success" else ""))
            text = L("служба ", "service ") + why + (f"\n{desc}" if desc and desc != unit else "")
            sender = L("системная служба", "system service") if scope == "system" else L("служба пользователя", "user service")
            events.emit(conn, "services", unit, text, sender=sender,
                        details=journal_tail(scope, unit, cfg["log_lines"]), key=key, urgency=2)
        for key in events.open_keys(conn, prefix):
            if key[len(prefix):] not in now_failed:
                events.resolve(conn, key)
    return total


# ── Windows ─────────────────────────────────────────────────────────────────

def parse_win_events(xml_text):
    """Вывод wevtutil qe /f:xml (события подряд, без корня) → [{id, time, event, name, service, param2}]."""
    out = []
    # вывод системной утилиты, но на всякий случай: без DOCTYPE/ENTITY (защита от «бомб» сущностей)
    if not xml_text.strip() or "<!DOCTYPE" in xml_text or "<!ENTITY" in xml_text:
        return out
    try:
        root = ET.fromstring("<Events>" + xml_text + "</Events>")
    except ET.ParseError:
        return out
    for ev in root.findall("e:Event", _NS):
        sysn = ev.find("e:System", _NS)
        if sysn is None:
            continue
        try:
            rid = int(sysn.findtext("e:EventRecordID", "0", _NS))
            eid = int(sysn.findtext("e:EventID", "0", _NS))
        except ValueError:
            continue
        tc = sysn.find("e:TimeCreated", _NS)
        data = {d.get("Name") or f"p{i}": (d.text or "") for i, d in enumerate(ev.findall("e:EventData/e:Data", _NS))}
        binary = ev.findtext("e:EventData/e:Binary", "", _NS) or ""
        out.append({"id": rid, "event": eid, "time": tc.get("SystemTime", "") if tc is not None else "",
                    "name": data.get("param1", ""), "param2": data.get("param2", ""),
                    "service": service_from_binary(binary)})
    return out


def service_from_binary(hexstr):
    """В событиях 7031/7034 в Binary лежит имя службы (UTF-16LE). Не вышло — ''."""
    try:
        name = bytes.fromhex(hexstr.strip()).decode("utf-16-le").strip("\x00").strip()
    except (ValueError, UnicodeDecodeError):
        return ""
    return name if re.match(r"^[\w.\-$ ]{1,80}$", name) else ""


def win_events(count=40):
    q = "*[System[Provider[@Name='Service Control Manager'] and (" + \
        " or ".join(f"EventID={i}" for i in WIN_IDS) + ")]]"
    r = _run(["wevtutil", "qe", "System", f"/q:{q}", "/rd:true", f"/c:{count}", "/f:xml"], timeout=20)
    if r.returncode:
        raise OSError((r.stderr or f"exit {r.returncode}").strip()[:300])
    return parse_win_events(r.stdout)


def win_running(service):
    try:
        r = _run(["sc", "query", service])
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r":\s*(\d)\s+[A-Z_]+", r.stdout.split("STATE", 1)[-1]) if "STATE" in r.stdout else None
    return (m.group(1) == "4") if m else None


def windows_step(conn, cfg):
    from i18n import L
    events._lang(conn)
    stored = str(rules.get_prefs(conn).get("services_win_last") or "")
    first = not stored.isdigit()            # первый запуск: только запомнить, старые события не тащим
    last = 0 if first else int(stored)
    evs = sorted(win_events(), key=lambda e: e["id"])
    top = max([last] + [e["id"] for e in evs])
    if not first:
        for e in evs:
            if e["id"] <= last:
                continue
            what = {7031: L("завершилась неожиданно", "terminated unexpectedly"),
                    7034: L("завершилась неожиданно", "terminated unexpectedly"),
                    7023: L("завершилась с ошибкой", "terminated with an error"),
                    7024: L("завершилась с ошибкой службы", "terminated with a service error"),
                    7000: L("не запустилась", "failed to start")}[e["event"]]
            extra = e["param2"] if e["event"] in (7000, 7023) else ""
            name = e["name"] or e["service"] or "?"
            key = "svc:win:" + (e["service"] or name)
            events.emit(conn, "services", name, L("служба ", "service ") + what + (f"\n{extra}" if extra else ""),
                        sender=L("служба Windows", "Windows service"), key=key, urgency=2)
    if first or top != last:
        rules.set_prefs(conn, {"services_win_last": str(top)})
        conn.commit()
    for key in events.open_keys(conn, "svc:win:"):
        svc = key[len("svc:win:"):]
        if re.match(r"^[\w.\-$]{1,80}$", svc) and win_running(svc):
            events.resolve(conn, key)
    return 0


# ── поток ───────────────────────────────────────────────────────────────────

def start(db_path):
    """Фоновый поток: пока колонка включена — проверка раз в POLL секунд."""
    def loop():
        while True:
            try:
                conn = events.connect(db_path)
                try:
                    cfg = rules.themed(rules.get_prefs(conn))["services"]
                    status["found"] = bool(shutil.which("wevtutil" if WINDOWS else "systemctl"))
                    if cfg["enabled"] and status["found"]:
                        was = status["running"]
                        status["failed"] = (windows_step if WINDOWS else linux_step)(conn, cfg)
                        status.update(running=True, error="", checked=time.strftime("%H:%M:%S"))
                        if not was:
                            print("Службы: слежу за упавшими службами", flush=True)
                    elif status["running"]:
                        status.update(running=False, error="")
                        print("Службы: слежка выключена", flush=True)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001 — systemctl/wevtutil недоступны, база занята
                if status["error"] != str(e)[:300]:
                    print(f"Службы: ошибка проверки: {e}", flush=True)
                status.update(running=False, error=str(e)[:300])
            time.sleep(POLL)
    threading.Thread(target=loop, name="services", daemon=True).start()


def public_status():
    return dict(status, platform="windows" if WINDOWS else "linux")
