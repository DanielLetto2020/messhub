#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Можно ли это публиковать? Проверка файлов репозитория и сообщений коммитов.

    python3 tools/check_public.py              # все файлы, которые отслеживает git
    python3 tools/check_public.py --staged     # только то, что уходит в коммит (удобно в git-хуке pre-commit)
    python3 tools/check_public.py --commits    # ещё и сообщения коммитов (перед публикацией, в CI)
    python3 tools/check_public.py --commits origin/main..HEAD

Что ищет (правила — CONTRIBUTING.md, «Что можно публиковать»):
  • файлы, которым не место в репозитории: базы, логи, секреты, состояние окна;
  • в тексте: домашние папки (/home/<имя>/…), токены ботов, пароли и ключи, чужие e-mail
    (разрешены example.com/.org/.net, noreply GitHub и адрес автора из NOTICE);
  • строки из личного стоп-листа .public-deny (одна на строку, файл в .gitignore — его
    содержимое в репозиторий не попадает): имя пользователя, рабочие названия и т.п.
Код выхода 1 — нашлось что-то; вывод говорит, где и что.
"""

import argparse
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BAD_NAMES = re.compile(r"(^|/)(telegram-forward\.json|ingest\.json|mail\.json|widget-state\.json|"
                       r"widget-[\w-]+\.json|\.public-deny|\.env(\..*)?)$"
                       r"|\.(db|db-wal|db-shm|sqlite3?|log|pem|key|p12)$")
HOME_PATH = re.compile(r"(/home/|/Users/)(?!<|\.\.\.|…|user\b|username\b|runner\b)[A-Za-z_][\w.-]*/")
BOT_TOKEN = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
SECRET = re.compile(r"""(?i)\b(api[_-]?key|secret|passw(or)?d|token)\b["']?\s*[:=]\s*["']([^"'\s<>{}$]{12,})["']""")
SAFE_SECRET = re.compile(r"(?i)demo|example|fake|not-real|dummy|test|xxx|<")
EMAIL = re.compile(r"\b[\w.+-]+@(?:[a-z0-9](?:[\w-]*[a-z0-9])?\.)+[a-z]{2,}\b", re.I)   # домен — не с дефиса
SAFE_MAIL = re.compile(r"@(example\.(com|org|net)|users\.noreply\.github\.com)$", re.I)
TEXT_EXT = {".py", ".md", ".html", ".js", ".sh", ".sql", ".yml", ".yaml", ".json", ".in", ".txt", ".cfg",
            ".toml", ".ini", ".service", ""}


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, check=True).stdout


def files(staged):
    if staged:
        out = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
    else:
        out = git("ls-files", "-z")
    return [f for f in out.split("\0") if f]


def author_mails():
    try:
        with open(os.path.join(ROOT, "NOTICE"), encoding="utf-8") as f:
            return {m.group(0).lower() for m in EMAIL.finditer(f.read())}
    except OSError:
        return set()


def deny_list():
    """Стоп-лист: целые слова без учёта регистра («ivan» не ловится в «ivanov»)."""
    try:
        with open(os.path.join(ROOT, ".public-deny"), encoding="utf-8") as f:
            words = [s.strip() for s in f if s.strip() and not s.startswith("#")]
    except OSError:
        return []
    return [re.compile(r"(?<![\w])" + re.escape(w) + r"(?![\w])", re.I) for w in words]


def read(path, staged):
    if staged:   # то, что именно уходит в коммит, а не рабочая копия
        return subprocess.run(["git", "-C", ROOT, "show", f":{path}"], capture_output=True).stdout
    with open(os.path.join(ROOT, path), "rb") as f:
        return f.read()


def check_text(path, text, problems, allowed_mail, deny):
    for no, line in enumerate(text.splitlines(), 1):
        where = f"{path}:{no}"
        if HOME_PATH.search(line):
            problems.append(f"{where}: домашняя папка в пути — замени на ~ или <папка>")
        if BOT_TOKEN.search(line):
            problems.append(f"{where}: похоже на токен Telegram-бота")
        m = SECRET.search(line)
        if m and not SAFE_SECRET.search(m.group(3)):
            problems.append(f"{where}: похоже на пароль/ключ ({m.group(1)})")
        for e in EMAIL.finditer(line):
            if not SAFE_MAIL.search(e.group(0)) and e.group(0).lower() not in allowed_mail:
                problems.append(f"{where}: e-mail {e.group(0)} — используй адреса @example.com")
        if any(d.search(line) for d in deny):
            problems.append(f"{where}: строка из .public-deny")


def check_commits(rng, problems, allowed_mail, deny):
    """Сообщения коммитов: стоп-лист и чужие адреса (сами файлы проверяет check_text)."""
    log = git("log", "--format=%H%x00%B%x1e", *([rng] if rng else []))
    for entry in filter(None, (x.strip("\n") for x in log.split("\x1e"))):
        sha, body = (entry.split("\x00") + [""])[:2]
        if any(d.search(body) for d in deny):
            problems.append(f"коммит {sha[:8]}: строка из .public-deny в сообщении")
        for e in EMAIL.finditer(body):
            if not SAFE_MAIL.search(e.group(0)) and e.group(0).lower() not in allowed_mail:
                problems.append(f"коммит {sha[:8]}: e-mail {e.group(0)} в сообщении")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--staged", action="store_true", help="только файлы, подготовленные к коммиту")
    ap.add_argument("--commits", nargs="?", const="", default=None, metavar="ДИАПАЗОН",
                    help="проверить и сообщения коммитов (по умолчанию — вся история)")
    a = ap.parse_args()
    problems, allowed, deny = [], author_mails(), deny_list()
    for path in files(a.staged):
        if BAD_NAMES.search(path):
            problems.append(f"{path}: такой файл в репозиторий не кладём (см. .gitignore)")
            continue
        ext = os.path.splitext(path)[1].lower()
        data = read(path, a.staged)
        if len(data) > 5 * 1024 * 1024:
            problems.append(f"{path}: больше 5 МБ")
        if ext in TEXT_EXT:
            check_text(path, data.decode("utf-8", "replace"), problems, allowed, deny)
        elif deny and ext not in (".png", ".jpg", ".webp", ".gif"):
            text = data.decode("utf-8", "replace")
            if any(d.search(text) for d in deny):
                problems.append(f"{path}: строка из .public-deny")
    if a.commits is not None:
        check_commits(a.commits, problems, allowed, deny)
    for p in problems:
        print("✕", p)
    if problems:
        print(f"\nНайдено: {len(problems)}. Правила — CONTRIBUTING.md, «Что можно публиковать»")
        return 1
    print("✓ публиковать можно" + (f" (стоп-лист: {len(deny)})" if deny else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
