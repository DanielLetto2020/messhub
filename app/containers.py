#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тематическая колонка «Контейнеры»: Docker и Podman (Linux, Windows и macOS).

Слушаем поток событий движка — `podman events --format json` / `docker events
--format '{{json .}}'` (только чтение: ничего не запускаем, не останавливаем и не
удаляем) — и кладём на доску только плохое:
  - контейнер вышел с кодом не 0 (кроме ручной остановки: stop/kill за 15 с до выхода
    или сразу после него);
  - код 137 и OOMKilled — «не хватило памяти»;
  - healthcheck стал unhealthy;
  - перезапуски по кругу видны по счётчику «3-й раз за 10 минут».
Запуск и обычную остановку можно включить в настройках. Когда контейнер снова работает
(20 с после старта без нового падения, или healthcheck снова healthy), карточка
получает «починилось» (events.resolve). Хвост лога — `logs --tail N`.

Ключ события: container:<движок>:<имя>. Rootless podman видит только контейнеры этого
пользователя; docker — если у пользователя есть доступ к сокету (группа docker).

Где движок: у программы из Finder, автозапуска или службы PATH урезан (на Mac — /usr/bin:/bin:/usr/sbin:/sbin),
а Docker Desktop, Homebrew, OrbStack, Colima и snap кладут docker и podman в свои папки — exe() ищет и там,
а env() добавляет их к PATH (docker зовёт оттуда свои помощники).
"""

import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

import events
import rules

ENGINES = ("podman", "docker")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0       # CREATE_NO_WINDOW: без мелькающих консолей на Windows
STOP_WINDOW = 15            # stop/kill за столько секунд до выхода — остановили руками
AFTER_DIE = 3               # столько ждём после выхода: docker шлёт stop уже после die
HEALTHY_AFTER = 20          # после старта столько секунд без падения — «починилось»
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

status = {e: {"found": False, "running": False, "error": "", "events": 0, "path": ""} for e in ENGINES}
_procs = {}
_lock = threading.Lock()


def _t(conn):
    return rules.themed(rules.get_prefs(conn))["containers"]


def parse(engine, line):
    """Строка потока событий → {name, action, code, health, project, image} или None."""
    try:
        e = json.loads(line)
    except ValueError:
        return None
    if not isinstance(e, dict):
        return None
    if engine == "podman" or "Status" in e:
        if e.get("Type", "container") != "container":
            return None
        attrs = e.get("Attributes") or {}
        action = str(e.get("Status") or "")
        health = str(e.get("health_status") or "")
        return {"name": str(e.get("Name") or "")[:120], "action": {"died": "die", "health_status": "health"}.get(action, action),
                "code": int(e.get("ContainerExitCode") or 0), "health": health,
                "project": str(attrs.get("com.docker.compose.project") or "")[:80], "image": str(e.get("Image") or "")}
    if e.get("Type") != "container":
        return None
    attrs = (e.get("Actor") or {}).get("Attributes") or {}
    action = str(e.get("Action") or e.get("status") or "")
    health = ""
    if action.startswith("health_status"):
        health = action.split(":", 1)[-1].strip()
        action = "health"
    try:
        code = int(attrs.get("exitCode") or 0)
    except ValueError:
        code = 0
    return {"name": str(attrs.get("name") or "")[:120], "action": action.split(":")[0], "code": code,
            "health": health, "project": str(attrs.get("com.docker.compose.project") or "")[:80],
            "image": str(attrs.get("image") or e.get("from") or "")}


def _extra_dirs():
    """Обычные места установки docker и podman, которых может не быть в PATH программы."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return ["/usr/local/bin", "/opt/homebrew/bin", os.path.join(home, ".docker", "bin"),
                "/Applications/Docker.app/Contents/Resources/bin", os.path.join(home, ".orbstack", "bin"),
                os.path.join(home, ".rd", "bin"), "/opt/podman/bin", "/opt/local/bin"]
    if os.name == "nt":
        pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
        return [os.path.join(pf, "Docker", "Docker", "resources", "bin"), os.path.join(pf, "RedHat", "Podman")]
    return ["/usr/local/bin", "/snap/bin", os.path.join(home, ".local", "bin"), os.path.join(home, "bin")]


def exe(engine):
    """Полный путь к docker или podman: из PATH, иначе из обычных мест установки. None — не установлен."""
    return shutil.which(engine) or shutil.which(engine, path=os.pathsep.join(_extra_dirs()))


