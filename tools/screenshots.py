#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Скриншоты для README — на вымышленных данных (tools/demo_data.py), в настоящем WebKit.

    python3 tools/screenshots.py                  # ru и en → docs/screens/<lang>/*.png
    python3 tools/screenshots.py --lang ru --only widget,settings-mail

Что делает: для каждого языка собирает демо-папку во временном каталоге, поднимает на ней
serve.py (Ollama и Telegram — на заведомо мёртвом адресе, наружу ничего не ходит), запускает
виртуальный дисплей Xvfb и снимает страницы в окне WebKit с временным (ephemeral) профилем.
Перед каждым снимком пути подменяются на «~/…», а текст страницы проверяется: если на
снимок попадает домашняя папка, имя пользователя или папка с кодом — скрипт падает, и
картинка не сохраняется. Нужны Xvfb и то же, что для виджета (GTK 3, WebKit2GTK 4.1).
Самопроверка защиты: MESSHUB_SHOTS_SELFTEST=1 … --only settings-system — должно упасть.
"""

import argparse
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

DARK_DESK = ("document.documentElement.style.background='#0e1014';"
             "document.body.classList.remove('nohost');'ok'")
W, S = (1640, 470), (1150, 800)        # размер окна: виджет и настройки
IT = (1240, 470)                        # доска только с тематическими колонками
LANG_Q = {"ru": {"search": "созвон"}, "en": {"search": "call"}}


def plan(lang):
    """(имя файла, адрес, (ширина, высота), шаги) — шаг: JS-строка или пауза в мс."""
    q = LANG_Q[lang]
    return [
        ("widget", "/widget", W, [DARK_DESK, 500]),
        ("widget-why", "/widget", W, [DARK_DESK,
            "document.querySelector('.col[data-key=express] .grp [data-act=toggle]').click();'ok'", 500,
            "document.querySelector('.col[data-key=express] .msg.hl [data-act=why]').click();'ok'", 700]),
        ("widget-close", "/widget", W, [DARK_DESK,
            "document.querySelector('.col[data-key=telegram] [data-act=close-col]').click();'ok'", 800]),
        ("widget-snooze", "/widget", W, [DARK_DESK,
            "document.querySelector('.col[data-key=mail] .msg [data-act=snooze]').click();'ok'", 500]),
        ("widget-focus", "/widget", W, [DARK_DESK, "document.getElementById('focusBtn').click();'ok'", 500]),
        ("widget-privacy", "/widget", W, [DARK_DESK, "document.getElementById('eye').click();'ok'", 500]),
        ("settings-sources", "/settings#sources", S, [900]),
        ("settings-source", "/settings#source=express", (1150, 1080), [900]),
        ("settings-rule-editor", "/settings#source=express", S, [900,
            "document.getElementById('addRule').click();'ok'", 400,
            "document.querySelector('#nrEd [data-act=highlight]').click();'ok'", 300]),
        ("settings-rules", "/settings#rules", S, [900]),
        ("settings-profiles", "/settings#profiles", S, [900]),
        ("settings-mentions", "/settings#mentions", S, [900]),
        ("settings-search", "/settings#search", S, [900,
            f"document.getElementById('sQ').value={json.dumps(q['search'])};"
            "document.getElementById('sGo').click();'ok'", 900]),
        ("settings-look", "/settings#look", S, [900]),
        ("settings-stats", "/settings#stats", (1150, 1180), ["wait-for:.tile", 600]),
        ("settings-data", "/settings#data", S, ["wait-for:h3", 900]),
        ("settings-mail", "/settings#mail", S, [900]),
        ("settings-forward", "/settings#forward", S, [900]),
        ("settings-ingest", "/settings#ingest", S, [900]),
        ("settings-system", "/settings#system", (1150, 1000), ["wait-for:.check", 600]),
        ("settings-themed", "/settings#themed", (1150, 1240), ["wait-for:.tcard", 700]),
        ("settings-logs", "/settings#logs", S, ["wait-for:.lg", 600]),
        ("settings-help", "/settings#help", S, [900]),
        # в конце — снимки, которые меняют настройки демо-папки: ИТ-колонки (остальные скрыты), светлая тема
        ("widget-it", "/widget", IT, [
            "fetch('/api/prefs',{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({hidden_cols:['express','telegram','mail','max','whatsapp','other:ci']})})"
            ".then(()=>location.reload());'ok'", 2200, DARK_DESK,
            "document.querySelector('.col[data-key=containers] .msg [data-act=det]').click();'ok'", 500]),
        ("widget-full", "/widget", IT, [DARK_DESK, 600,
            "document.querySelector('.col[data-key=containers] .det [data-act=full]').click();'ok'", 500]),
        ("widget-light", "/widget", W, [
            "fetch('/api/prefs',{method:'POST',headers:{'Content-Type':'application/json'},"
            "body:JSON.stringify({theme:'light',opacity:0.9,hidden_cols:['containers','services','commands']})})"
            ".then(()=>location.reload());'ok'", 2200,
            "document.documentElement.style.background='#c9ced6';document.body.classList.remove('nohost');'ok'", 400]),
    ]


# ── окно WebKit (запускается отдельным процессом на виртуальном дисплее) ──────

def harness(plan_file):
    import gi
    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("WebKit2", "4.1")
    from gi.repository import Gdk, GLib, Gtk, WebKit2
    job = json.load(open(plan_file, encoding="utf-8"))
    Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
    win = Gtk.Window()
    masks, leaks = job["masks"], job["leaks"]
    # подмена путей встраивается в страницу ДО её скриптов и ловит каждый новый текст
    # (MutationObserver) — данные, пришедшие позже, тоже не успеют показаться как есть
    guard = ("(()=>{try{localStorage.clear();}catch(e){}"      # каждый кадр — с чистого листа (фокус, размытие)
             "const M=%s;const fix=n=>{let v=n.nodeValue;for(const [a,b] of M)v=v.split(a).join(b);"
             "if(v!==n.nodeValue)n.nodeValue=v;};const all=r=>{const w=document.createTreeWalker(r,NodeFilter.SHOW_TEXT);"
             "let n;while((n=w.nextNode()))fix(n);};new MutationObserver(ms=>{for(const m of ms){"
             "if(m.type==='characterData')fix(m.target);else m.addedNodes.forEach(n=>n.nodeType===3?fix(n):all(n));}})"
             ".observe(document,{subtree:true,childList:true,characterData:true});"
             "document.addEventListener('DOMContentLoaded',()=>all(document.body));})();" % json.dumps(masks))
    ucm = WebKit2.UserContentManager()
    ucm.add_script(WebKit2.UserScript(guard, WebKit2.UserContentInjectedFrames.ALL_FRAMES,
                                      WebKit2.UserScriptInjectionTime.START, None, None))
    web = WebKit2.WebView(web_context=WebKit2.WebContext.new_ephemeral(), user_content_manager=ucm)
    win.add(web)
    leak_js = ("(()=>{const L=%s;const t=document.body.innerText;"
               "return JSON.stringify(L.filter(x=>t.includes(x)));})()" % json.dumps(leaks))
    shots, state = job["shots"], {"i": -1, "failed": []}

    def js(code, then):
        def done(v, res):
            try:
                out = v.evaluate_javascript_finish(res).to_string()
            except Exception as e:  # noqa: BLE001 — ошибку шага показываем и идём дальше
                out = "ERR " + str(e)
            then(out)
        web.evaluate_javascript(code, -1, None, None, None, done)

    def next_shot():
        state["i"] += 1
        if state["i"] >= len(shots):
            Gtk.main_quit()
            return False
        name, url, size, steps = shots[state["i"]]
        win.resize(*size)
        win.show_all()
        web.load_uri(job["base"] + url)
        GLib.timeout_add(1500, run_steps, name, list(steps))
        return False

    def run_steps(name, steps):
        if not steps:
            js(leak_js, lambda found: snap(name, found))
            return False
        s = steps.pop(0)
        if isinstance(s, int):
            GLib.timeout_add(s, run_steps, name, steps)
        elif s.startswith("wait-for:"):          # ждать, пока на странице появится элемент (до 15 с)
            sel, tries = s[9:], [0]

            def poll():
                def got(out):
                    tries[0] += 1
                    if out == "true" or tries[0] > 75:
                        if out != "true":
                            print(f"  {name}: не дождался {sel}", flush=True)
                        GLib.timeout_add(300, run_steps, name, steps)
                    else:
                        GLib.timeout_add(200, poll)
                js(f"!!document.querySelector({json.dumps(sel)})", got)
                return False
            poll()
        else:
            js(s, lambda out: (out.startswith("ERR") and print(f"  {name}: шаг не сработал: {out}", flush=True),
                               GLib.timeout_add(150, run_steps, name, steps)))
        return False

    def fail(name, found):
        print(f"  ✕ {name}: на странице личное ({', '.join(found)}) — снимок НЕ сохранён", flush=True)
        state["failed"].append(name)

    def snap(name, found):
        found = json.loads(found) if found and found.startswith("[") else ["проверка не ответила"]
        if found:
            fail(name, found)
            GLib.timeout_add(100, next_shot)
            return
        gw = win.get_window()
        pb = Gdk.pixbuf_get_from_window(gw, 0, 0, gw.get_width(), gw.get_height())
        path = os.path.join(job["out"], name + ".png")
        pb.savev(path, "png", ["compression"], ["9"])

        def after(out):          # и после снимка: если что-то дорисовалось — файл удаляем
            late = json.loads(out) if out and out.startswith("[") else ["проверка не ответила"]
            if late:
                os.remove(path)
                fail(name, late)
            else:
                print(f"  ✓ {name}", flush=True)
            GLib.timeout_add(100, next_shot)
        js(leak_js, after)

    GLib.timeout_add(300, next_shot)
    Gtk.main()
    sys.exit(1 if state["failed"] else 0)


# ── оркестр: демо-папка, сервер, дисплей ─────────────────────────────────────

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def free_display():
    for n in range(90, 200):
        if not os.path.exists(f"/tmp/.X11-unix/X{n}") and not os.path.exists(f"/tmp/.X{n}-lock"):
            return f":{n}"
    raise SystemExit("Нет свободного номера дисплея для Xvfb")


def wait_http(url, timeout=15):
    t = time.time()
    while time.time() - t < timeout:
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return
        except OSError:
            time.sleep(0.2)
    raise SystemExit(f"Сервер не поднялся: {url}")


def fake_github(ver):
    """Локальный «GitHub»: последний выпуск = ver. На снимках — ✓ «последняя версия», без сети."""
    import http.server
    body = json.dumps({"tag_name": "v" + ver, "html_url": "https://github.com/DanielLetto2020/messhub/releases/latest"}).encode()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def shoot(lang, out_dir, only, display, ver):
    home = tempfile.mkdtemp(prefix=f"messhub-shots-{lang}-")
    gh, gh_url = fake_github(ver)
    # копия программы с номером будущего выпуска: снимки идут в тот же коммит, что и выпуск
    app = os.path.join(home, "app")
    shutil.copytree(os.path.join(HERE, "app"), app, ignore=shutil.ignore_patterns("__pycache__"))
    with open(os.path.join(app, "VERSION"), "w", encoding="utf-8") as f:
        f.write(ver + "\n")
    env = dict(os.environ, MESSHUB_HOME=home, OLLAMA_HOST="http://127.0.0.1:9", MESSHUB_UPDATE_URL=gh_url,
               MESSHUB_TG_API="http://127.0.0.1:9", MESSHUB_EXPORT_DIR=os.path.join(home, "Downloads"),
               MESSHUB_THEMED_DEMO="1")     # состояние docker/podman/systemd — выдуманное, настоящие не спрашиваем
    for k in ("MESSHUB_MAIL_CFG", "MESSHUB_FORWARD_CFG"):
        env.pop(k, None)
    os.makedirs(env["MESSHUB_EXPORT_DIR"])
    db = subprocess.run([PY, os.path.join(HERE, "tools", "demo_data.py"), "--home", home, "--lang", lang],
                        env=env, check=True, capture_output=True, text=True).stdout.strip()
    port = free_port()
    srv = subprocess.Popen([PY, os.path.join(app, "serve.py"), "--db", db, "--port", str(port)],
                           env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        base = f"http://127.0.0.1:{port}"
        wait_http(base + "/api/version")
        urllib.request.urlopen(base + "/api/update", timeout=5).read()          # запустить проверку версии
        for _ in range(50):
            if json.load(urllib.request.urlopen(base + "/api/update", timeout=5)).get("latest"):
                break
            time.sleep(0.1)
        user_home = os.path.expanduser("~")
        dl = "~/Загрузки" if lang == "ru" else "~/Downloads"
        masks = [[app, "~/messhub/app"], [os.path.join(home, "share"), "~/.local/share/messhub"],
                 [os.path.join(home, ".config"), "~/.config/messhub"],
                 [os.path.join(home, ".cache"), "~/.cache/messhub"],
                 [env["MESSHUB_EXPORT_DIR"], dl], [HERE, "~/messhub"], [user_home, "~"]]
        leaks = sorted({user_home, getpass.getuser(), home, HERE, tempfile.gettempdir() + "/"} - {""}, key=len)
        if os.environ.get("MESSHUB_SHOTS_SELFTEST"):   # самопроверка: без подмены снимок «Системы» обязан упасть
            masks = []
        shots = [s for s in plan(lang) if not only or s[0] in only]
        os.makedirs(out_dir, exist_ok=True)
        pf = os.path.join(home, "plan.json")
        with open(pf, "w", encoding="utf-8") as f:
            json.dump({"base": base, "out": out_dir, "shots": shots, "masks": masks, "leaks": leaks}, f)
        print(f"{lang}: {len(shots)} снимков → {out_dir}", flush=True)
        r = subprocess.run([PY, __file__, "--harness", pf], env=dict(env, DISPLAY=display))
        return r.returncode
    finally:
        srv.terminate()
        srv.wait(5)
        gh.shutdown()
        shutil.rmtree(home, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Скриншоты messhub на вымышленных данных")
    ap.add_argument("--lang", nargs="+", default=["ru", "en"], choices=["ru", "en"])
    ap.add_argument("--out", default=os.path.join(HERE, "docs", "screens"))
    ap.add_argument("--only", default="", help="имена снимков через запятую")
    ap.add_argument("--version", default="", help="номер на снимках (по умолчанию — номер следующего коммита)")
    ap.add_argument("--harness", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.harness:
        return harness(a.harness)
    if not shutil.which("Xvfb"):
        raise SystemExit("Нужен Xvfb (пакет xvfb)")
    display = free_display()
    xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1920x1300x24", "-nolisten", "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1)
        only = {x.strip() for x in a.only.split(",") if x.strip()}
        sys.path.insert(0, os.path.join(HERE, "app"))
        import version
        ver = a.version or version.next_version()
        print(f"номер на снимках: {ver}", flush=True)
        bad = [lang for lang in a.lang if shoot(lang, os.path.join(a.out, lang), only, display, ver)]
    finally:
        xvfb.terminate()
        xvfb.wait(5)
    if bad:
        raise SystemExit(f"Не все снимки сняты: {', '.join(bad)}")


if __name__ == "__main__":
    main()
