#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ассистент: беседа с моделью на этом компьютере по базе сообщений (окно /assistant).

Модель — только локальная: Ollama (http://127.0.0.1:11434) или LM Studio (OpenAI-совместимый
сервер, http://127.0.0.1:1234). Адрес в домашней сети — если это явно разрешить; облачные адреса
не принимаются (rules.ai_url_ok). Сообщения не уходят с компьютера.

Модели: список установленных (Ollama /api/tags, LM Studio /api/v0/models или /v1/models),
каталог для скачивания в Ollama (свой, с размерами; любое имя из ollama.com/library или
hf.co/… — тоже можно) — /api/pull с прогрессом и отменой, удаление — /api/delete. Для LM Studio
скачивание — в самой программе; если есть её команда lms, сервер можно запустить отсюда.

Беседы (таблицы ai_sessions, ai_messages): у каждой свои настройки — модель, температура,
размер контекста, длина ответа, свой системный промпт и выборка сообщений (период, источники,
сколько сообщений, брать ли логи и прочитанное). Ответ на вопрос:
  1. выборка: сообщения за период (слова «сегодня», «вчера», «за неделю» в вопросе сужают его),
     по источникам; самые подходящие — по умному поиску (векторы rag.py, если включён) или по
     словам вопроса, плюс самые свежие; сколько влезет в контекст;
  2. в модель — системный промпт, сводка (сколько сообщений, откуда), сами сообщения строками
     «#id · дата · источник / чат / кто: текст», история беседы и вопрос;
  3. ответ идёт потоком (NDJSON: context → token… → done), номера #id в ответе — ссылки на окно
     сообщения. Прерванный ответ сохраняется как есть.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import catcher
import i18n
import rules
from i18n import L

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0
PERIODS = {"1d": 1, "2d": 2, "7d": 7, "30d": 30, "all": 0}
CTX_SIZES = (2048, 4096, 8192, 16384, 32768, 65536, 131072)
IT_SOURCES = ("containers", "services", "commands", "resources", "logwatch")

# каталог для скачивания в Ollama: имя, размер, для кого (размеры — примерно, как у Q4)
CATALOG = (
    {"name": "qwen3:4b", "gb": 2.6, "ru": True, "about": ("Быстрая и лёгкая, хорошо понимает русский. Для слабых компьютеров.",
                                                          "Fast and light, good with Russian. For modest computers.")},
    {"name": "qwen3:8b", "gb": 5.2, "ru": True, "about": ("Хороший баланс качества и скорости, хорошо по-русски. Рекомендуем для 8 ГБ видеопамяти.",
                                                          "A good balance of quality and speed, good with Russian. Recommended for 8 GB of VRAM.")},
    {"name": "qwen3:14b", "gb": 9.3, "ru": True, "about": ("Умнее, но нужна видеокарта на 12 ГБ и больше.",
                                                           "Smarter, needs a 12 GB+ graphics card.")},
    {"name": "gemma3:4b", "gb": 3.3, "ru": True, "about": ("Лёгкая модель Google, понимает русский.", "A light Google model, understands Russian.")},
    {"name": "gemma3:12b", "gb": 8.1, "ru": True, "about": ("Модель Google покрупнее: аккуратные сводки.", "A bigger Google model: tidy summaries.")},
    {"name": "llama3.1:8b", "gb": 4.9, "ru": False, "about": ("Популярная модель Meta, лучше всего по-английски.",
                                                             "A popular Meta model, best in English.")},
    {"name": "llama3.2:3b", "gb": 2.0, "ru": False, "about": ("Маленькая и быстрая модель Meta.", "A small and fast Meta model.")},
    {"name": "mistral-nemo", "gb": 7.1, "ru": True, "about": ("Mistral с большим контекстом, неплохо по-русски.",
                                                             "Mistral with a long context, decent in Russian.")},
    {"name": "phi4-mini", "gb": 2.5, "ru": False, "about": ("Компактная модель Microsoft.", "A compact Microsoft model.")},
    {"name": "gpt-oss:20b", "gb": 14.0, "ru": True, "about": ("Открытая модель OpenAI: сильная, но нужна видеокарта на 16 ГБ.",
                                                             "OpenAI's open model: strong, needs a 16 GB graphics card.")},
    {"name": "hf.co/mradermacher/T-lite-it-1.0-GGUF:Q4_K_M", "gb": 4.7, "ru": True,
     "about": ("T-lite: русскоязычная модель на основе Qwen 2.5 7B.", "T-lite: a Russian-first model based on Qwen 2.5 7B.")},
)

pull = {"model": "", "status": "", "completed": 0, "total": 0, "error": "", "done": True, "cancel": False}
_pull_lock = threading.Lock()


# ── HTTP к модели ───────────────────────────────────────────────────────────

def _check(url, allow_lan=False):
    if not rules.ai_url_ok(url, allow_lan):
        raise ValueError(L("Адрес модели — только на этом компьютере", "The model address must be on this computer"))


def _req(base, path, body=None, timeout=10, method=None, allow_lan=False):
    _check(base, allow_lan)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _json(base, path, body=None, timeout=10, method=None, allow_lan=False):
    with _req(base, path, body, timeout, method, allow_lan) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def hardware():
    """Видеопамять NVIDIA и оперативная память, ГБ — чтобы подсказать, какая модель поместится."""
    vram = 0.0
    exe = shutil.which("nvidia-smi")
    if exe:
        try:
            r = subprocess.run([exe, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW)
            vram = max((int(x) for x in r.stdout.split() if x.isdigit()), default=0) / 1024
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    ram = 0.0
    try:
        if WINDOWS:
            import resources
            ram = resources.memory()[2] / 1024 ** 3
        else:
            with open("/proc/meminfo", encoding="utf-8") as f:
                ram = int(f.readline().split()[1]) / 1024 ** 2
    except (OSError, ValueError, IndexError):
        pass
    return {"vram_gb": round(vram, 1), "ram_gb": round(ram, 1)}


def fit(gb, hw):
    """ok — в видеокарту; cpu — только в оперативную память (медленнее); big — может не хватить."""
    if hw["vram_gb"] and gb <= hw["vram_gb"] * 0.92:
        return "ok"
    if hw["ram_gb"] and gb <= hw["ram_gb"] * 0.6:
        return "cpu"
    return "big"


def ollama_status(url):
    out = {"url": url, "ok": False, "version": "", "error": "", "models": [], "running": []}
    try:
        out["version"] = _json(url, "/api/version", timeout=3).get("version", "")
        tags = _json(url, "/api/tags", timeout=5).get("models", [])
        out["models"] = [{"name": m.get("name", ""), "gb": round((m.get("size") or 0) / 1024 ** 3, 1),
                          "params": (m.get("details") or {}).get("parameter_size", ""),
                          "quant": (m.get("details") or {}).get("quantization_level", ""),
                          "family": (m.get("details") or {}).get("family", ""),
                          "embed": _is_embed(m.get("name", ""), m.get("details") or {})} for m in tags]
        try:
            out["running"] = [m.get("name", "") for m in _json(url, "/api/ps", timeout=3).get("models", [])]
        except (OSError, ValueError):
            pass
        out["ok"] = True
    except (OSError, ValueError, urllib.error.URLError) as e:
        out["error"] = _human(e)
    return out


def _is_embed(name, details):
    fam = " ".join([str(details.get("family", ""))] + list(details.get("families") or [])).lower()
    return any(h in (name.lower() + " " + fam) for h in ("embed", "bge", "bert", "minilm", "nomic", "e5-", "gte"))


def lmstudio_status(url):
    out = {"url": url, "ok": False, "error": "", "models": [], "cli": bool(lms_cli())}
    try:
        try:
            data = _json(url, "/api/v0/models", timeout=4).get("data", [])     # подробный список (LM Studio 0.3.6+)
            out["models"] = [{"name": m.get("id", ""), "embed": m.get("type") == "embeddings",
                              "loaded": m.get("state") == "loaded", "ctx": m.get("max_context_length") or 0,
                              "quant": m.get("quantization", ""), "family": m.get("arch", "")} for m in data]
        except (OSError, ValueError, urllib.error.URLError):
            data = _json(url, "/v1/models", timeout=4).get("data", [])
            out["models"] = [{"name": m.get("id", ""), "embed": "embed" in m.get("id", "").lower()} for m in data]
        out["ok"] = True
    except (OSError, ValueError, urllib.error.URLError) as e:
        out["error"] = _human(e)
    return out


def lms_cli():
    exe = shutil.which("lms")
    if not exe:
        cand = os.path.expanduser(os.path.join("~", ".lmstudio", "bin", "lms.exe" if WINDOWS else "lms"))
        exe = cand if os.path.exists(cand) else None
    return exe


def lmstudio_start():
    exe = lms_cli()
    if not exe:
        raise ValueError(L("Не нашёл команду lms — запусти сервер в LM Studio: Developer → Start Server",
                           "The lms command was not found — start the server in LM Studio: Developer → Start Server"))
    r = subprocess.run([exe, "server", "start"], capture_output=True, text=True, timeout=60, creationflags=NO_WINDOW)
    return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr).strip()[-500:]}