def env():
    """Окружение для вызовов движка: к PATH добавлены места установки."""
    e = dict(os.environ)
    have = [p for p in (e.get("PATH") or "").split(os.pathsep) if p]
    e["PATH"] = os.pathsep.join(have + [d for d in _extra_dirs() if d not in have])
    return e


def run_engine(engine, args, **kw):
    """Короткий вызов движка (logs, inspect, system df) — полным путём и с полным PATH."""
    return subprocess.run([exe(engine) or engine, *args], env=env(), creationflags=NO_WINDOW, **kw)


def logs_tail(engine, name, n):
    """Последние n строк лога контейнера (без цветовых кодов, строка — до 300 символов)."""
    if n <= 0:
        return ""
    try:
        r = run_engine(engine, ["logs", "--tail", str(n), name], capture_output=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return ""
    raw = (r.stdout or b"") + (b"\n" + r.stderr if r.stderr else b"")
    lines = [_ANSI.sub("", ln)[:300] for ln in raw.decode("utf-8", "replace").splitlines() if ln.strip()]
    return "\n".join(lines[-n:])


def oom_killed(engine, name):
    try:
        r = run_engine(engine, ["inspect", "--format", "{{.State.OOMKilled}}", name],
                       capture_output=True, text=True, timeout=8)
        return r.stdout.strip().lower() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


class Watcher:
    """Разбор событий одного движка; решения о карточках — в handle()."""

    def __init__(self, db_path, engine):
        self.db, self.engine = db_path, engine
        self.stops, self.ooms, self.starts, self.dies = {}, {}, {}, {}
        self.health = {}
        self._cfg_cache = (0.0, None)

    def key(self, name):
        return f"container:{self.engine}:{name}"

    def _cfg(self):
        """Настройки колонки; события healthcheck идут часто — перечитываем не чаще раза в 5 с."""
        t, cfg = self._cfg_cache
        if cfg is None or time.time() - t > 5:
            conn = events.connect(self.db)
            try:
                cfg = _t(conn)
            finally:
                conn.close()
            self._cfg_cache = (time.time(), cfg)
        return cfg

    def ignored(self, name, cfg):
        return any(fnmatch.fnmatch(name, p) for p in cfg["ignore"])

    def handle(self, ev, now=None, later=None):
        """later(delay, fn) — отложить решение (в тестах вызывается сразу)."""
        now = now or time.time()
        later = later or (lambda d, fn: threading.Timer(d, fn).start())
        name = ev["name"]
        if not name:
            return
        cfg = self._cfg()
        if self.ignored(name, cfg):
            return
        act = ev["action"]
        if act in ("stop", "kill"):
            self.stops[name] = now
        elif act == "oom":
            self.ooms[name] = now
        elif act == "start":
            self.starts[name] = now
            if cfg["startstop"]:
                self.card(name, ev, "start")
            later(HEALTHY_AFTER, lambda: self.check_healthy(name, now))
        elif act == "die":
            self.dies[name] = now
            later(AFTER_DIE, lambda: self.decide_die(name, ev, now))
        elif act == "health" and ev["health"]:
            prev = self.health.get(name)
            self.health[name] = ev["health"]
            if ev["health"] == "unhealthy" and prev != "unhealthy":
                self.card(name, ev, "unhealthy")
            elif ev["health"] == "healthy" and prev == "unhealthy":
                self.resolve(name)

    def decide_die(self, name, ev, t_die):
        stop = self.stops.get(name, 0)
        manual = t_die - STOP_WINDOW <= stop <= t_die + AFTER_DIE + 1
        cfg = self._cfg()
        if manual or ev["code"] == 0:
            if cfg["startstop"]:
                self.card(name, ev, "stop")
            return
        oom = ev["code"] == 137 and (self.ooms.get(name, 0) >= t_die - 5 or oom_killed(self.engine, name))
        self.card(name, ev, "oom" if oom else "die", lines=cfg["log_lines"])

    def check_healthy(self, name, t_start):
        if self.dies.get(name, 0) > t_start or self.health.get(name) == "unhealthy":
            return
        self.resolve(name)

    def resolve(self, name):
        conn = events.connect(self.db)
        try:
            events.resolve(conn, self.key(name))
        finally:
            conn.close()

    def card(self, name, ev, kind, lines=0):
        from i18n import L
        conn = events.connect(self.db)
        try:
            events._lang(conn)
            key = self.key(name)
            sender = ev["project"] or self.engine
            if kind in ("start", "stop"):
                text = L("запущен", "started") if kind == "start" else L("остановлен", "stopped")
                events.emit(conn, "containers", name, text, sender=sender)
                return
            n = events.recent_count(conn, key, 10) + 1
            if kind == "unhealthy":
                text = L("healthcheck: нездоров (unhealthy)", "healthcheck: unhealthy")
            elif kind == "oom":
                text = L(f"упал: не хватило памяти (OOM, код {ev['code']})", f"crashed: out of memory (OOM, code {ev['code']})")
            else:
                text = L(f"упал с кодом {ev['code']}", f"crashed with code {ev['code']}")
            if n > 1:
                text += L(f" · {n}-й раз за 10 минут", f" · {n} times in 10 minutes")
            details = logs_tail(self.engine, name, lines) if lines else ""
            events.emit(conn, "containers", name, text, sender=sender, details=details, key=key, urgency=2)
        finally:
            conn.close()


def human_error(engine, err):
    """Частые причины, почему слушать события нельзя, — понятными словами."""
    from i18n import L
    e = err.lower()
    if "permission denied" in e:
        return L(f"нет доступа к {engine}: добавь пользователя в группу {engine} и перезайди в систему",
                 f"no access to {engine}: add your user to the {engine} group and log in again")
    if "cannot connect" in e or "is the docker daemon running" in e or "connection refused" in e \
            or "no such file or directory" in e:
        return L(f"служба {engine} не запущена — как запустится, начну слушать",
                 f"the {engine} service is not running; will listen once it starts")
    return err[:300]


def _reader(db_path, engine, stop):
    fmt = "json" if engine == "podman" else "{{json .}}"
    w = Watcher(db_path, engine)
    while not stop.is_set():
        st = status[engine]
        try:
            p = subprocess.Popen([exe(engine) or engine, "events", "--format", fmt, "--filter", "type=container"],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                 errors="replace", bufsize=1, creationflags=NO_WINDOW, env=env())
        except OSError as e:
            st.update(running=False, error=str(e))
            stop.wait(60)
            continue
        with _lock:
            _procs[engine] = p
        st.update(running=True, error="")
        print(f"Контейнеры: слушаю события {engine}", flush=True)
        for line in p.stdout:
            if stop.is_set():
                break
            ev = parse(engine, line)
            if ev:
                st["events"] += 1
                try:
                    w.handle(ev)
                except Exception as e:  # noqa: BLE001 — одно событие не должно ронять слушателя
                    print(f"Контейнеры: ошибка разбора события {engine}: {e!r}", flush=True)
        err = (p.stderr.read() or "").strip().splitlines()
        p.wait()
        st["running"] = False
        if stop.is_set():
            break
        raw = (err[-1] if err else f"exit {p.returncode}")[:300]
        conn = events.connect(db_path)
        try:
            events._lang(conn)
        finally:
            conn.close()
        st["error"] = human_error(engine, raw)
        print(f"Контейнеры: {engine} events завершился: {raw}", flush=True)
        stop.wait(60)            # движок не запущен или нет доступа — попробуем позже


def start(db_path):
    """Фоновый поток: раз в 10 с сверяет настройку и запускает/гасит слушателей движков."""
    stops = {}

    def loop():
        while True:
            try:
                conn = events.connect(db_path)
                try:
                    on = _t(conn)["enabled"]
                finally:
                    conn.close()
            except Exception:  # noqa: BLE001 — база занята: подождём
                on = None
            for eng in ENGINES:
                path = exe(eng)
                status[eng].update(found=bool(path), path=path or "")
                if on is None:
                    continue
                running = eng in stops and not stops[eng].is_set()
                if on and status[eng]["found"] and not running:
                    stops[eng] = threading.Event()
                    threading.Thread(target=_reader, args=(db_path, eng, stops[eng]),
                                     name=f"containers-{eng}", daemon=True).start()
                elif not on and running:
                    stops[eng].set()
                    with _lock:
                        p = _procs.pop(eng, None)
                    if p:
                        try:
                            p.terminate()
                        except OSError:
                            pass
                    status[eng].update(running=False, error="")
                    print(f"Контейнеры: слушатель {eng} выключен", flush=True)
            time.sleep(10)
    threading.Thread(target=loop, name="containers", daemon=True).start()


def public_status():
    return {e: dict(s) for e, s in status.items()}
