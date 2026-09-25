#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ассистент: беседа с моделью на этом компьютере по базе сообщений (окно /assistant).

Модель — локальная: Ollama (http://127.0.0.1:11434) или LM Studio (OpenAI-совместимый сервер,
http://127.0.0.1:1234); адрес в домашней сети — если это явно разрешить; другие адреса не
принимаются (rules.ai_url_ok). Единственное исключение — OpenRouter (облако, сотни моделей):
только если пользователь сам включил его, дал свой ключ и согласился, что выборка сообщений и
вопрос уйдут на серверы OpenRouter и провайдера модели; такие беседы помечены жёлтым.

Картинки к вопросу (для моделей, которые их видят): хранятся в <данные>/ai-images, модели уходят
только с последним вопросом.

Модели: список установленных (Ollama /api/tags, LM Studio /api/v0/models или /v1/models),
каталог для скачивания в Ollama (свой, с размерами; любое имя из ollama.com/library или
hf.co/… — тоже можно) — /api/pull с прогрессом и отменой, удаление — /api/delete. Для LM Studio
скачивание — в самой программе; если есть её команда lms, сервер можно запустить отсюда.

Беседы (таблицы ai_sessions, ai_messages): у каждой свои настройки — модель, температура,
размер контекста, длина ответа, свой системный промпт и выборка сообщений (период, источники,
сколько сообщений, брать ли логи и прочитанное). Ответ на вопрос:
  1. выборка: сообщения за период (слова «сегодня», «вчера», «за неделю» в вопросе сужают его),
     по источникам; самые подходящие — по умному поиску (векторы rag.py, если включён) или по
     словам вопроса, плюс самые свежие; сколько влезет в контекст (plan: запас на размышления и
     ответ, русский текст — ≈2 символа на токен; у OpenRouter контекст — самой модели);
  2. в модель — системный промпт, сводка (сколько сообщений, откуда), сами сообщения строками
     «#id · дата · источник / чат / кто: текст», история беседы и вопрос;
  3. ответ идёт потоком (NDJSON: context → think…/token… → done), номера #id в ответе — ссылки на окно
     сообщения. Прерванный ответ сохраняется как есть. «Думающая» модель истратила всё на
     размышления и не ответила — второй заход без них (retry), у OpenRouter с обязательными
     размышлениями — с наименьшим усилием.
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import base64
import hashlib
import http.client

import catcher
import i18n
import paths
import rules
from i18n import L

OPENROUTER = os.environ.get(f"{paths.ENV_PREFIX}_OPENROUTER_URL", "https://openrouter.ai/api/v1")   # переменная — для тестов
_or_models = {"t": 0.0, "list": [], "error": ""}
MAX_IMAGES, MAX_IMAGE_BYTES = 4, 8 * 1024 * 1024
_IMG_MAGIC = ((b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF8", "gif"), (b"RIFF", "webp"))

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
        elif sys.platform == "darwin":
            ram = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True,
                                     timeout=5).stdout.strip()) / 1024 ** 3
            vram = vram or ram * 0.66          # Apple Silicon: общая память, видеоядро берёт до ~2/3
        else:
            with open("/proc/meminfo", encoding="utf-8") as f:
                ram = int(f.readline().split()[1]) / 1024 ** 2
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
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
            out["models"] = [{"name": m.get("id", ""), "embed": m.get("type") == "embeddings", "vision": m.get("type") == "vlm",
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
    if isinstance(e, urllib.error.HTTPError):      # у OpenRouter и LM Studio причина — в теле ответа
        try:
            err = json.loads(e.read() or b"{}").get("error")
            msg = str((err or {}).get("message") if isinstance(err, dict) else err or "")
        except Exception:                           # тела может не быть вовсе (разные версии Python)
            msg = ""
        known = {401: L("ключ не подходит", "the key is not accepted"),
                 402: L("на счёте OpenRouter не хватает денег", "not enough credits on OpenRouter"),
                 429: L("слишком много запросов — лимит модели, попробуй позже", "too many requests — model limit, try later")}
        return (known.get(e.code) or f"HTTP {e.code}") + (f" ({msg[:200]})" if msg else "")
    s = str(getattr(e, "reason", "") or e)
    if "refused" in s.lower() or "10061" in s:
        return L("не запущен (соединение отклонено)", "not running (connection refused)")
    if "timed out" in s.lower():
        return L("не отвечает", "not responding")
    return s[:200]


# ── OpenRouter (внешний, по согласию) ────────────────────────────────────────

def or_key():
    try:
        with open(paths.OPENROUTER_CFG, encoding="utf-8") as f:
            return str(json.load(f).get("key") or "")
    except (OSError, ValueError):
        return ""


def or_save_key(key):
    key = (key or "").strip()
    if not key:
        try:
            os.remove(paths.OPENROUTER_CFG)
        except OSError:
            pass
        return
    if not re.match(r"^[\w\-.:]{16,200}$", key):
        raise ValueError(L("Ключ OpenRouter выглядит неправильно (sk-or-…)", "The OpenRouter key looks wrong (sk-or-…)"))
    paths.ensure_dirs()
    paths.write_private(paths.OPENROUTER_CFG, json.dumps({"key": key}))


def _or_req(path, body=None, timeout=30, auth=True):
    headers = {"Content-Type": "application/json", "HTTP-Referer": "https://github.com/DanielLetto2020/messhub",
               "X-Title": "messhub"}
    if auth:
        key = or_key()
        if not key:
            raise ValueError(L("Нет ключа OpenRouter — добавь его в «Моделях»", "No OpenRouter key — add it under “Models”"))
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(OPENROUTER + path, data=data, headers=headers, method="POST" if data else "GET")
    return urllib.request.urlopen(req, timeout=timeout)


def or_models(force=False):
    """Каталог моделей OpenRouter (публичный список, без ключа), кэш на час."""
    if not force and _or_models["list"] and time.time() - _or_models["t"] < 3600:
        return _or_models["list"]
    try:
        with _or_req("/models", timeout=20, auth=False) as r:
            data = json.load(r).get("data", [])
    except (OSError, ValueError, urllib.error.URLError) as e:
        _or_models["error"] = _human(e)
        return _or_models["list"]
    out = []
    for m in data:
        arch = m.get("architecture") or {}
        if "text" not in (arch.get("output_modalities") or ["text"]):
            continue
        pr = m.get("pricing") or {}

        def per_m(x):
            try:
                return round(float(x or 0) * 1_000_000, 3)
            except ValueError:
                return 0.0
        p_in, p_out = per_m(pr.get("prompt")), per_m(pr.get("completion"))    # цена-не-число не роняет весь каталог
        rs = m.get("reasoning") if isinstance(m.get("reasoning"), dict) else {}
        top = m.get("top_provider") if isinstance(m.get("top_provider"), dict) else {}
        out.append({"name": m.get("id", ""), "title": m.get("name", ""), "ctx": int(m.get("context_length") or 0),
                    "max_out": int(top.get("max_completion_tokens") or 0),
                    "vision": "image" in (arch.get("input_modalities") or []),
                    "reasoning": "reasoning" in (m.get("supported_parameters") or []),
                    "mandatory": bool(rs.get("mandatory")),   # размышления не выключаются (DeepSeek R1, gpt-oss, Gemini 2.5 Pro…)
                    "efforts": [str(x) for x in (rs.get("supported_efforts") or [])],
                    "price_in": p_in, "price_out": p_out,
                    "free": m.get("id", "").endswith(":free") or (not p_in and not p_out)})
    out.sort(key=lambda x: x["name"])
    _or_models.update(t=time.time(), list=out, error="")
    return out


def or_status(ai_prefs, with_models=False):
    key = or_key()
    st = {"enabled": ai_prefs["openrouter"], "has_key": bool(key), "hint": ("…" + key[-4:]) if key else "",
          "consent": ai_prefs["openrouter_consent"], "error": _or_models["error"], "models": []}
    if with_models and ai_prefs["openrouter"]:
        st["models"] = or_models()
        st["error"] = _or_models["error"]
    return st


def or_setup(conn, enabled, key=None, consent=False):
    """Включить OpenRouter (нужны ключ и согласие), выключить или удалить ключ."""
    if key is not None:
        or_save_key(key)
    if enabled:
        if not or_key():
            raise ValueError(L("Сначала вставь ключ OpenRouter", "Paste the OpenRouter key first"))
        if not consent:
            raise ValueError(L("Нужно согласие: выборка сообщений и вопросы будут уходить в OpenRouter",
                               "Consent is needed: message selections and questions will be sent to OpenRouter"))
        rules.set_prefs(conn, {"ai": {"openrouter": True, "openrouter_consent": catcher.msk_time()}}, cloud_ok=True)
    else:
        upd = {"openrouter": False}
        if rules.get_prefs(conn)["ai"]["provider"] == "openrouter":   # новые беседы не должны начинаться с облака
            upd.update(provider="", model="")
        rules.set_prefs(conn, {"ai": upd}, cloud_ok=True)
    return or_status(rules.get_prefs(conn)["ai"], with_models=enabled)


def _or_model(name):
    return next((m for m in _or_models["list"] if m["name"] == name), None)


def _demo_status(ai):
    """Снимки экрана (MESSHUB_THEMED_DEMO=1): выдуманные модели вместо настоящих Ollama и LM Studio."""
    return ({"url": ai["ollama_url"], "ok": True, "version": "0.13.5", "error": "", "running": ["qwen3:8b"],
             "models": [{"name": "qwen3:8b", "gb": 5.2, "params": "8.2B", "quant": "Q4_K_M", "family": "qwen3", "embed": False},
                        {"name": "gemma3:4b", "gb": 3.3, "params": "4.3B", "quant": "Q4_K_M", "family": "gemma3", "embed": False},
                        {"name": "bge-m3", "gb": 1.2, "params": "567M", "quant": "F16", "family": "bert", "embed": True}]},
            {"url": ai["lmstudio_url"], "ok": False, "error": L("не запущен (соединение отклонено)", "not running (connection refused)"),
             "models": [], "cli": True})


_DEMO_OR = [  # имя, название, контекст, картинки, размышления, цена за 1 млн токенов (вход, выход)
    ("deepseek/deepseek-r1-0528:free", "DeepSeek: R1 0528 (free)", 163840, False, True, 0, 0),
    ("google/gemini-2.5-flash", "Google: Gemini 2.5 Flash", 1048576, True, True, 0.3, 2.5),
    ("google/gemini-2.5-pro", "Google: Gemini 2.5 Pro", 1048576, True, True, 1.25, 10),
    ("meta-llama/llama-3.3-70b-instruct:free", "Meta: Llama 3.3 70B Instruct (free)", 131072, False, False, 0, 0),
    ("mistralai/mistral-small-3.2-24b-instruct", "Mistral: Mistral Small 3.2 24B", 131072, True, False, 0.05, 0.1),
    ("openai/gpt-4.1-mini", "OpenAI: GPT-4.1 Mini", 1047576, True, False, 0.4, 1.6),
    ("openai/gpt-oss-120b", "OpenAI: gpt-oss-120b", 131072, False, True, 0.07, 0.28),
    ("qwen/qwen2.5-vl-72b-instruct:free", "Qwen: Qwen2.5 VL 72B Instruct (free)", 32768, True, False, 0, 0),
    ("qwen/qwen3-235b-a22b-2507", "Qwen: Qwen3 235B A22B Instruct 2507", 262144, False, False, 0.08, 0.55),
    ("x-ai/grok-4-fast", "xAI: Grok 4 Fast", 2000000, True, True, 0.2, 0.5)]


def _demo_or(ai):
    models = [{"name": n, "title": ti, "ctx": c, "max_out": 0, "vision": v, "reasoning": r, "mandatory": r, "efforts": [],
               "price_in": pi, "price_out": po, "free": not pi and not po} for n, ti, c, v, r, pi, po in _DEMO_OR]
    _or_models.update(t=time.time(), list=models, error="")
    on = ai["openrouter"]
    return {"enabled": on, "has_key": on, "hint": "…demo" if on else "", "consent": ai["openrouter_consent"],
            "error": "", "models": models if on else []}


def status(conn):
    ai = rules.get_prefs(conn)["ai"]
    hw = hardware()
    if os.environ.get("MESSHUB_THEMED_DEMO") == "1":
        hw = {"vram_gb": 8.0, "ram_gb": 32.0}
        o, lm = _demo_status(ai)
        return {"prefs": ai, "ollama": o, "lmstudio": lm, "hardware": hw,
                "openrouter": _demo_or(ai),
                "catalog": [dict(c, about=c["about"][i18n.lang() == "en"], fit=fit(c["gb"], hw)) for c in CATALOG],
                "pull": dict(pull), "ctx_sizes": list(CTX_SIZES), "periods": list(PERIODS), "default_system": default_system()}
    return {"prefs": ai, "ollama": ollama_status(ai["ollama_url"]), "lmstudio": lmstudio_status(ai["lmstudio_url"]),
            "openrouter": or_status(ai, with_models=True),
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
            caps = d.get("capabilities") or []
            thinking = "thinking" in caps
            _caps[(provider, model)] = thinking
            return {"ctx": int(ctx or 0), "params": (d.get("details") or {}).get("parameter_size", ""),
                    "thinking": thinking, "vision": "vision" in caps}
        if provider == "openrouter":
            m = _or_model(model) or (or_models() and _or_model(model)) or {}
            return {"ctx": m.get("ctx", 0), "params": "", "thinking": m.get("reasoning", False), "vision": m.get("vision", False),
                    "mandatory": m.get("mandatory", False), "max_out": m.get("max_out", 0),
                    "price_in": m.get("price_in", 0), "price_out": m.get("price_out", 0)}
        for m in lmstudio_status(ai["lmstudio_url"])["models"]:
            if m["name"] == model:
                return {"ctx": int(m.get("ctx") or 0), "params": "", "thinking": _guess_thinking(model),
                        "vision": m.get("vision", False)}
    except (OSError, ValueError, urllib.error.URLError):
        pass
    return {"ctx": 0, "params": "", "thinking": _guess_thinking(model), "vision": False}


def _guess_thinking(model):
    return bool(re.search(r"qwen3|deepseek-r1|qwq|gpt-oss|magistral|phi4-reasoning|thinking|reason", model.lower()))


def thinks(ai_prefs, provider, model):
    """Умеет ли модель размышлять (у Ollama — по её описанию, спрашиваем один раз)."""
    key = (provider, model)
    if provider == "openrouter":
        m = _or_model(model)
        return bool(m and m["reasoning"])
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
CHARS_PER_TOKEN = 2.0       # замер на русских сообщениях (qwen3, T-lite): ≈2 символа на токен; по-английски — больше
MARGIN = 256                # токенов про запас: служебная разметка чата у модели
OR_THINK = 16384            # OpenRouter: запас на размышления сверх ответа (OpenRouter заранее бронирует деньги на max_tokens)
LOCAL_THINK_MAX = 8192      # на компьютере: размышлениям — остаток контекста, но не больше (зациклившаяся модель думала бы час)
IMAGE_TOKENS = 1500         # сколько контекста примерно занимает одна картинка


def est_tokens(text):
    """Сколько токенов займёт текст — с запасом (точно знает только сама модель)."""
    return int(len(text or "") / CHARS_PER_TOKEN) + 1


def plan(st, lim=None, thinking=False):
    """Как делить контекст: ctx — весь, out — запас на размышления и ответ, prompt — на промпт (системный
    промпт, выборка, история, вопрос). У OpenRouter контекст — самой модели (настройка «Размер контекста»
    только для моделей на этом компьютере: от неё зависит видеопамять)."""
    lim = lim or {}
    ctx = st["num_ctx"]
    if st["provider"] == "openrouter":              # каталог не загрузился — хотя бы 32 тыс.: облачные модели умеют больше
        ctx = lim.get("ctx") or max(ctx, 32768)
    think = 0
    if thinking:
        think = OR_THINK if st["provider"] == "openrouter" else max(2048, int(ctx * 0.3))
    out = st["max_tokens"] + think
    if lim.get("max_out"):
        out = min(out, lim["max_out"])
    out = min(out, int(ctx * 0.6))                  # промпту — не меньше 40% контекста
    return {"ctx": ctx, "out": out, "prompt": max(256, ctx - out - MARGIN)}


def session_defaults(conn):
    ai = rules.get_prefs(conn)["ai"]
    return {**{k: ai[k] for k in SESSION_KEYS}, "sources": []}


def clean_settings(conn, patch, base=None):
    base = dict(base or session_defaults(conn))
    merged = {**base, **{k: v for k, v in dict(patch or {}).items() if k in (*SESSION_KEYS, "sources")}}
    ai = rules.clean_ai({**rules.get_prefs(conn)["ai"], **{k: merged[k] for k in SESSION_KEYS}})
    return {**{k: ai[k] for k in SESSION_KEYS}, "sources": [str(x)[:200] for x in list(merged.get("sources") or [])][:50]}


def list_sessions(conn):
    def prov(settings):
        try:
            return str(json.loads(settings or "{}").get("provider") or "")
        except ValueError:
            return ""
    return [{"id": i, "title": t, "created": c, "updated": u, "count": n, "provider": prov(st)}
            for i, t, c, u, n, st in conn.execute(
                "SELECT s.id, s.title, s.created, s.updated, (SELECT COUNT(*) FROM ai_messages m WHERE m.session_id = s.id), "
                "s.settings FROM ai_sessions s ORDER BY s.updated DESC LIMIT 500")]


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
    mine = set()
    for (meta,) in conn.execute("SELECT meta FROM ai_messages WHERE session_id = ?", (sid,)):
        try:
            mine |= set(json.loads(meta or "{}").get("images") or [])
        except ValueError:
            pass
    conn.execute("DELETE FROM ai_messages WHERE session_id = ?", (sid,))
    n = conn.execute("DELETE FROM ai_sessions WHERE id = ?", (sid,)).rowcount
    if mine:                                   # картинки, которых больше нет ни в одной беседе, — удалить
        used = set()
        for (meta,) in conn.execute("SELECT meta FROM ai_messages WHERE meta LIKE '%images%'"):
            try:
                used |= set(json.loads(meta or "{}").get("images") or [])
            except ValueError:
                pass
        for name in mine - used:
            p = image_file(name)
            if p:
                os.remove(p)
    return n


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


def build_context(conn, st, question, thinking=False, budget=None):
    """Выборка сообщений: (строки для модели, id, сводка, с какого периода).
    budget — символов на сообщения (по умолчанию — 3/4 промпта по plan; thinking — модель будет размышлять,
    сообщениям достаётся меньше)."""
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
    rows = conn.execute(f"SELECT id, app, COALESCE(site, ''), chat, sender, message, event_iso, details, "
                        f"resolved_at FROM messages{wsql} ORDER BY id DESC LIMIT 20000", params).fetchall()
    srcs = set(st.get("sources") or [])
    ql = question.casefold()
    items = []
    for mid, app, site, chat, sender, message, iso, details, resolved in rows:
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
    if budget is None:
        budget = int(plan(st, None, thinking)["prompt"] * 0.75 * CHARS_PER_TOKEN)
    chosen, used, cut = [], 0, False
    ranked = sorted(items, key=lambda x: (-scored.get(x["id"], 0), -x["id"]))
    for it in ranked:
        if len(chosen) >= st["max_msgs"]:
            break
        line = _line(it, st["include_logs"])
        if used + len(line) > budget:
            cut = True
            if scored.get(it["id"]):
                continue
            break
        chosen.append((it, line))
        used += len(line)
    left = min(len(ranked), st["max_msgs"]) - len(chosen) if cut else 0
    chosen.sort(key=lambda x: x[0]["id"])
    period = (frm.strftime("%d.%m %H:%M") if frm else L("всё время", "all time")) + \
        (" – " + to.strftime("%d.%m %H:%M") if to else "")
    summary = L(f"Период: {period}. Всего сообщений: {total}", f"Period: {period}. Messages in total: {total}") + \
        ("; " + ", ".join(f"{k} {v}" for k, v in sorted(by_src.items(), key=lambda x: -x[1])[:10]) if by_src else "") + \
        "." + (L(f" В выборке: {len(chosen)}.", f" In the selection: {len(chosen)}.") if chosen else "") + \
        (L(f" Не влезло в контекст: {left}.", f" Did not fit into the context: {left}.") if left else "")
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
             "Когда ссылаешься на сообщение, пиши его номер в виде #123. Ничего не выдумывай. "
             "Если просят график или диаграмму, выведи данные блоком ```chart с JSON вида "
             "{\"type\": \"bar\" | \"line\" | \"pie\", \"title\": \"…\", \"labels\": [\"…\"], "
             "\"series\": [{\"name\": \"…\", \"data\": [числа]}]} — окно само нарисует график.",
             "You are an assistant answering questions about the user's notifications: messages from messengers, "
             "mail and computer events (containers, services, commands). Answer in English, briefly and to the point, "
             "with lists where it helps. Rely only on the messages given; if the answer is not there, say so. "
             "When you refer to a message, write its number like #123. Do not make anything up. "
             "If asked for a chart, output the data as a ```chart block with JSON like "
             "{\"type\": \"bar\" | \"line\" | \"pie\", \"title\": \"…\", \"labels\": [\"…\"], "
             "\"series\": [{\"name\": \"…\", \"data\": [numbers]}]} — the window draws it.")


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


def save_images(data_urls):
    """data:-адреса картинок со страницы → имена файлов в <данные>/ai-images (по содержимому)."""
    names = []
    for u in list(data_urls or [])[:MAX_IMAGES]:
        m = re.match(r"^data:image/[\w.+-]+;base64,(.+)$", str(u), re.S)
        if not m:
            raise ValueError(L("Картинка не распознана", "The image was not recognized"))
        raw = base64.b64decode(m.group(1), validate=False)
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError(L("Картинка больше 8 МБ", "The image is larger than 8 MB"))
        ext = next((e for magic, e in _IMG_MAGIC if raw.startswith(magic)), None)
        if not ext or (ext == "webp" and raw[8:12] != b"WEBP"):
            raise ValueError(L("Годятся PNG, JPEG, GIF и WebP", "PNG, JPEG, GIF and WebP work"))
        name = hashlib.sha256(raw).hexdigest()[:24] + "." + ext
        os.makedirs(paths.AI_IMAGES_DIR, exist_ok=True)
        path = os.path.join(paths.AI_IMAGES_DIR, name)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(raw)
        names.append(name)
    return names


def image_file(name):
    if not re.match(r"^[0-9a-f]{24}\.(png|jpg|gif|webp)$", name or ""):
        return None
    p = os.path.join(paths.AI_IMAGES_DIR, name)
    return p if os.path.exists(p) else None


def _b64(name):
    with open(os.path.join(paths.AI_IMAGES_DIR, name), "rb") as f:
        return base64.b64encode(f.read()).decode()


def _with_images(provider, msg, names):
    """Вопрос с картинками — в формате провайдера (Ollama: images, остальные: части content)."""
    if not names:
        return msg
    if provider == "ollama":
        return dict(msg, images=[_b64(n) for n in names])
    mime = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}
    return {"role": msg["role"], "content": [{"type": "text", "text": msg["content"]}] +
            [{"type": "image_url", "image_url": {"url": f"data:{mime[n.rsplit('.', 1)[1]]};base64,{_b64(n)}"}} for n in names]}


def chat(db_path, sid, question, emit, lang="ru", images=None):
    """Вопрос → ответ модели потоком: emit(dict) для каждого события. Возвращает сохранённый ответ."""
    conn = sqlite3.connect(db_path, timeout=10)
    try:
        i18n.set_lang(lang)
        s = get_session(conn, sid)
        st = s["settings"]
        ai = rules.get_prefs(conn)["ai"]
        if not st["provider"] or not st["model"]:
            raise ValueError(L("Выбери модель в настройках беседы", "Pick a model in the conversation settings"))
        if st["provider"] == "openrouter" and not ai["openrouter"]:
            raise ValueError(L("OpenRouter выключен — включи его в «Моделях» или выбери локальную модель",
                               "OpenRouter is off — turn it on under “Models” or pick a local model"))
        question = question.strip()[:8000]
        names = save_images(images) if images else []
        if not question and names:
            question = L("Что на картинке?", "What is in the picture?")
        if not question:
            raise ValueError(L("Пустой вопрос", "Empty question"))
        now = catcher.msk_time()
        conn.execute("INSERT INTO ai_messages (session_id, role, content, created, meta) VALUES (?,?,?,?,?)",
                     (sid, "user", question, now, json.dumps({"images": names}) if names else "{}"))
        if not s["title"]:
            conn.execute("UPDATE ai_sessions SET title = ? WHERE id = ?", (question.splitlines()[0][:80], sid))
        conn.execute("UPDATE ai_sessions SET updated = ? WHERE id = ?", (now, sid))
        conn.commit()
        lim = _limits(st["provider"], st["model"])          # у OpenRouter — заодно подтянет каталог моделей
        can_think = thinks(ai, st["provider"], st["model"])
        will_think = st.get("think") != "off" and can_think
        pl = plan(st, lim, will_think or bool(lim.get("mandatory")))
        base = st["system"] or default_system()
        fixed = est_tokens(base + question) + 200 + IMAGE_TOKENS * len(names)       # 200 — сводка и подписи
        hist = _history(s["messages"], int(pl["prompt"] * 0.2 * CHARS_PER_TOKEN))
        room = pl["prompt"] - fixed - sum(est_tokens(m["content"]) for m in hist)
        lines, ids, summary, period = build_context(conn, st, question, will_think,
                                                    budget=max(0, int(room * CHARS_PER_TOKEN)))
        emit({"type": "context", "count": len(ids), "ids": ids, "summary": summary, "period": period})
        system = base + "\n\n" + L(
            "Сводка по выборке: ", "Selection summary: ") + summary + "\n" + L(
            "Сообщения (номер · дата · источник / чат / кто: текст):", "Messages (number · date · source / chat / who: text):") + \
            "\n" + ("".join(lines) or L("(за этот период сообщений нет)\n", "(no messages in this period)\n"))
        messages = [{"role": "system", "content": system}, *hist,
                    _with_images(st["provider"], {"role": "user", "content": question}, names)]
        used = est_tokens(system + question) + sum(est_tokens(m["content"]) for m in hist) + IMAGE_TOKENS * len(names)
        free = max(st["max_tokens"], pl["ctx"] - used - MARGIN)      # всё, что осталось от контекста
        t0, answer, thought, tokens, stopped, reason, cost = time.time(), [], [], 0, False, "", None
        retried, retry_err = False, ""
        # первый заход — как настроено; если размышления съели весь запас и ответа нет — второй, без размышлений
        passes = [dict(st, _predict=_predict(st, pl, free, will_think, lim))]
        while passes:
            cur = passes.pop(0)
            split = ThinkSplitter()         # <think>…</think> внутри текста (LM Studio, старые Ollama) — в размышления
            reason, p_tok, p_cost = "", 0, None
            try:
                for ev in _stream(ai, cur, messages):
                    for kind, piece in split.feed(ev.get("t", ""), ev.get("think", "")):
                        (thought if kind == "think" else answer).append(piece)
                        if not emit({"type": "think" if kind == "think" else "token", "t": piece}):
                            stopped = True
                            break
                    if stopped:
                        break
                    p_tok = ev.get("tokens") or p_tok
                    reason = ev.get("done_reason") or reason
                    p_cost = ev.get("cost", p_cost)
            except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException) as e:   # в т.ч. оборванный поток
                if retried and not answer:          # второй заход не удался — объясним в заметке
                    retry_err = _human(e)
                elif not answer and not thought:
                    raise ValueError(L(f"Модель не ответила: {_human(e)}", f"The model did not answer: {_human(e)}"))
                else:
                    stopped = True
            for kind, piece in split.flush():
                (thought if kind == "think" else answer).append(piece)
                emit({"type": "think" if kind == "think" else "token", "t": piece})
            tokens += p_tok                     # за оба захода: платят и за размышления первого
            if p_cost is not None:
                cost = (cost or 0) + p_cost
            if not retried and not stopped and not "".join(answer).strip() and (thought or reason == "length") \
                    and (can_think or lim.get("mandatory")):
                retried = True
                if not emit({"type": "retry", "text": L("Размышления заняли весь запас — отвечаю с наименьшими размышлениями…",
                                                        "Thinking used up the whole budget — answering with the least thinking…")
                             if lim.get("mandatory") else L("Размышления заняли весь запас — отвечаю без них…",
                                                            "Thinking used up the whole budget — answering without it…")}):
                    stopped = True
                    break
                passes.append(dict(st, think="off", _retry=True, _predict=_predict(st, pl, free, True, lim)))
        text = "".join(answer)
        if "</think>" in text:          # «думает всегда», а <think> открыл шаблон модели: рассуждения — до </think>
            pre, text = text.rsplit("</think>", 1)
            thought.append(pre.replace("<think>", ""))
        text = text.strip()
        note = ""
        if not text and not stopped:
            note = (L("Модель не успела ответить: весь запас ушёл на размышления, а без них она отвечать не стала. "
                      "Увеличь «Размер контекста» в настройках беседы или возьми модель без размышлений.",
                      "The model ran out of room: everything went into thinking, and it would not answer without it. "
                      "Raise “Context size” in the conversation settings or use a model without thinking.") if thought else
                    L("Модель ничего не ответила. Попробуй ещё раз, другую модель или меньше сообщений в выборке.",
                      "The model returned nothing. Try again, another model or fewer messages in the selection."))
            if retry_err:
                note += L(f" Второй заход не удался: {retry_err}.", f" The second attempt failed: {retry_err}.")
        elif retried and text:
            note = (L("Размышления заняли весь запас — ответ дан с наименьшими размышлениями.",
                      "Thinking used up the whole budget — the answer was given with the least thinking.")
                    if lim.get("mandatory") else
                    L("Размышления заняли весь запас — ответ дан без них. Чтобы модель успевала подумать, увеличь "
                      "«Размер контекста» в настройках беседы.",
                      "Thinking used up the whole budget — the answer was given without it. To leave room for thinking, "
                      "raise “Context size” in the conversation settings."))
        elif reason == "length" and text:
            note = L("Ответ обрезан по «Длине ответа» — её можно увеличить в настройках беседы.",
                     "The answer was cut at “Answer length” — raise it in the conversation settings.")
        meta = {"ids": ids, "model": f"{st['provider']}: {st['model']}", "ms": int((time.time() - t0) * 1000),
                "external": st["provider"] == "openrouter",
                "tokens": tokens, "stopped": stopped, "summary": summary, "note": note,
                "thinking": "".join(thought).strip()[-20000:]}
        if cost is not None:
            meta["cost"] = cost                  # OpenRouter: сколько стоил ответ, в долларах
        conn.execute("INSERT INTO ai_messages (session_id, role, content, created, meta) VALUES (?,?,?,?,?)",
                     (sid, "assistant", text, catcher.msk_time(), json.dumps(meta, ensure_ascii=False)))
        conn.execute("UPDATE ai_sessions SET updated = ? WHERE id = ?", (catcher.msk_time(), sid))
        conn.commit()
        emit({"type": "done", **meta})
        return text
    finally:
        conn.close()


def _limits(provider, model):
    """Пределы облачной модели из каталога OpenRouter: контекст, длина ответа, обязательные размышления."""
    if provider != "openrouter":
        return {}
    m = _or_model(model) or (or_models() and _or_model(model)) or {}
    return {k: m.get(k, d) for k, d in (("ctx", 0), ("max_out", 0), ("mandatory", False), ("efforts", []))}


def _predict(st, pl, free, thinking, lim):
    """Сколько токенов модели можно выдать за заход. Размышления идут в тот же счёт, что и ответ, поэтому
    «думающей» модели — всё, что осталось от контекста (у OpenRouter — запас plan: он бронирует деньги)."""
    if st["provider"] == "openrouter":
        return pl["out"] if thinking or lim.get("mandatory") else st["max_tokens"]
    return min(free, st["max_tokens"] + LOCAL_THINK_MAX) if thinking else st["max_tokens"]


EFFORTS = ("minimal", "low", "medium", "high", "xhigh", "max")


def _or_reasoning(think, lim):
    """Параметр reasoning для OpenRouter: выключить размышления можно, только если модель это позволяет;
    у моделей с обязательными размышлениями — наименьшее усилие (exclude лишь прятал бы их, а платить — всё равно)."""
    if think:
        return None
    efforts = lim.get("efforts") or []            # пусто — модель принимает любое усилие
    if not lim.get("mandatory"):                  # усилие не из списка модели OpenRouter отклоняет (400)
        return {"effort": "none"} if not efforts or "none" in efforts else {"enabled": False}
    low = next((e for e in EFFORTS if e in efforts), None)
    return {"effort": low or "low"}


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
    budget = st.get("_predict") or st["max_tokens"]
    if st["provider"] == "ollama":
        body = {"model": st["model"], "messages": messages, "stream": True,
                "options": {"temperature": st["temperature"], "num_ctx": st["num_ctx"], "num_predict": budget}}
        if can_think:
            body["think"] = think        # у «думающих» моделей: выключено — отвечает сразу
        if can_think and st.get("_retry"):
            if "gpt-oss" in st["model"].lower():
                body["think"] = "low"    # gpt-oss не выключает размышления, только уровень
            else:   # модели «думают всегда» (…-Thinking-2507) think=false не слушают: начинаем ответ за них — размышления
                head = L("**Ответ**\n\n", "**Answer**\n\n")    # уже закрыты, ответ начат (без заголовка откроют <think> снова)
                body["messages"] = [*messages, {"role": "assistant", "content": head, "thinking": L(
                    "Размышлять дальше некогда — отвечаю сразу по сообщениям.",
                    "No more time to think — answering right away from the messages.")}]
                yield {"t": head}
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
    elif st["provider"] == "openrouter":
        body = {"model": st["model"], "messages": messages, "stream": True, "temperature": st["temperature"],
                "max_tokens": budget, "usage": {"include": True}}
        lim = _limits("openrouter", st["model"])
        rs = _or_reasoning(think, lim) if can_think or lim.get("mandatory") else None
        if rs:
            body["reasoning"] = rs
        with _or_req("/chat/completions", body, timeout=900) as r:
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
                if ev.get("error"):
                    raise ValueError(str((ev["error"] or {}).get("message") or ev["error"])[:300])
                ch = (ev.get("choices") or [{}])[0]
                d = ch.get("delta") or {}
                out = {"t": d.get("content") or "", "think": d.get("reasoning") or "",
                       "tokens": (ev.get("usage") or {}).get("completion_tokens", 0),
                       "done_reason": ch.get("finish_reason") or ""}
                if (ev.get("usage") or {}).get("cost") is not None:
                    out["cost"] = float(ev["usage"]["cost"])
                yield out
    else:
        if can_think and not think and "qwen3" in st["model"].lower():
            messages = [dict(messages[0], content=messages[0]["content"] + "\n/no_think"), *messages[1:]]
        body = {"model": st["model"], "messages": messages, "stream": True, "temperature": st["temperature"],
                "max_tokens": budget, "usage": {"include": True}}
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