def _human(e):
    s = str(getattr(e, "reason", "") or e)
    if "refused" in s.lower() or "10061" in s:
        return L("не запущен (соединение отклонено)", "not running (connection refused)")
    if "timed out" in s.lower():
        return L("не отвечает", "not responding")
    return s[:200]


def _demo_status(ai):
    """Снимки экрана (MESSHUB_THEMED_DEMO=1): выдуманные модели вместо настоящих Ollama и LM Studio."""
    return ({"url": ai["ollama_url"], "ok": True, "version": "0.13.5", "error": "", "running": ["qwen3:8b"],
             "models": [{"name": "qwen3:8b", "gb": 5.2, "params": "8.2B", "quant": "Q4_K_M", "family": "qwen3", "embed": False},
                        {"name": "gemma3:4b", "gb": 3.3, "params": "4.3B", "quant": "Q4_K_M", "family": "gemma3", "embed": False},
                        {"name": "bge-m3", "gb": 1.2, "params": "567M", "quant": "F16", "family": "bert", "embed": True}]},
            {"url": ai["lmstudio_url"], "ok": False, "error": L("не запущен (соединение отклонено)", "not running (connection refused)"),
             "models": [], "cli": True})


def status(conn):
    ai = rules.get_prefs(conn)["ai"]
    hw = hardware()
    if os.environ.get("MESSHUB_THEMED_DEMO") == "1":
        hw = {"vram_gb": 8.0, "ram_gb": 32.0}
        o, lm = _demo_status(ai)
        return {"prefs": ai, "ollama": o, "lmstudio": lm, "hardware": hw,
                "catalog": [dict(c, about=c["about"][i18n.lang() == "en"], fit=fit(c["gb"], hw)) for c in CATALOG],
                "pull": dict(pull), "ctx_sizes": list(CTX_SIZES), "periods": list(PERIODS), "default_system": default_system()}
    return {"prefs": ai, "ollama": ollama_status(ai["ollama_url"]), "lmstudio": lmstudio_status(ai["lmstudio_url"]),
            "hardware": hw, "catalog": [dict(c, about=c["about"][i18n.lang() == "en"], fit=fit(c["gb"], hw)) for c in CATALOG],
            "pull": dict(pull), "ctx_sizes": list(CTX_SIZES), "periods": list(PERIODS),
            "default_system": default_system()}


