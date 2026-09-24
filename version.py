#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Версия и имя программы — одни на все модули, страницы, установщик и пакеты.

Нумерация: 1.0.<номер коммита, считая с нуля>. Первый коммит — 1.0.0, второй — 1.0.1,
и так дальше, каждый коммит в истории +1 (слияния тоже коммиты). Руками номер не меняют:
  • в клоне git он считается сам: git rev-list --count HEAD минус один;
  • в пакете (.deb, .rpm, zip, exe, msi) его вписывает сборка в файл VERSION рядом с кодом
    (tools/build.py), потому что там нет .git;
  • ни того ни другого (архив исходников с GitHub) — 1.0.0+unknown.
Выпуск — тег vX.Y.Z на коммите, чей номер это и есть (скилл release). SERIES («1.0») меняют
только при несовместимых изменениях, по решению владельца.

APP_ID — техническое имя: папки данных (~/.local/share/<APP_ID>), имена сервисов
systemd (<APP_ID>.service, <APP_ID>-widget.service), префикс переменных окружения.
LEGACY_IDS — прежние имена: их папки данных и сервисы при установке переезжают на новое
(paths.migrate_old_app_dirs, install.sh).
"""

import os
import subprocess

APP_NAME = "messhub"
APP_ID = "messhub"
LEGACY_IDS = ("express-msgs",)      # до переименования проект назывался eXpress-msgs
SERIES = "1.0"                      # МАЖОР.МИНОР; третье число — номер коммита

HERE = os.path.dirname(os.path.abspath(__file__))


def _stamped():
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _from_git():
    """Номер коммита — только если эта папка и есть корень репозитория программы
    (а не, скажем, чей-то домашний каталог под git, куда распаковали архив)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def git(*args):
        return subprocess.run(["git", "-C", HERE, *args], capture_output=True, text=True,
                              timeout=5, env=env).stdout.strip()
    try:
        if os.path.realpath(git("rev-parse", "--show-toplevel") or "/nonexistent") != os.path.realpath(HERE):
            return None
        n = int(git("rev-list", "--count", "HEAD"))
        return f"{SERIES}.{n - 1}" if n > 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def next_version():
    """Какой номер получит следующий коммит — для записи в CHANGELOG перед выпуском."""
    cur = _from_git()
    return f"{SERIES}.{int(cur.rsplit('.', 1)[1]) + 1}" if cur else f"{SERIES}.0"


__version__ = _stamped() or _from_git() or f"{SERIES}.0+unknown"


def version_line():
    return f"{APP_NAME} {__version__}"


if __name__ == "__main__":
    import sys
    print(next_version() if "--next" in sys.argv else __version__)
