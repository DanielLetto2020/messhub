#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка для macOS (Apple Silicon) — только на Mac (в CI: packages.yml, задание mac). Зовётся из
tools/build.py mac; нужны Python 3.9+ и pip install -r packaging/macos/requirements.txt pyinstaller.

Что получается в dist/:
  messhub-<v>-macos-arm64.dmg   образ диска: перетащить messhub в «Программы»
  messhub-<v>-macos-arm64.zip   то же приложение архивом
Подпись — ad-hoc (codesign --sign -), без платного Apple Developer ID. Поэтому при первом запуске
macOS предупредит, что не может проверить разработчика, и откроется программа через «Системные
настройки → Конфиденциальность и безопасность → Всё равно открыть» (или xattr, см. README).
Подпись должна быть целой: с «битой» macOS пишет «повреждено» и не даёт открыть вовсе, поэтому
после всех правок пакет подписывается заново и проверяется codesign --verify --deep --strict.
"""

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")
BUNDLE_ID = "io.github.danielletto2020.messhub"
ARCH = "arm64"
MIN_MACOS = "14.0"
README_DMG = """messhub {v} - macOS (Apple Silicon), beta

RU
1. Перетащи messhub в папку «Программы» (Applications).
2. Открой messhub. macOS скажет, что не может проверить разработчика: нажми «Готово».
   Программа без платной подписи Apple - так macOS предупреждает о любой такой программе.
3. Системные настройки -> Конфиденциальность и безопасность -> внизу «Всё равно открыть» ->
   пароль -> «Открыть». (Или в Терминале: xattr -dr com.apple.quarantine /Applications/messhub.app)
4. Разреши «Полный доступ к диску» (messhub сам откроет этот раздел): macOS хранит уведомления
   в защищённой базе, messhub её только читает. Затем перезапусти messhub.
Всё остаётся на этом Mac. Подробно: https://github.com/DanielLetto2020/messhub#macos-бета-apple-silicon

EN
1. Drag messhub into Applications.
2. Open messhub. macOS says it can't verify the developer: press "Done".
   The app has no paid Apple signature - macOS warns about any such app.
3. System Settings -> Privacy & Security -> at the bottom "Open Anyway" -> password -> "Open".
   (Or in Terminal: xattr -dr com.apple.quarantine /Applications/messhub.app)
4. Allow "Full Disk Access" (messhub opens that pane itself): macOS keeps notifications in a
   protected database, messhub only reads it. Then restart messhub.
Everything stays on this Mac. Details: https://github.com/DanielLetto2020/messhub/blob/main/README.en.md#macos-beta-apple-silicon
"""


def run(args, **kw):
    print("$", " ".join(args), flush=True)
    return subprocess.run(args, check=True, **kw)


def pyinstaller(src, v):
    """messhub.app (оконная сборка) и рядом с ним внутри — консольная обёртка messhub-run."""
    data = [f for f in os.listdir(src) if os.path.isfile(os.path.join(src, f)) and not f.endswith((".py", ".sh"))]
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
            "--name", "messhub", "--icon", os.path.join(src, "icons", "messhub.icns"),
            "--osx-bundle-identifier", BUNDLE_ID, "--target-architecture", ARCH,
            "--distpath", os.path.join(DIST, "mac"), "--workpath", os.path.join(src, "_build"),
            "--specpath", os.path.join(src, "_build"),
            "--collect-all", "webview",
            "--add-data", f"{os.path.join(src, 'icons')}{os.pathsep}icons",
            "--add-data", f"{os.path.join(src, 'web')}{os.pathsep}web"]
    for f in data:
        args += ["--add-data", f"{os.path.join(src, f)}{os.pathsep}."]
    args.append(os.path.join(src, "messhub_mac.py"))
    run(args, cwd=src)
    app = os.path.join(DIST, "mac", "messhub.app")
    if not os.path.exists(os.path.join(app, "Contents", "MacOS", "messhub")):
        raise SystemExit("PyInstaller не собрал messhub.app")
    # messhub-run — обёртка для колонки «Команды» (run.py, только stdlib), одним файлом рядом с messhub
    tmp = os.path.join(src, "_run")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
         "--name", "messhub-run", "--target-architecture", ARCH, "--distpath", tmp,
         "--workpath", os.path.join(src, "_build_run"), "--specpath", os.path.join(src, "_build_run"),
         os.path.join(src, "run.py")], cwd=src)
    shutil.copy2(os.path.join(tmp, "messhub-run"), os.path.join(app, "Contents", "MacOS", "messhub-run"))
    return app


def info_plist(app, v):
    """Номер версии, название, минимальная macOS — в Info.plist (PyInstaller пишет 0.0.0)."""
    path = os.path.join(app, "Contents", "Info.plist")
    with open(path, "rb") as f:
        info = plistlib.load(f)
    info.update({"CFBundleName": "messhub", "CFBundleDisplayName": "messhub",
                 "CFBundleShortVersionString": v, "CFBundleVersion": v,
                 "LSMinimumSystemVersion": MIN_MACOS, "NSHighResolutionCapable": True,
                 "LSApplicationCategoryType": "public.app-category.productivity",
                 "NSHumanReadableCopyright": "© 2026 Кузьминский Максим i@m-letto.ru · Apache-2.0"})
    with open(path, "wb") as f:
        plistlib.dump(info, f)


def sign(app):
    """Подпись ad-hoc всего пакета заново (после правок Info.plist и messhub-run) и проверка."""
    run(["codesign", "--force", "--deep", "--sign", "-", "--timestamp=none", app])
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app])


def zip_app(app, v):
    out = os.path.join(DIST, f"messhub-{v}-macos-{ARCH}.zip")
    if os.path.exists(out):
        os.remove(out)
    run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, out])   # ditto сохраняет ссылки и подпись
    return out


def dmg(app, v):
    out = os.path.join(DIST, f"messhub-{v}-macos-{ARCH}.dmg")
    if os.path.exists(out):
        os.remove(out)
    with tempfile.TemporaryDirectory() as tmp:
        stage = os.path.join(tmp, "messhub")
        os.makedirs(stage)
        run(["ditto", app, os.path.join(stage, "messhub.app")])
        os.symlink("/Applications", os.path.join(stage, "Applications"))
        with open(os.path.join(stage, "README.txt"), "w", encoding="utf-8") as f:
            f.write(README_DMG.format(v=v))
        run(["hdiutil", "create", "-volname", f"messhub {v}", "-srcfolder", stage, "-ov", "-format", "UDZO", out])
    return out


def build(v, files, stage):
    if sys.platform != "darwin":
        raise SystemExit("Сборка для macOS — только на Mac (или в GitHub Actions)")
    os.makedirs(DIST, exist_ok=True)
    shutil.rmtree(os.path.join(DIST, "mac"), ignore_errors=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src")
        stage(src, files, v)
        app = pyinstaller(src, v)
    info_plist(app, v)
    sign(app)
    return [dmg(app, v), zip_app(app, v)]