_caps = {}                   # (провайдер, модель) → умеет ли «размышлять» (qwen3, deepseek-r1, gpt-oss…)


def model_info(conn, provider, model):
    """Сколько контекста умеет модель и «думающая» ли она (если провайдер это говорит)."""
    ai = rules.get_prefs(conn)["ai"]
    if os.environ.get("MESSHUB_THEMED_DEMO") == "1":
        return {"ctx": 40960, "params": "8.2B", "thinking": True}
    try:
        if provider == "ollama":
            d = _json(ai["ollama_url"], "/api/show", {"model": model}, timeout=10, allow_lan=ai["allow_lan"])
            mi = d.get("model_info") or {}
            ctx = next((v for k, v in mi.items() if k.endswith(".context_length")), 0)
            thinking = "thinking" in (d.get("capabilities") or [])
            _caps[(provider, model)] = thinking
            return {"ctx": int(ctx or 0), "params": (d.get("details") or {}).get("parameter_size", ""), "thinking": thinking}
        for m in lmstudio_status(ai["lmstudio_url"])["models"]:
            if m["name"] == model:
                return {"ctx": int(m.get("ctx") or 0), "params": "", "thinking": _guess_thinking(model)}
    except (OSError, ValueError, urllib.error.URLError):
        pass
    return {"ctx": 0, "params": "", "thinking": _guess_thinking(model)}


