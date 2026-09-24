#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
У всех ли строк интерфейса есть английский перевод?

    python3 tools/i18n_check.py

Собирает русские строки из widget.html и settings.html — t('…'), t(условие ? '…' : '…'),
data-t / data-t-title / data-t-ph / data-t-aria, словари, которые идут через t() (ACT, HINTS,
MAIL_PRESETS, …), — и сверяет с ключами EN в i18n.js. Справка (HELP) не проверяется: у неё
свой английский текст. Ещё ищет повторяющиеся ключи в EN. Нужен node (чтобы честно
выполнить i18n.js); без него ключи EN читаются регулярным выражением.
Код выхода 1 — есть пропуски или дубли.
"""

import collections
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ("app/web/widget.html", "app/web/settings.html", "app/web/message.html")
DICTS = ("ACT", "COLOR_NAMES", "HINTS", "MAIL_PRESETS", "SEC_NAMES", "ACT_WORD", "LOG_LVL", "LOG_SRC", "LOG_FILTERS")
LISTS = ("DOW", "DOW_LONG")
KEY_RE = re.compile(r"(?:^|[{,\s])'((?:[^'\\]|\\.)*)'\s*:", re.M)


def en_keys(js):
    body = js[js.index("const EN = {"):js.index("\n};")]
    dups = [k for k, n in collections.Counter(KEY_RE.findall(body)).items() if n > 1]
    if shutil.which("node"):
        code = js.replace("function translateDom", "function __unused") + "\nconsole.log(JSON.stringify(Object.keys(EN)))"
        out = subprocess.run(["node", "-e", code], capture_output=True, text=True)
        if out.returncode:
            sys.exit("i18n.js не выполняется:\n" + out.stderr)
        return set(json.loads(out.stdout)), dups
    return set(k.replace("\\'", "'") for k in KEY_RE.findall(body)), dups


def page_keys(src):
    keys = set()
    src = re.sub(r"const HELP = \{.*?\n\]\};", "", src, flags=re.S)
    keys.update(m.group(1).replace("\\'", "'") for m in re.finditer(r"\bt\(\s*'((?:[^'\\]|\\.)*)'", src))
    keys.update(re.findall(r'data-t(?:-title|-ph|-aria)?="([^"]*)"', src))
    for m in re.finditer(r"\bt\(([^()]*\?[^()]*)\)", src):
        keys.update(re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(1)))
    for name in DICTS:
        m = re.search(r"const " + name + r"\s*=\s*\{(.*?)\};", src, re.S)
        if m:
            keys.update(re.findall(r":\s*'((?:[^'\\]|\\.)*)'", m.group(1)))
    for name in LISTS:
        m = re.search(r"const " + name + r"\s*=\s*\[(.*?)\];", src, re.S)
        if m:
            keys.update(re.findall(r"'([^']*)'", m.group(1)))
    for m in re.finditer(r"mode\('\w+','([^']*)','([^']*)'\)", src):      # варианты в «Почте»
        keys.update(m.groups())
    for m in re.finditer(r"const hint=(.*?);\n", src, re.S):               # подсказки «нельзя закрыть»
        keys.update(re.findall(r"'([^']{8,})'", m.group(1)))
    return {k for k in keys if re.search("[а-яё]", k, re.I)}


def main():
    en, dups = en_keys(open(os.path.join(ROOT, "app", "web", "i18n.js"), encoding="utf-8").read())
    keys = set()
    for p in PAGES:
        keys |= page_keys(open(os.path.join(ROOT, p), encoding="utf-8").read())
    miss = sorted(keys - en)
    for k in miss:
        print("нет перевода:", k)
    for k in dups:
        print("ключ повторяется в EN:", k)
    print(f"{len(keys)} строк, без перевода {len(miss)}, повторов {len(dups)}")
    return 1 if miss or dups else 0


if __name__ == "__main__":
    sys.exit(main())
