#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тематическая колонка «Ресурсы»: диск, память, swap, температура процессора и видеокарты.

Раз в минуту (только чтение): место на дисках (shutil.disk_usage по настоящим файловым
системам из /proc/mounts, на Windows — по буквам дисков) и свои папки из настроек, память и
swap (/proc/meminfo, на Windows — GlobalMemoryStatusEx), температура процессора
(/sys/class/hwmon: coretemp, k10temp, zenpower; или термозона x86_pkg_temp) и видеокарты
NVIDIA (nvidia-smi, если есть). Порог превышен → карточка; стало ниже порога на 3 единицы
(чтобы не мигало) → «починилось». Ключ res:<что>:<где>.

К карточке о заполненном диске прикладывается, сколько занимают образы и контейнеры
(`podman system df`, `docker system df`) — частая причина. Сама программа ничего не удаляет.
"""

import os
import re
import shutil
import subprocess
import threading
import time

import events
import rules
from i18n import L

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0
POLL = 60
HYST = 3                      # на столько ниже порога — «починилось»
REAL_FS = {"ext2", "ext3", "ext4", "btrfs", "xfs", "zfs", "f2fs", "ntfs", "ntfs3", "fuseblk", "vfat", "exfat",
           "jfs", "reiserfs", "bcachefs"}

status = {"running": False, "error": "", "checked": "", "values": {}}


def gb(n):
    return f"{n / 1024 ** 3:.1f}"


def mounts():
    """Точки монтирования настоящих дисков (без snap, tmpfs, overlay и т.п.)."""
    if WINDOWS:
        import string
        return [f"{c}:\\" for c in string.ascii_uppercase if os.path.exists(f"{c}:\\")]
    out, seen = [], set()
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3 or parts[2] not in REAL_FS:
                    continue
                dev, mnt = parts[0], parts[1].replace("\\040", " ")
                if mnt.startswith(("/snap/", "/boot/efi", "/var/snap/")) or dev in seen:
                    continue
                seen.add(dev)
                out.append(mnt)
    except OSError:
        out = ["/"]
    return out


def disk_usage(paths):
    """{точка: (процент занятого, свободно байт, всего байт)}; одинаковые диски — один раз."""
    res, devs = {}, set()
    for p in paths:
        try:
            dev = os.stat(p).st_dev
            if dev in devs:
                continue
            devs.add(dev)
            u = shutil.disk_usage(p)
        except OSError:
            continue
        if u.total:
            res[p] = (round(100 * (u.total - u.free) / u.total), u.free, u.total)
    return res


def memory():
    """(процент занятой памяти, процент занятого swap, всего памяти байт)."""
    if WINDOWS:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.dwMemoryLoad, None, m.ullTotalPhys
    info = {}
    with open("/proc/meminfo", encoding="utf-8") as f:
        for line in f:
            k, _, v = line.partition(":")
            info[k] = int(v.split()[0]) * 1024 if v.split() else 0
    total, avail = info.get("MemTotal", 0), info.get("MemAvailable", 0)
    st, sf = info.get("SwapTotal", 0), info.get("SwapFree", 0)
    mem = round(100 * (total - avail) / total) if total else 0
    swap = round(100 * (st - sf) / st) if st else None
    return mem, swap, total


def cpu_temp():
    """Температура процессора, °C, или None."""
    if WINDOWS:
        return None
    best = None
    for hw in sorted(os.listdir("/sys/class/hwmon")) if os.path.isdir("/sys/class/hwmon") else []:
        base = os.path.join("/sys/class/hwmon", hw)
        try:
            name = open(os.path.join(base, "name"), encoding="utf-8").read().strip()
        except OSError:
            continue
        if name not in ("coretemp", "k10temp", "zenpower", "cpu_thermal"):
            continue
        for f in os.listdir(base):
            if re.match(r"temp\d+_input$", f):
                try:
                    t = int(open(os.path.join(base, f)).read()) / 1000
                    best = t if best is None else max(best, t)
                except (OSError, ValueError):
                    pass
    if best is None:
        for z in sorted(os.listdir("/sys/class/thermal")) if os.path.isdir("/sys/class/thermal") else []:
            try:
                if open(f"/sys/class/thermal/{z}/type").read().strip() in ("x86_pkg_temp", "cpu-thermal"):
                    best = int(open(f"/sys/class/thermal/{z}/temp").read()) / 1000
            except (OSError, ValueError):
                pass
    return round(best) if best is not None else None


def gpu_temps():
    """[(имя, °C, занято памяти МБ, всего МБ)] видеокарт NVIDIA или []."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "--query-gpu=name,temperature.gpu,memory.used,memory.total",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                           creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return []
    out = []
    for line in r.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 4:
            try:
                out.append((parts[0], int(parts[1]), int(parts[2]), int(parts[3])))
            except ValueError:
                pass
    return out