def _guess_thinking(model):
    return bool(re.search(r"qwen3|deepseek-r1|qwq|gpt-oss|magistral|phi4-reasoning|thinking|reason", model.lower()))


def thinks(ai_prefs, provider, model):
    """Умеет ли модель размышлять (у Ollama — по её описанию, спрашиваем один раз)."""
    key = (provider, model)
    if key not in _caps:
        if provider == "ollama":
            try:
                d = _json(ai_prefs["ollama_url"], "/api/show", {"model": model}, timeout=10, allow_lan=ai_prefs["allow_lan"])
                _caps[key] = "thinking" in (d.get("capabilities") or [])
            except (OSError, ValueError, urllib.error.URLError):
                return _guess_thinking(model)
        else:
            _caps[key] = _guess_thinking(model)
    return _caps[key]


# ── скачивание в Ollama ─────────────────────────────────────────────────────

def start_pull(conn, model):
    model = (model or "").strip()
    if not re.match(r"^[\w.\-/:@]{2,200}$", model):
        raise ValueError(L("Имя модели — как в каталоге Ollama, например qwen3:8b", "Model name as in the Ollama library, e.g. qwen3:8b"))
    ai = rules.get_prefs(conn)["ai"]
    _check(ai["ollama_url"], ai["allow_lan"])
    with _pull_lock:
        if not pull["done"]:
            raise ValueError(L(f"Уже скачивается {pull['model']}", f"{pull['model']} is already downloading"))
        pull.update(model=model, status=L("начинаю…", "starting…"), completed=0, total=0, error="", done=False, cancel=False)
    lang = i18n.lang()

    def work():
        i18n.set_lang(lang)
        try:
            with _req(ai["ollama_url"], "/api/pull", {"model": model, "stream": True}, timeout=600,
                      allow_lan=ai["allow_lan"]) as r:
                for line in r:
                    if pull["cancel"]:
                        pull.update(status=L("отменено", "cancelled"))
                        break
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    if ev.get("error"):
                        pull["error"] = str(ev["error"])[:300]
                        break
                    pull.update(status=str(ev.get("status", ""))[:120])
                    if ev.get("total"):
                        pull.update(total=int(ev["total"]), completed=int(ev.get("completed") or 0))
                    if ev.get("status") == "success":
                        print(f"Ассистент: скачана модель {model}", flush=True)
        except (OSError, ValueError, urllib.error.URLError) as e:
            pull["error"] = _human(e)
        finally:
            pull["done"] = True
    threading.Thread(target=work, name="ai-pull", daemon=True).start()
    return dict(pull)


def cancel_pull():
    pull["cancel"] = True
    return dict(pull)


def delete_model(conn, model):
    ai = rules.get_prefs(conn)["ai"]
    with _req(ai["ollama_url"], "/api/delete", {"model": model}, timeout=30, method="DELETE", allow_lan=ai["allow_lan"]):
        pass
    return {"ok": True}


# ── беседы ──────────────────────────────────────────────────────────────────

SESSION_KEYS = ("provider", "model", "temperature", "num_ctx", "max_tokens", "system", "period", "max_msgs",
                "include_logs", "include_read", "think")
THINK_BUDGET = 4096          # сколько токенов «думающей» модели даём на размышления сверх длины ответа


def think_budget(st):
    """Токены на размышления: не больше THINK_BUDGET и не больше 40% контекста (он делится с выборкой)."""
    return min(THINK_BUDGET, int(st["num_ctx"] * 0.4))


def session_defaults(conn):
    ai = rules.get_prefs(conn)["ai"]
    return {**{k: ai[k] for k in SESSION_KEYS}, "sources": []}


def clean_settings(conn, patch, base=None):
    base = dict(base or session_defaults(conn))
    merged = {**base, **{k: v for k, v in dict(patch or {}).items() if k in (*SESSION_KEYS, "sources")}}
    ai = rules.clean_ai({**rules.get_prefs(conn)["ai"], **{k: merged[k] for k in SESSION_KEYS}})
    return {**{k: ai[k] for k in SESSION_KEYS}, "sources": [str(x)[:200] for x in list(merged.get("sources") or [])][:50]}


def list_sessions(conn):
    return [{"id": i, "title": t, "created": c, "updated": u, "count": n}
            for i, t, c, u, n in conn.execute(
                "SELECT s.id, s.title, s.created, s.updated, (SELECT COUNT(*) FROM ai_messages m WHERE m.session_id = s.id) "
                "FROM ai_sessions s ORDER BY s.updated DESC LIMIT 500")]


