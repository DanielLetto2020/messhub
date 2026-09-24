#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сборка пакетов messhub для выпуска. Всё собирается в dist/ из файлов, которые отслеживает git,
с номером версии, вписанным в файл VERSION (в самом репозитории его нет — номер = число коммитов).

    python3 tools/build.py tar             # messhub-<v>.tar.gz — исходники + ./install.sh
    python3 tools/build.py deb             # messhub_<v>_all.deb — Debian, Ubuntu, Mint (нужен dpkg-deb)
    python3 tools/build.py rpm             # messhub-<v>-1.noarch.rpm — Fedora, openSUSE (нужен rpmbuild)
    python3 tools/build.py linux           # всё три
    python3 tools/build.py windows         # на Windows: messhub.exe (PyInstaller) → zip, msi, bat
    python3 tools/build.py stage --out DIR # только разложить файлы программы в DIR (для своих сборок)

Пакеты .deb/.rpm ставят программу в /usr/lib/messhub, команду /usr/bin/messhub, ярлык в меню
и юниты systemd --user в /usr/lib/systemd/user. Включает автозапуск сам человек — первым запуском
«messhub» из меню (или командой messhub): для каждого пользователя отдельно, без sudo.
"""

import argparse
import gzip
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import version  # noqa: E402

DIST = os.path.join(ROOT, "dist")
# что нужно программе во время работы (остальное — тесты, инструменты, документация)
SKIP_PREFIX = ("tests/", "tools/", "docs/", ".github/")
SKIP_FILES = {".gitignore", "CONTRIBUTING.md", "SECURITY.md", "requirements-windows.txt"}
LINUX_ONLY_SKIP = ("winwidget.py", "wincatcher.py", "messhub_win.py", "packaging/windows/")
DEB_DEPENDS = ("python3 (>= 3.9), python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1, "
               "dbus-bin | dbus")
DEB_RECOMMENDS = "gir1.2-wnck-3.0, libnotify-bin, gnome-session-canberra | pipewire-bin"
RPM_REQUIRES = ("python3 >= 3.9", "python3-gobject", "gtk3", "webkit2gtk4.1", "dbus-tools")
RPM_RECOMMENDS = ("libwnck3", "libnotify")
SUMMARY = "Desktop notification board: all notifications in one window, stored locally"
DESCRIPTION = ("messhub keeps the notifications your Linux desktop shows (messengers, mail, browser,\n"
               "your scripts) in a local database and shows them on a translucent board with a column\n"
               "per app: mail-like rules, search, statistics, snooze, pin. Nothing leaves the computer.")
HOMEPAGE = "https://github.com/DanielLetto2020/messhub"
MAINTAINER = "Кузьминский Максим Павлович <i@m-letto.ru>"


def tracked():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z"], capture_output=True, text=True, check=True).stdout
    return [f for f in out.split("\0") if f and os.path.isfile(os.path.join(ROOT, f))]


def runtime_files(windows=False):
    files = [f for f in tracked() if not f.startswith(SKIP_PREFIX) and f not in SKIP_FILES]
    if not windows:
        files = [f for f in files if not f.startswith(LINUX_ONLY_SKIP)]
    return files


def ver():
    v = version.__version__
    if "+" in v:
        raise SystemExit(f"Не знаю номер версии ({v}): собирать нужно из клона git")
    return v


def stage(dest, files, v):
    """Разложить файлы программы в dest и вписать номер версии."""
    for f in files:
        os.makedirs(os.path.dirname(os.path.join(dest, f)) or dest, exist_ok=True)
        shutil.copy2(os.path.join(ROOT, f), os.path.join(dest, f))
    with open(os.path.join(dest, "VERSION"), "w", encoding="utf-8") as fh:
        fh.write(v + "\n")


def render_unit(tpl, app_dir, python="/usr/bin/python3"):
    with open(os.path.join(ROOT, "packaging", "systemd", tpl), encoding="utf-8") as f:
        s = f.read()
    return (s.replace("@DIR@", app_dir).replace("@PYTHON@", python)
             .replace("@APP_ID@", version.APP_ID).replace("@APP_NAME@", version.APP_NAME))


def write(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


def linux_tree(root, v):
    """Общее дерево файлов для .deb и .rpm (корень файловой системы)."""
    app = "/usr/lib/messhub"
    stage(root + app, runtime_files(), v)
    for f in ("install.sh", "uninstall.sh", "README.md", "README.en.md", "CHANGELOG.md"):
        os.remove(root + app + "/" + f)                 # ставит менеджер пакетов; документы — в /usr/share/doc
    shutil.rmtree(root + app + "/packaging/systemd")
    shutil.rmtree(root + app + "/packaging/linux")
    write(root + "/usr/bin/messhub", open(os.path.join(ROOT, "packaging", "linux", "messhub.sh"),
                                          encoding="utf-8").read(), 0o755)
    write(root + "/usr/lib/systemd/user/messhub.service", render_unit("app.service.in", app))
    write(root + "/usr/lib/systemd/user/messhub-widget.service", render_unit("app-widget.service.in", app))
    write(root + "/usr/share/applications/messhub.desktop",
          open(os.path.join(ROOT, "packaging", "linux", "messhub.desktop"), encoding="utf-8").read())
    icons = os.path.join(ROOT, "packaging", "icons")
    for size in (16, 24, 32, 48, 64, 128, 256):
        d = f"{root}/usr/share/icons/hicolor/{size}x{size}/apps"
        os.makedirs(d, exist_ok=True)
        shutil.copy2(os.path.join(icons, f"messhub-{size}.png"), d + "/messhub.png")
    os.makedirs(root + "/usr/share/icons/hicolor/scalable/apps", exist_ok=True)
    shutil.copy2(os.path.join(icons, "messhub.svg"), root + "/usr/share/icons/hicolor/scalable/apps/messhub.svg")
    doc = root + "/usr/share/doc/messhub"
    os.makedirs(doc, exist_ok=True)
    for f in ("README.md", "README.en.md", "NOTICE", "LICENSE"):
        shutil.copy2(os.path.join(ROOT, f), doc)
    with open(os.path.join(ROOT, "CHANGELOG.md"), "rb") as src, gzip.open(doc + "/changelog.gz", "wb") as dst:
        dst.write(src.read())
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            os.chmod(os.path.join(dirpath, d), 0o755)
        for f in filenames:
            p = os.path.join(dirpath, f)
            if not p.startswith(root + "/usr/bin/"):
                os.chmod(p, 0o644)          # в пакете запускаемые только /usr/bin/*; hooks/*.sh подключают через source


def build_tar(v):
    name = f"messhub-{v}"
    out = os.path.join(DIST, f"{name}.tar.gz")
    with tempfile.TemporaryDirectory() as tmp:
        stage(os.path.join(tmp, name), runtime_files(), v)
        with tarfile.open(out, "w:gz") as tar:
            tar.add(os.path.join(tmp, name), arcname=name, filter=lambda ti: _owner(ti))
    return out


def _owner(ti):
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = "root"
    return ti


def build_deb(v):
    if not shutil.which("dpkg-deb"):
        raise SystemExit("Нужен dpkg-deb (пакет dpkg)")
    out = os.path.join(DIST, f"messhub_{v}_all.deb")
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "root")
        linux_tree(root, v)
        size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(root) for f in fs) // 1024
        write(root + "/DEBIAN/control", f"""Package: messhub