def containers_df():
    """Сколько занимают образы и контейнеры — к карточке о заполненном диске."""
    parts = []
    import containers
    for eng in ("podman", "docker"):
        if not containers.exe(eng):
            continue
        try:
            r = containers.run_engine(eng, ["system", "df"], capture_output=True, text=True, timeout=20)
            if r.returncode == 0 and r.stdout.strip():
                parts.append(f"$ {eng} system df\n{r.stdout.strip()}")
        except (OSError, subprocess.SubprocessError):
            pass
    return "\n\n".join(parts)


class Checker:
    """Одна проверка: значения → карточки и «починилось». Состояние — открытые ключи в базе."""

    def __init__(self, conn, cfg):
        self.conn, self.cfg = conn, cfg
        self.open = events.open_keys(conn, "res:")
        self.seen = set()

    def over(self, key, value, limit, chat, text, sender, details=""):
        """value ≥ limit — проблема (одна карточка, пока не отпустит); ниже limit − HYST — починилось."""
        self.seen.add(key)
        if value >= limit:
            if key not in self.open:
                events.emit(self.conn, "resources", chat, text, sender=sender,
                            details=details() if callable(details) else details, key=key, urgency=2)
                self.open.add(key)
        elif value <= limit - HYST and key in self.open:
            events.resolve(self.conn, key)
            self.open.discard(key)

    def run(self):
        c = self.cfg
        vals = {}
        paths = mounts() + [p for p in c["paths"] if os.path.isdir(os.path.expanduser(p))]
        for mnt, (pct, free, total) in disk_usage([os.path.expanduser(p) for p in paths]).items():
            vals[f"disk {mnt}"] = f"{pct}%"
            self.over(f"res:disk:{mnt}", pct, c["disk_pct"], mnt,
                      L(f"диск заполнен на {pct}% (свободно {gb(free)} из {gb(total)} ГБ)",
                        f"disk is {pct}% full ({gb(free)} of {gb(total)} GB free)"),
                      L("диск", "disk"), details=containers_df)
        try:
            mem, swap, total = memory()
            vals["memory"] = f"{mem}%"
            self.over("res:mem", mem, c["mem_pct"], L("Память", "Memory"),
                      L(f"память занята на {mem}% из {gb(total)} ГБ", f"memory is {mem}% used of {gb(total)} GB"),
                      L("память", "memory"))
            if swap is not None:
                vals["swap"] = f"{swap}%"
                self.over("res:swap", swap, c["swap_pct"], "Swap",
                          L(f"swap занят на {swap}%", f"swap is {swap}% used"), L("память", "memory"))
        except (OSError, ValueError):
            pass
        t = cpu_temp()
        if t is not None:
            vals["cpu"] = f"{t}°C"
            self.over("res:cpu", t, c["cpu_temp"], L("Процессор", "CPU"),
                      L(f"процессор нагрелся до {t} °C", f"CPU is at {t} °C"), L("температура", "temperature"))
        for i, (name, temp, used, total) in enumerate(gpu_temps()):
            vals[f"gpu{i}"] = f"{temp}°C"
            self.over(f"res:gpu:{i}", temp, c["gpu_temp"], name,
                      L(f"видеокарта нагрелась до {temp} °C (память {used} из {total} МБ)",
                        f"GPU is at {temp} °C (memory {used} of {total} MB)"), L("температура", "temperature"))
        for key in self.open - self.seen:          # диск отключили — проблемы с ним больше нет
            events.resolve(self.conn, key)
        return vals


def start(db_path):
    def loop():
        while True:
            try:
                conn = events.connect(db_path)
                try:
                    cfg = rules.themed(rules.get_prefs(conn))["resources"]
                    if cfg["enabled"]:
                        events._lang(conn)
                        was = status["running"]
                        vals = Checker(conn, cfg).run()
                        status.update(running=True, error="", checked=time.strftime("%H:%M:%S"), values=vals)
                        if not was:
                            print("Ресурсы: слежу за диском, памятью и температурой", flush=True)
                    elif status["running"]:
                        status.update(running=False, values={})
                        print("Ресурсы: слежка выключена", flush=True)
                finally:
                    conn.close()
            except Exception as e:  # noqa: BLE001 — одна неудачная проверка не роняет поток
                if status["error"] != str(e)[:300]:
                    print(f"Ресурсы: ошибка проверки: {e!r}", flush=True)
                status.update(running=False, error=str(e)[:300])
            time.sleep(POLL)
    threading.Thread(target=loop, name="resources", daemon=True).start()


def public_status():
    return dict(status)