def create_session(conn, settings=None, title=""):
    now = catcher.msk_time()
    st = clean_settings(conn, settings)
    cur = conn.execute("INSERT INTO ai_sessions (title, created, updated, settings) VALUES (?,?,?,?)",
                       (title[:120], now, now, json.dumps(st, ensure_ascii=False)))
    return get_session(conn, cur.lastrowid)


def get_session(conn, sid):
    row = conn.execute("SELECT id, title, created, updated, settings FROM ai_sessions WHERE id = ?", (sid,)).fetchone()
    if not row:
        raise ValueError(L("Нет такой беседы", "No such conversation"))
    try:
        st = json.loads(row[4] or "{}")
    except ValueError:
        st = {}
    msgs = [{"id": i, "role": r, "content": c, "created": t, "meta": json.loads(m or "{}")}
            for i, r, c, t, m in conn.execute("SELECT id, role, content, created, meta FROM ai_messages "
                                              "WHERE session_id = ? ORDER BY id", (sid,))]
    return {"id": row[0], "title": row[1], "created": row[2], "updated": row[3],
            "settings": {**session_defaults(conn), **st}, "messages": msgs}


def update_session(conn, sid, title=None, settings=None):
    s = get_session(conn, sid)
    if title is not None:
        conn.execute("UPDATE ai_sessions SET title = ? WHERE id = ?", (str(title).strip()[:120], sid))
    if settings is not None:
        st = clean_settings(conn, settings, s["settings"])
        conn.execute("UPDATE ai_sessions SET settings = ? WHERE id = ?", (json.dumps(st, ensure_ascii=False), sid))
    return get_session(conn, sid)


def delete_session(conn, sid):
    conn.execute("DELETE FROM ai_messages WHERE session_id = ?", (sid,))
    return conn.execute("DELETE FROM ai_sessions WHERE id = ?", (sid,)).rowcount


def save_defaults(conn, settings):
    st = clean_settings(conn, settings)
    rules.set_prefs(conn, {"ai": {k: st[k] for k in SESSION_KEYS}})
    return st


def export_markdown(conn, sid):
    s = get_session(conn, sid)
    out = [f"# {s['title'] or L('Беседа', 'Conversation')}", ""]
    for m in s["messages"]:
        who = L("Я", "Me") if m["role"] == "user" else L("Ассистент", "Assistant")
        out += [f"**{who}** · {m['created'][:16]}", "", m["content"], ""]
    return "\n".join(out)


# ── выборка сообщений под вопрос ────────────────────────────────────────────

STOP = set("""и в во на не что это как а но или ли же бы за по из от до для о об про у к ко с со мне меня мой
моя мои я ты вы он она они мы там тут где когда какой какие какая кто чем чего всё все всех было была были
есть нет да ну вот the a an of to in on at for and or is are was were what who which when how me my i you""".split())


def _stems(text):
    return {w[:5] for w in re.findall(r"[\w]{3,}", (text or "").casefold()) if w not in STOP and not w.isdigit()}


def question_period(q, default):
    """Слова «сегодня», «вчера», «за неделю», «за месяц» в вопросе → (с какого, по какое) местного времени."""
    ql = q.casefold()
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if re.search(r"\b(сегодня|today)\b", ql):
        return today, None
    if re.search(r"\b(вчера|yesterday)\b", ql):
        return today - timedelta(days=1), today
    if re.search(r"(за|this|past|last)\s+(недел|week)", ql):
        return now - timedelta(days=7), None
    if re.search(r"(за|this|past|last)\s+(месяц|month)", ql):
        return now - timedelta(days=30), None
    days = PERIODS.get(default, 7)
    return (now - timedelta(days=days) if days else None), None


def _msk(dt):
    """Местное naive → строка времени записи (received_at хранится по Москве)."""
    if dt is None:
        return ""
    local = dt.astimezone()
    return local.astimezone(catcher.MSK).strftime("%Y-%m-%d %H:%M:%S")


