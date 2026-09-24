#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Окно доски на Windows 10/11 — то же, что widget.py на Linux, но на pywebview (движок WebView2).

Страница та же (/widget?host=pywebview) и говорит с окном теми же сообщениями через
window.pywebview.api.post(…):
  geom-start:<move|n|s|e|w|ne|…> → geom:<dx>,<dy> → geom-end — перетащить или растянуть окно
      (у окна без рамки на Windows нет системного перетаскивания — сдвиг считает страница);
  lock:1 / lock:0 — замок: не двигать, не менять размер, держать под остальными окнами;
  settings / settings:<раздел> — окно настроек;  message:<id> — окно одного сообщения (/message?id=N);
  assistant — окно ассистента (/assistant);
  open:{"app","site"} — сайт открыть в браузере, приложение — по его AUMID (shell:AppsFolder).

Прозрачных окон WebView2 не умеет — подложка сплошная (класс pyw на странице). Место, размер
и замок хранятся в том же widget-state.json, что и на Linux (%APPDATA%\\\\messhub).
"""

import json
import os
import threading
import time
import webbrowser

import paths
import screen
import version
import wincatcher

MIN_W, MIN_H = 360, 160
DEF_W, DEF_H = 1000, 300
HWND_BOTTOM, SWP_KEEP = 1, 0x0001 | 0x0002 | 0x0010        # NOSIZE | NOMOVE | NOACTIVATE


def _load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_state(path, st):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(st, f)
    except OSError:
        pass


class Api:
    """Мост для страницы (window.pywebview.api). Поля с «_» pywebview наружу не отдаёт."""

    def __init__(self, base_url, state_path):
        self._base, self._state_path = base_url, state_path
        self._state = _load_state(state_path)
        self._win = self._settings = None
        self._pages = {}             # отдельные окна страниц: message, assistant
        self._share, self._share_thread = {"on": False}, None     # показ экрана → размыть доску
        self._g0 = None
        self._save_timer = None

    # ── страница → окно ──
    def post(self, msg):
        try:
            self._handle(str(msg))
        except Exception as e:  # noqa: BLE001 — ошибка одной команды не роняет окно
            print(f"окно: {msg!r}: {e!r}", flush=True)

    def _handle(self, msg):
        w = self._win
        if msg.startswith("geom-start:"):
            if not self._state.get("locked"):
                self._g0 = (msg.split(":", 1)[1], w.x, w.y, w.width, w.height)
        elif msg.startswith("geom:") and self._g0:
            dx, dy = (int(float(v)) for v in msg[5:].split(","))
            edge, x0, y0, w0, h0 = self._g0
            if edge == "move":
                w.move(x0 + dx, y0 + dy)
            else:
                from webview.window import FixPoint
                nw = max(MIN_W, w0 + (dx if "e" in edge else -dx if "w" in edge else 0))
                nh = max(MIN_H, h0 + (dy if "s" in edge else -dy if "n" in edge else 0))
                fix = (FixPoint.EAST if "w" in edge else FixPoint.WEST) | \
                      (FixPoint.SOUTH if "n" in edge else FixPoint.NORTH)
                w.resize(nw, nh, fix_point=fix)
        elif msg == "geom-end":
            self._g0 = None
            self._remember()
        elif msg in ("lock:1", "lock:0"):
            self._state["locked"] = msg == "lock:1"
            self._remember()
            self._keep_below()
        elif msg == "settings" or msg.startswith("settings:"):
            self._open_settings(msg.split(":", 1)[1] if ":" in msg else "")
        elif msg.startswith("share:"):
            cfg = json.loads(msg[6:])
            self._share = {"on": bool(cfg.get("on")), "patterns": [str(x) for x in cfg.get("patterns") or []]}
            if self._share["on"] and not self._share_thread:
                self._share_thread = threading.Thread(target=self._share_loop, name="share", daemon=True)
                self._share_thread.start()
        elif msg.startswith("message:") and msg[8:].isdigit():
            self._open_page("message", f"/message?id={int(msg[8:])}&host=pywebview", 900, 640)
        elif msg == "assistant":
            self._open_page("assistant", "/assistant?host=pywebview", 1120, 760)
        elif msg.startswith("open:"):
            self._open(json.loads(msg[5:]))

    # ── окно ──
    def _remember(self, *_):
        """Место и размер — через полсекунды после того, как окно перестали двигать."""
        if self._save_timer:
            self._save_timer.cancel()

        def save():
            w = self._win
            if w:
                self._state.update(x=w.x, y=w.y, w=w.width, h=w.height)
                _save_state(self._state_path, self._state)
        self._save_timer = threading.Timer(0.5, save)
        self._save_timer.daemon = True
        self._save_timer.start()

    def _hwnd(self):
        try:
            return self._win.native.Handle.ToInt32()
        except Exception:  # noqa: BLE001
            return None

    def _keep_below(self):
        if self._state.get("locked"):
            h = self._hwnd()
            if h:
                import ctypes
                ctypes.windll.user32.SetWindowPos(h, HWND_BOTTOM, 0, 0, 0, 0, SWP_KEEP)

    def _below_loop(self):
        while self._win:
            self._keep_below()
            time.sleep(1.0)

    def _toast(self, key, params=None):
        if self._win:
            self._win.evaluate_js(f"window.hostToast && hostToast({json.dumps(key)}, "
                                  f"{json.dumps(params or {}, ensure_ascii=False)}, true)")

    def _open(self, d):
        site, app = d.get("site") or "", d.get("app") or ""
        if site:
            webbrowser.open("https://" + site)
            return
        aumid = wincatcher.aumid_for(app)
        if aumid:
            try:
                os.startfile("shell:AppsFolder\\" + aumid)
                return
            except OSError as e:
                self._toast("Не удалось запустить: {e}", {"e": str(e)})
                return
        self._toast("Не нашёл окно «{app}» — приложение закрыто?", {"app": app})

    def _open_settings(self, section):
        import webview
        url = self._base + "/settings" + ("#" + section if section else "")
        if self._settings:
            try:
                self._settings.load_url(url)
                self._settings.restore()
                self._settings.show()
                return
            except Exception:  # noqa: BLE001 — окно уже закрыли
                self._settings = None
        self._settings = webview.create_window(f"{version.APP_NAME} — настройки", url, width=1100, height=760,
                                               background_color="#16181d", min_size=(760, 480))
        self._settings.events.closed += lambda: setattr(self, "_settings", None)

    def _open_page(self, kind, path, width, height):
        """Отдельное окно страницы (сообщение, ассистент), каждого вида одно: уже открыто — показать."""
        import webview
        url = self._base + path
        win = self._pages.get(kind)
        if win:
            try:
                if kind == "message":
                    win.load_url(url)
                win.restore()
                win.show()
                return
            except Exception:  # noqa: BLE001 — окно уже закрыли
                self._pages.pop(kind, None)
        bridge = PageApi(self)
        win = webview.create_window(version.APP_NAME, url, js_api=bridge, width=width, height=height,
                                    background_color="#171a21", min_size=(480, 320))
        bridge._win = win
        self._pages[kind] = win
        win.events.closed += lambda: self._pages.pop(kind, None)

    def _share_loop(self):
        """Раз в 3 с: окна-индикаторы показа экрана (заголовки через EnumWindows) → hostSetShare."""
        active = False
        while self._share.get("on"):
            hit = screen.title_match(_window_titles(), self._share.get("patterns") or [])
            if bool(hit) != active and self._win:
                active = bool(hit)
                self._win.evaluate_js(f"window.hostSetShare && hostSetShare({'true' if active else 'false'})")
            time.sleep(3)
        if active and self._win:
            self._win.evaluate_js("window.hostSetShare && hostSetShare(false)")
        self._share_thread = None

    def _on_loaded(self):
        locked = "true" if self._state.get("locked") else "false"
        self._win.evaluate_js(f"window.hostSetLocked && hostSetLocked({locked})")
        self._keep_below()


def _window_titles():
    """Заголовки видимых окон верхнего уровня (Windows)."""
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return []
    user32, out = ctypes.windll.user32, []
    proto = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _l):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                out.append(buf.value)
        return True
    user32.EnumWindows(proto(cb), 0)
    return out


class PageApi:
    """Мост отдельного окна (сообщение, ассистент): close — закрыть, open:{…} — перейти в приложение,
    message:<id> / assistant / settings — открыть другое окно (как с доски)."""

    def __init__(self, main):
        self._main, self._win = main, None

    def post(self, msg):
        try:
            msg = str(msg)
            if msg == "close" and self._win:
                self._win.destroy()
            elif msg.startswith("open:"):
                self._main._open(json.loads(msg[5:]))
            else:
                self._main._handle(msg)
        except Exception as e:  # noqa: BLE001 — ошибка одной команды не роняет окно
            print(f"окно страницы: {msg!r}: {e!r}", flush=True)


def _default_geometry():
    import webview
    try:
        s = webview.screens[0]
        return (max(0, (s.width - DEF_W) // 2), max(0, s.height - DEF_H - 60), DEF_W, DEF_H)
    except Exception:  # noqa: BLE001
        return (100, 100, DEF_W, DEF_H)


def _visible(x, y, w, h):
    """Центр окна — на каком-нибудь мониторе (монитор могли отключить)."""
    import webview
    cx, cy = x + w / 2, y + h / 2
    for s in webview.screens:
        sx, sy = getattr(s, "x", 0), getattr(s, "y", 0)
        if sx <= cx <= sx + s.width and sy <= cy <= sy + s.height:
            return True
    return False


def run(base_url, state_path=paths.WIDGET_STATE, only="", open_settings=False):
    """Открыть доску и крутить окна до закрытия (главный поток). → когда окно закрыли."""
    import webview
    api = Api(base_url, state_path)
    st = api._state
    geo = (st.get("x"), st.get("y"), st.get("w"), st.get("h"))
    if None in geo or not _visible(*geo):
        geo = _default_geometry()
    x, y, w, h = geo
    url = base_url + "/widget?host=pywebview" + ("&only=" + only if only else "")
    win = webview.create_window(version.version_line(), url, js_api=api, x=x, y=y, width=max(MIN_W, w),
                                height=max(MIN_H, h), frameless=True, easy_drag=False, resizable=True,
                                min_size=(MIN_W, MIN_H), background_color="#12151c", text_select=True)
    api._win = win
    win.events.loaded += api._on_loaded
    win.events.moved += api._remember
    win.events.resized += api._remember
    win.events.shown += lambda: threading.Thread(target=api._below_loop, daemon=True).start()

    def closed():
        api._remember()
        api._win = None
    win.events.closed += closed
    if open_settings:
        api._open_settings("")
    storage = os.path.join(paths.CACHE_DIR, "webview")         # localStorage страницы (фокус, размытие)
    os.makedirs(storage, exist_ok=True)
    webview.start(gui="edgechromium", private_mode=False, storage_path=storage,
                  icon=os.path.join(paths.HERE, "icons", "messhub.ico"))
