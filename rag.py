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
базе; «Выключить» может их удалить. Считается на чистом Python (numpy не нужен):
на 10 тыс. сообщений поиск — около секунды.
"""

import heapq
import json
import math
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from array import array
from operator import mul

import catcher
import rules
from i18n import L

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
EMBED_HINTS = ("embed", "bge", "e5", "minilm", "gte", "nomic", "mxbai", "arctic")

state = {"installing": False, "progress": "", "error": ""}   # для страницы настроек
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
    done = conn.execute("SELECT COUNT(*) FROM embeddings WHERE model = ?", (prefs["model"],)).fetchone()[0]
    return {"enabled": prefs["enabled"], "model": prefs["model"], "chat_model": prefs["chat_model"],
            "ollama": not err, "ollama_error": err, "model_installed": _has(names, prefs["model"]),
            "chat_models": [n for n in names if not _is_embed(n)],
            "embed_models": [n for n in names if _is_embed(n)],
            "indexed": done, "total": total, **state}


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


def _embed(model, texts):
    vecs = _call("/api/embed", {"model": model, "input": texts}, timeout=120)["embeddings"]
    out = []
    for v in vecs:
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        out.append(array("f", (x / n for x in v)))
    return out


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
            vecs = _embed(p["model"], [_text(c, s, m) for _, c, s, m in rows])
            conn.executemany("INSERT OR REPLACE INTO embeddings (message_id, model, vec) VALUES (?,?,?)",
                             [(r[0], p["model"], v.tobytes()) for r, v in zip(rows, vecs)])
            conn.commit()
            return len(rows)
        finally:
            conn.close()


def search(conn, q, k=20, src=""):
    """Ближайшие по смыслу сообщения → [(близость, id)]."""
    p = rules.get_prefs(conn)["rag"]
    if not p["enabled"]:
        raise ValueError(L("Умный поиск выключен — включи его в «Поиск»",
                           "Smart search is off — enable it in “Search”"))
    qv = _embed(p["model"], [q])[0]
    best = []
    for mid, blob in conn.execute("SELECT message_id, vec FROM embeddings WHERE model = ?", (p["model"],)):
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