def build_context(conn, st, question, thinking=False):
    """Выборка сообщений: (строки для модели, id, сводка, с какого периода).
    thinking — модель будет размышлять: сообщениям достаётся меньшая доля контекста."""
    prefs = rules.get_prefs(conn)
    names = prefs["source_names"]
    frm, to = question_period(question, st["period"])
    where, params = [], []
    if frm:
        where.append("received_at >= ?"); params.append(_msk(frm))
    if to:
        where.append("received_at < ?"); params.append(_msk(to))
    if not st["include_read"]:
        where.append("is_read = 0")
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(f"SELECT id, app, COALESCE(site, ''), chat, sender, message, event_iso, details, is_read, "
                        f"resolved_at FROM messages{wsql} ORDER BY id DESC LIMIT 20000", params).fetchall()
    srcs = set(st.get("sources") or [])
    ql = question.casefold()
    items = []
    for mid, app, site, chat, sender, message, iso, details, is_read, resolved in rows:
        s = rules.source_of(app, site, names)
        if srcs and s["key"] not in srcs:
            continue
        items.append({"id": mid, "src": s["key"], "src_name": s["name"], "chat": chat or "", "sender": sender or "",
                      "text": message or "", "iso": iso or "", "details": details or "", "resolved": resolved or ""})
    total = len(items)
    by_src = {}
    for it in items:
        by_src[it["src_name"]] = by_src.get(it["src_name"], 0) + 1
    # что брать: подходящие по словам (или по смыслу, если включён умный поиск) + самые свежие
    qs = _stems(question)
    scored = {}
    if prefs["rag"]["enabled"]:
        try:
            import rag
            for score, mid in rag.search(conn, question, k=min(200, st["max_msgs"])):
                scored[mid] = 10 + score * 10
        except Exception:  # noqa: BLE001 — умный поиск недоступен: обойдёмся словами
            pass
    it_q = bool(re.search(r"контейнер|служб|сервер|упал|ошибк|сборк|деплой|container|service|crash|error|build", ql))
    for it in items:
        hay = _stems(f"{it['chat']} {it['sender']} {it['text']}")
        sc = len(qs & hay) * 3 + scored.get(it["id"], 0)
        if it_q and it["src"] in IT_SOURCES:
            sc += 2
        if sc:
            scored[it["id"]] = sc
    share = 0.35 if thinking else 0.55               # остальное — история беседы, размышления и ответ
    budget = int(st["num_ctx"] * share * 3)          # символов на сообщения (≈3 символа на токен)
    chosen, used = [], 0
    ranked = sorted(items, key=lambda x: (-scored.get(x["id"], 0), -x["id"]))
    for it in ranked:
        if len(chosen) >= st["max_msgs"]:
            break
        line = _line(it, st["include_logs"])
        if used + len(line) > budget:
            if scored.get(it["id"]):
                continue
            break
        chosen.append((it, line))
        used += len(line)
    chosen.sort(key=lambda x: x[0]["id"])
    period = (frm.strftime("%d.%m %H:%M") if frm else L("всё время", "all time")) + \
        (" – " + to.strftime("%d.%m %H:%M") if to else "")
    summary = L(f"Период: {period}. Всего сообщений: {total}", f"Period: {period}. Messages in total: {total}") + \
        ("; " + ", ".join(f"{k} {v}" for k, v in sorted(by_src.items(), key=lambda x: -x[1])[:10]) if by_src else "") + \
        "." + (L(f" В выборке: {len(chosen)}.", f" In the selection: {len(chosen)}.") if chosen else "")
    return [ln for _, ln in chosen], [it["id"] for it, _ in chosen], summary, period


def _line(it, logs):
    when = it["iso"].replace("T", " ")[5:16] if it["iso"] else ""
    who = " / ".join(x for x in (it["src_name"], it["chat"], it["sender"] if it["sender"] != it["chat"] else "") if x)
    text = re.sub(r"\s+", " ", it["text"]).strip()[:600]
    s = f"#{it['id']} · {when} · {who}: {text}"
    if it.get("resolved"):                # тематические колонки: проблема уже ушла
        s += L(f" [починилось {it['resolved'][5:16]}]", f" [fixed {it['resolved'][5:16]}]")
    if logs and it["details"]:
        s += "\n    " + it["details"][-800:].replace("\n", "\n    ")
    return s + "\n"


