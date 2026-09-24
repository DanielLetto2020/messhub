#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка для Windows 10/11 — только на Windows (в CI: .github/workflows/release.yml). Зовётся
из tools/build.py windows; нужны Python 3.9+, pip install -r requirements-windows.txt pyinstaller
и WiX Toolset 5 (dotnet tool install --global wix) для .msi.

Что получается в dist/:
  messhub-<v>-windows-portable.zip   папка messhub с messhub.exe; данные — рядом (portable.txt)
  messhub-<v>-windows-setup.bat      установка для себя без прав администратора (скачает zip)
  messhub-<v>-windows-x64.msi        обычный установщик: меню «Пуск», запуск вместе с Windows
"""

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
RELEASES = "https://github.com/DanielLetto2020/messhub/releases/download"


def pyinstaller(src, v):
    """messhub.exe (оконная сборка, папкой: так быстрее запуск и меньше ложных тревог антивирусов)."""
    data = [f for f in os.listdir(src) if os.path.isfile(os.path.join(src, f)) and not f.endswith((".py", ".sh"))]
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
            "--name", "messhub", "--icon", os.path.join(src, "packaging", "icons", "messhub.ico"),
            "--distpath", os.path.join(DIST, "win"), "--workpath", os.path.join(src, "_build"),
            "--specpath", os.path.join(src, "_build"),
            "--collect-all", "winrt", "--collect-all", "webview",
            "--add-data", f"{os.path.join(src, 'packaging', 'icons')}{os.pathsep}packaging/icons"]
    for f in data:
        args += ["--add-data", f"{os.path.join(src, f)}{os.pathsep}."]
    args.append(os.path.join(src, "messhub_win.py"))
    subprocess.run(args, check=True, cwd=src)
    app = os.path.join(DIST, "win", "messhub")
    if not os.path.exists(os.path.join(app, "messhub.exe")):
        raise SystemExit("PyInstaller не собрал messhub.exe")
    return app


def portable_zip(app, v):
    out = os.path.join(DIST, f"messhub-{v}-windows-portable.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for d, _, fs in os.walk(app):
            for f in fs:
                p = os.path.join(d, f)
                z.write(p, os.path.join("messhub", os.path.relpath(p, app)))
        z.write(os.path.join(ROOT, "packaging", "windows", "portable.txt"), "messhub/portable.txt")
    return out


def setup_bat(v):
    with open(os.path.join(ROOT, "packaging", "windows", "setup.bat.in"), encoding="utf-8") as f:
        text = f.read().replace("@VERSION@", v).replace("@URL@", RELEASES)
    out = os.path.join(DIST, f"messhub-{v}-windows-setup.bat")
    with open(out, "w", encoding="ascii", newline="\r\n") as f:     # cmd.exe читает CRLF и ASCII надёжнее всего
        f.write(text)
    return out


def msi(app, v):
    wix = shutil.which("wix")
    if not wix:
        print("msi пропущен: нет WiX (dotnet tool install --global wix)")
        return None
    out = os.path.join(DIST, f"messhub-{v}-windows-x64.msi")
    subprocess.run([wix, "build", os.path.join(ROOT, "packaging", "windows", "messhub.wxs"), "-arch", "x64",
                    "-d", f"Version={v}", "-d", f"Icon={os.path.join(ROOT, 'packaging', 'icons', 'messhub.ico')}",
                    "-bindpath", f"app={app}", "-o", out], check=True)
    return out


def build(v, files, stage):
    if os.name != "nt":
        raise SystemExit("Сборка для Windows — только на Windows (или в GitHub Actions)")
    os.makedirs(DIST, exist_ok=True)
    shutil.rmtree(os.path.join(DIST, "win"), ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src")
        stage(src, files, v)
        app = pyinstaller(src, v)
    return [p for p in (portable_zip(app, v), setup_bat(v), msi(app, v)) if p]