Version: {v}
Architecture: all
Maintainer: {MAINTAINER}
Installed-Size: {size}
Depends: {DEB_DEPENDS}
Recommends: {DEB_RECOMMENDS}
Section: utils
Priority: optional
Homepage: {HOMEPAGE}
Description: {SUMMARY}
""" + "".join(f" {line}\n" for line in DESCRIPTION.splitlines()))
        write(root + "/DEBIAN/postinst", "#!/bin/sh\nset -e\n"
              "command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true\n"
              "command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true\n"
              'echo "messhub: запусти «messhub» из меню приложений (или командой messhub) — появится доска"\n',
              0o755)
        write(root + "/DEBIAN/prerm", "#!/bin/sh\nset -e\n"
              "# у каждого пользователя свои сервисы; остановить можно только у себя: systemctl --user stop messhub\n"
              "exit 0\n", 0o755)
        subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", root, out], check=True,
                       stdout=subprocess.DEVNULL)
    return out


def build_rpm(v):
    if not shutil.which("rpmbuild"):
        raise SystemExit("Нужен rpmbuild (пакет rpm / rpm-build)")
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "root")
        linux_tree(root, v)
        files = []
        for d, _, fs in os.walk(root):
            for f in fs:
                p = os.path.join(d, f)[len(root):]
                files.append(("%doc " if p.startswith("/usr/share/doc/") else "") + f'"{p}"')
        spec = os.path.join(tmp, "messhub.spec")
        req = "\n".join(f"Requires: {r}" for r in RPM_REQUIRES)
        rec = "\n".join(f"Recommends: {r}" for r in RPM_RECOMMENDS)
        date = time.strftime("%a %b %d %Y")
        write(spec, f"""Name: messhub
Version: {v}
Release: 1
Summary: {SUMMARY}
License: Apache-2.0
URL: {HOMEPAGE}
BuildArch: noarch
AutoReqProv: no
{req}
{rec}

%description
{DESCRIPTION}

%install
cp -a {root}/. %{{buildroot}}/

%post
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
exit 0

%files
%dir /usr/lib/messhub
{chr(10).join(sorted(files))}

%changelog
* {date} Кузьминский Максим Павлович <i@m-letto.ru> - {v}-1
- См. CHANGELOG.md
""")
        top = os.path.join(tmp, "rpmbuild")
        subprocess.run(["rpmbuild", "-bb", "--quiet", "--define", f"_topdir {top}",
                        "--define", "_build_id_links none", spec], check=True)
        built = [os.path.join(d, f) for d, _, fs in os.walk(os.path.join(top, "RPMS")) for f in fs if f.endswith(".rpm")]
        out = os.path.join(DIST, os.path.basename(built[0]))
        shutil.copy2(built[0], out)
    return out


def main():
    ap = argparse.ArgumentParser(description="Сборка пакетов messhub")
    ap.add_argument("what", choices=("tar", "deb", "rpm", "linux", "windows", "stage"))
    ap.add_argument("--out", help="для stage: куда разложить")
    a = ap.parse_args()
    v = ver()
    os.makedirs(DIST, exist_ok=True)
    if a.what == "stage":
        stage(a.out, runtime_files(windows=sys.platform == "win32"), v)
        print(a.out)
        return
    if a.what == "windows":
        import build_windows          # tools/build_windows.py — только на Windows
        for p in build_windows.build(v, runtime_files(windows=True), stage):
            print(p)
        return
    todo = {"tar": [build_tar], "deb": [build_deb], "rpm": [build_rpm],
            "linux": [build_tar, build_deb, build_rpm]}[a.what]
    for fn in todo:
        if fn is build_rpm and a.what == "linux" and not shutil.which("rpmbuild"):
            print("rpm пропущен: нет rpmbuild")
            continue
        print(fn(v))


if __name__ == "__main__":
    main()
