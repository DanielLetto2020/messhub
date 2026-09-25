#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Умный поиск (RAG) — необязательный, целиком локальный, через Ollama.

Без него работает обычный поиск (подстрока без учёта регистра по тексту, чату и
отправителю). Кому нужен поиск «по смыслу» и ответы на вопросы по переписке —
включает его в настройках:

  1. «Установить» — Ollama (http://127.0.0.1:11434, или OLLAMA_HOST) скачивает модель
     векторов (по умолчанию bge-m3 — многоязычная, хорошо понимает русский, ~1.2 ГБ).
  2. Фоновый цикл понемногу считает векторы всех сообщений (таблица embeddings).
  3. Поиск: вектор запроса → ближайшие сообщения по косинусной близости.
  4. «Спросить»: найденные сообщения + вопрос → чат-модель Ollama (выбирается в
     настройках, по умолчанию первая не-векторная) → ответ со ссылками на сообщения.

Всё остаётся на компьютере: Ollama — локальный сервер. Векторы хранятся в той же
базе; «Выключить» может их удалить.

Сбои сами себя лечат: bge-m3 в Ollama на отдельных текстах выдаёт NaN, и Ollama отвечает 500 на всю
порцию. Тогда порция считается по одному сообщению, сбойное — по кускам (вектор — среднее кусков, что
посчитались); не вышло совсем — строка с пустым вектором («пропущено»), чтобы не держать очередь.
Пропущенные пробуются снова при запуске сервиса и раз в сутки. Ollama недоступна — повтор с
нарастающей паузой (до 5 минут), ошибка исчезает сама, как только векторы снова считаются. Считается на чистом Python (numpy не нужен):
на 10 тыс. сообщений поиск — около секунды.
"""

import heapq
import json
import math
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from array import array
from operator import mul

import rules
from i18n import L

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
EMBED_HINTS = ("embed", "bge", "e5", "minilm", "gte", "nomic", "mxbai", "arctic")

state = {"installing": False, "progress": "", "error": "", "retry_at": 0}   # для страницы настроек
_lock = threading.Lock()


def _call(path, body=None, timeout=30, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(OLLAMA + path, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def models():
    """Модели в Ollama → (список имён, ошибка)."""
    try:
        return [m["name"] for m in _call("/api/tags", timeout=4).get("models", [])], ""
    except (OSError, ValueError, urllib.error.URLError) as e:
        return [], str(e)


def _is_embed(name):
    return any(h in name.lower() for h in EMBED_HINTS)


def _has(names, model):
    return any(n == model or n.split(":")[0] == model.split(":")[0] for n in names)


def status(conn):
    prefs = rules.get_prefs(conn)["rag"]
    names, err = models()
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    done, skipped = conn.execute("SELECT COALESCE(SUM(length(vec) > 0), 0), COALESCE(SUM(length(vec) = 0), 0) "
                                 "FROM embeddings WHERE model = ?", (prefs["model"],)).fetchone()
    return {"enabled": prefs["enabled"], "model": prefs["model"], "chat_model": prefs["chat_model"],
            "ollama": not err, "ollama_error": err, "model_installed": _has(names, prefs["model"]),
            "chat_models": [n for n in names if not _is_embed(n)],
            "embed_models": [n for n in names if _is_embed(n)],
            "indexed": done, "skipped": skipped, "total": total, **state,
            "retry_in": max(0, int(state["retry_at"] - time.time())) if state["error"] else 0}


def install(db_path, model, chat_model=""):
    """Скачать модель векторов (в фоне, с прогрессом) и включить умный поиск."""
    if state["installing"]:
        return

    def work():
        state.update(installing=True, progress=L("начинаю…", "starting…"), error="")
        try:
            req = urllib.request.Request(OLLAMA + "/api/pull", method="POST",
                                         data=json.dumps({"model": model, "stream": True}).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=3600) as r:
                for line in r:
                    ev = json.loads(line or b"{}")
                    if ev.get("error"):
                        raise RuntimeError(ev["error"])
                    if ev.get("total"):
                        state["progress"] = f"{ev.get('status', '')} {100 * ev.get('completed', 0) // ev['total']}%"
                    else:
                        state["progress"] = ev.get("status", "")
            conn = sqlite3.connect(db_path, timeout=5)
            try:
                old = rules.get_prefs(conn)["rag"]
                if old["model"] != model:     # векторы другой модели несравнимы — удаляем
                    conn.execute("DELETE FROM embeddings WHERE model != ?", (model,))
                rules.set_prefs(conn, {"rag": {"enabled": True, "model": model,
                                               "chat_model": chat_model or old["chat_model"]}})
                conn.commit()
            finally:
                conn.close()
            state["progress"] = L("готово — считаю векторы сообщений", "done — indexing messages")
        except Exception as e:  # сеть, Ollama не запущена, нет такой модели
            state["error"] = str(e)
        finally:
            state["installing"] = False
    threading.Thread(target=work, name="rag-install", daemon=True).start()


def disable(conn, drop):
    p = rules.get_prefs(conn)["rag"]
    rules.set_prefs(conn, {"rag": dict(p, enabled=False)})
    if drop:
        conn.execute("DELETE FROM embeddings")


def remove_model(model):
    _call("/api/delete", {"model": model}, method="DELETE")


def _text(chat, sender, message):
    who = sender if sender and sender != chat else ""
    return f"{chat or ''}{' · ' + who if who else ''}: {message or ''}"[:2000]


def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return array("f", (x / n for x in v))


def _embed(model, texts):
    return [_norm(v) for v in _call("/api/embed", {"model": model, "input": texts}, timeout=120)["embeddings"]]


def _bad_input(e):
    """Ollama не смогла посчитать именно этот текст (NaN у bge-m3 и т.п.), а не лежит сама."""
    return isinstance(e, urllib.error.HTTPError) and e.code in (400, 500)


def _embed_one(model, text):
    """Одно сообщение, если порция не посчиталась: целиком, иначе среднее по кускам, что считаются.
    → вектор или None (пропустить)."""
    try:
        return _embed(model, [text])[0]
    except urllib.error.HTTPError as e:
        if not _bad_input(e):
            raise
    parts = [x for x in re.split(r"(?<=[.!?…\n])\s+", text) if x.strip()]   # предложения и строки
    if len(parts) < 2:
        parts = [text[i:i + 60] for i in range(0, len(text), 60)]
    acc = None
    for part in parts[:40]:
        try:
            v = _embed(model, [part])[0]
        except urllib.error.HTTPError as e:
            if not _bad_input(e):
                raise
            continue
        acc = list(v) if acc is None else [a + b for a, b in zip(acc, v)]
    return _norm(acc) if acc else None


def human_error(e):
    """Ошибка фонового подсчёта — понятными словами."""
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = json.loads(e.read() or b"{}").get("error", "")
        except Exception:             # тела может не быть вовсе (разные версии Python)
            body = ""
        if e.code == 404 or "not found" in str(body):
            return L("модели векторов нет в Ollama — нажми «Установить и включить»",
                     "the embedding model is missing in Ollama — press “Install and enable”")
        return f"Ollama: HTTP {e.code}" + (f" ({str(body)[:200]})" if body else "")
    s = str(getattr(e, "reason", "") or e)
    if "refused" in s.lower() or "10061" in s:
        return L("Ollama не запущена", "Ollama is not running")
    if "timed out" in s.lower():
        return L("Ollama не отвечает", "Ollama is not responding")
    return s[:300]


def retry_skipped(db_path):
    """Пропущенные сообщения — ещё раз в очередь (после обновления Ollama или модели могут посчитаться)."""
    conn = sqlite3.connect(db_path, timeout=5)
    try:
        n = conn.execute("DELETE FROM embeddings WHERE length(vec) = 0").rowcount
        conn.commit()
        return n
    finally:
        conn.close()


def index_step(db_path, batch=32):
    """Из фонового цикла: посчитать векторы для порции ещё не проиндексированных
    сообщений (сначала свежие). → сколько посчитано."""
    with _lock:
        conn = sqlite3.connect(db_path, timeout=5)
        try:
            p = rules.get_prefs(conn)["rag"]
            if not p["enabled"] or state["installing"]:
                return 0
            rows = conn.execute("""SELECT m.id, m.chat, m.sender, m.message FROM messages m
                                   LEFT JOIN embeddings e ON e.message_id = m.id AND e.model = ?
                                   WHERE e.message_id IS NULL ORDER BY m.id DESC LIMIT ?""",
                                (p["model"], batch)).fetchall()
            if not rows:
                return 0
            texts = [_text(c, s, m) for _, c, s, m in rows]
            try:
                vecs = _embed(p["model"], texts)
            except urllib.error.HTTPError as e:
                if not _bad_input(e):
                    raise
                vecs = [_embed_one(p["model"], x) for x in texts]     # одно сбойное не держит всю порцию
            conn.executemany("INSERT OR REPLACE INTO embeddings (message_id, model, vec) VALUES (?,?,?)",
                             [(r[0], p["model"], v.tobytes() if v else b"") for r, v in zip(rows, vecs)])
            conn.commit()
            state["error"] = ""
            return len(rows)
        finally:
            conn.close()


def search(conn, q, k=20):
    """Ближайшие по смыслу сообщения → [(близость, id)]."""
    p = rules.get_prefs(conn)["rag"]
    if not p["enabled"]:
        raise ValueError(L("Умный поиск выключен — включи его в «Поиск»",
                           "Smart search is off — enable it in “Search”"))
    qv = _embed(p["model"], [q])[0]
    best = []
    for mid, blob in conn.execute("SELECT message_id, vec FROM embeddings WHERE model = ?", (p["model"],)):
        if not blob:                  # пропущенное — вектора нет
            continue
        v = array("f")
        v.frombytes(blob)
        score = sum(map(mul, qv, v))
        if len(best) < k:
            heapq.heappush(best, (score, mid))
        elif score > best[0][0]:
            heapq.heapreplace(best, (score, mid))
    return sorted(best, reverse=True)


def ask(conn, question, rows_by_id):
    """Ответ на вопрос по найденным сообщениям. rows_by_id — {id: строка сообщения}."""
    p = rules.get_prefs(conn)["rag"]
    names, err = models()
    chat_model = p["chat_model"] or next((n for n in names if not _is_embed(n)), "")
    if not chat_model:
        raise ValueError(L("В Ollama нет чат-модели для ответов — поставь любую (ollama pull …)",
                           "No chat model in Ollama for answers — pull one (ollama pull …)"))
    ctx = "\n".join(f"[{m['id']}] {m['received_at']} · {m['src_name']} · {_text(m['chat'], m['sender'], m['message'])}"
                    for m in rows_by_id.values())
    system = L("Ты помощник по личной переписке пользователя. Отвечай кратко и только по приведённым "
               "сообщениям; если ответа в них нет — так и скажи. Ссылайся на сообщения номерами в "
               "квадратных скобках, например [12].",
               "You help the user with their own messages. Answer briefly and only from the messages "
               "given; if the answer is not there, say so. Cite messages by number in square brackets, "
               "e.g. [12].")
    user = L(f"Сообщения:\n{ctx}\n\nВопрос: {question}", f"Messages:\n{ctx}\n\nQuestion: {question}")
    r = _call("/api/chat", {"model": chat_model, "stream": False, "options": {"temperature": 0.2},
                            "messages": [{"role": "system", "content": system},
                                         {"role": "user", "content": user}]}, timeout=240)
    return r.get("message", {}).get("content", ""), chat_model