def default_system():
    return L("Ты — помощник, который отвечает на вопросы по уведомлениям пользователя: сообщениям из мессенджеров, "
             "почты и событиям компьютера (контейнеры, службы, команды). Отвечай по-русски, коротко и по делу, "
             "списками, где уместно. Опирайся только на приведённые сообщения; если ответа в них нет — так и скажи. "
             "Когда ссылаешься на сообщение, пиши его номер в виде #123. Ничего не выдумывай.",
             "You are an assistant answering questions about the user's notifications: messages from messengers, "
             "mail and computer events (containers, services, commands). Answer in English, briefly and to the point, "
             "with lists where it helps. Rely only on the messages given; if the answer is not there, say so. "
             "When you refer to a message, write its number like #123. Do not make anything up.")


# ── ответ модели потоком ────────────────────────────────────────────────────

def _history(msgs, budget):
    out, used = [], 0
    for m in reversed(msgs):
        if m["role"] not in ("user", "assistant"):
            continue
        n = len(m["content"])
        if used + n > budget:
            break
        out.append({"role": m["role"], "content": m["content"]})
        used += n
    return list(reversed(out))


def chat(db_path, sid, question, emit, lang="ru"):
    """Вопрос → ответ модели потоком: emit(dict) для каждого события. Возвращает сохранённый ответ."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        i18n.set_lang(lang)
        s = get_session(conn, sid)
        st = s["settings"]
        ai = rules.get_prefs(conn)["ai"]
        if not st["provider"] or not st["model"]:
            raise ValueError(L("Выбери модель в настройках беседы", "Pick a model in the conversation settings"))
        question = question.strip()[:8000]
        if not question:
            raise ValueError(L("Пустой вопрос", "Empty question"))
        now = catcher.msk_time()
        conn.execute("INSERT INTO ai_messages (session_id, role, content, created) VALUES (?,?,?,?)",
                     (sid, "user", question, now))
        if not s["title"]:
            conn.execute("UPDATE ai_sessions SET title = ? WHERE id = ?", (question.splitlines()[0][:80], sid))
        conn.execute("UPDATE ai_sessions SET updated = ? WHERE id = ?", (now, sid))
        conn.commit()
        will_think = st.get("think") != "off" and thinks(ai, st["provider"], st["model"])
        lines, ids, summary, period = build_context(conn, st, question, will_think)
        emit({"type": "context", "count": len(ids), "ids": ids, "summary": summary, "period": period})
        system = (st["system"] or default_system()) + "\n\n" + L(
            "Сводка по выборке: ", "Selection summary: ") + summary + "\n" + L(
            "Сообщения (номер · дата · источник / чат / кто: текст):", "Messages (number · date · source / chat / who: text):") + \
            "\n" + ("".join(lines) or L("(за этот период сообщений нет)\n", "(no messages in this period)\n"))
        hist = _history(s["messages"], int(st["num_ctx"] * 0.2 * 3))
        messages = [{"role": "system", "content": system}, *hist, {"role": "user", "content": question}]
        t0, answer, thought, tokens, stopped, reason = time.time(), [], [], 0, False, ""
        split = ThinkSplitter()             # <think>…</think> внутри текста (LM Studio, старые Ollama) — в размышления
        try:
            for ev in _stream(ai, st, messages):
                for kind, piece in split.feed(ev.get("t", ""), ev.get("think", "")):
                    (thought if kind == "think" else answer).append(piece)
                    if not emit({"type": "think" if kind == "think" else "token", "t": piece}):
                        stopped = True
                        break
                if stopped:
                    break
                tokens = ev.get("tokens") or tokens
                reason = ev.get("done_reason") or reason
        except (OSError, ValueError, urllib.error.URLError) as e:
            if not answer and not thought:
                raise ValueError(L(f"Модель не ответила: {_human(e)}", f"The model did not answer: {_human(e)}"))
            stopped = True
        for kind, piece in split.flush():
            (thought if kind == "think" else answer).append(piece)
            emit({"type": "think" if kind == "think" else "token", "t": piece})
        text = "".join(answer).strip()
        note = ""
        if not text and not stopped:
            note = (L("Модель не успела ответить: весь лимит ушёл на размышления. Увеличь «Размер контекста» и "
                      "«Длину ответа» в настройках беседы или возьми модель без размышлений.",
                      "The model ran out of room: the whole limit went into thinking. Raise “Context size” and “Answer "
                      "length” in the conversation settings or use a model without thinking.") if thought else
                    L("Модель ничего не ответила. Попробуй ещё раз, другую модель или меньше сообщений в выборке.",
                      "The model returned nothing. Try again, another model or fewer messages in the selection."))
        elif reason == "length" and text:
            note = L("Ответ обрезан по «Длине ответа» — её можно увеличить в настройках беседы.",
                     "The answer was cut at “Answer length” — raise it in the conversation settings.")
        meta = {"ids": ids, "model": f"{st['provider']}: {st['model']}", "ms": int((time.time() - t0) * 1000),
                "tokens": tokens, "stopped": stopped, "summary": summary, "note": note,
                "thinking": "".join(thought).strip()[-20000:]}
        conn.execute("INSERT INTO ai_messages (session_id, role, content, created, meta) VALUES (?,?,?,?,?)",
                     (sid, "assistant", text, catcher.msk_time(), json.dumps(meta, ensure_ascii=False)))
        conn.execute("UPDATE ai_sessions SET updated = ? WHERE id = ?", (catcher.msk_time(), sid))
        conn.commit()
        emit({"type": "done", **meta})
        return text
    finally:
        conn.close()


class ThinkSplitter:
    """Делит поток на размышления и ответ: отдельное поле thinking/reasoning_content или теги <think>…</think>
    в тексте (тег может прийти по кусочкам). → [(think|answer, текст)]."""

    def __init__(self):
        self.inside, self.buf = False, ""

    def feed(self, text, think=""):
        out = [("think", think)] if think else []
        self.buf += text or ""
        while self.buf:
            tag = "</think>" if self.inside else "<think>"
            i = self.buf.find(tag)
            if i < 0:
                keep = next((k for k in range(min(len(tag) - 1, len(self.buf)), 0, -1)
                             if tag.startswith(self.buf[-k:])), 0)      # хвост может быть началом тега
                piece, self.buf = self.buf[:len(self.buf) - keep], self.buf[len(self.buf) - keep:]
                if piece:
                    out.append(("think" if self.inside else "answer", piece))
                break
            if i:
                out.append(("think" if self.inside else "answer", self.buf[:i]))
            self.buf, self.inside = self.buf[i + len(tag):], not self.inside
        return [(k, p) for k, p in out if p]

    def flush(self):
        piece, self.buf = self.buf, ""
        return [("think" if self.inside else "answer", piece)] if piece else []


def _stream(ai, st, messages):
    """События от Ollama или LM Studio: {t: текст ответа, think: размышления, tokens, done_reason}."""
    can_think = thinks(ai, st["provider"], st["model"])
    think = can_think and st.get("think") != "off"
    budget = st["max_tokens"] + (think_budget(st) if think else 0)
    if st["provider"] == "ollama":
        body = {"model": st["model"], "messages": messages, "stream": True,
                "options": {"temperature": st["temperature"], "num_ctx": st["num_ctx"], "num_predict": budget}}
        if can_think:
            body["think"] = think        # у «думающих» моделей: выключено — отвечает сразу
        with _req(ai["ollama_url"], "/api/chat", body, timeout=900, allow_lan=ai["allow_lan"]) as r:
            for line in r:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("error"):
                    raise ValueError(str(ev["error"])[:300])
                m = ev.get("message") or {}
                yield {"t": m.get("content", ""), "think": m.get("thinking", ""),
                       "tokens": ev.get("eval_count", 0) if ev.get("done") else 0,
                       "done_reason": ev.get("done_reason", "") if ev.get("done") else ""}
                if ev.get("done"):
                    return
    else:
        if can_think and not think and "qwen3" in st["model"].lower():
            messages = [dict(messages[0], content=messages[0]["content"] + "\n/no_think"), *messages[1:]]
        body = {"model": st["model"], "messages": messages, "stream": True, "temperature": st["temperature"],
                "max_tokens": budget}
        with _req(ai["lmstudio_url"], "/v1/chat/completions", body, timeout=900, allow_lan=ai["allow_lan"]) as r:
            for raw in r:
                line = raw.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    ev = json.loads(data)
                except ValueError:
                    continue
                ch = (ev.get("choices") or [{}])[0]
                d = ch.get("delta") or {}
                yield {"t": d.get("content") or "", "think": d.get("reasoning_content") or d.get("reasoning") or "",
                       "tokens": (ev.get("usage") or {}).get("completion_tokens", 0),
                       "done_reason": ch.get("finish_reason") or ""}
