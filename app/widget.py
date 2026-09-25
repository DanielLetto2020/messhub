#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Виджет на рабочий стол: полупрозрачное окно с доской колонок по источникам.

Оборачивает веб-страницу /widget (её отдаёт serve.py / collect.py) в окно
GTK + WebKit2:
  - без рамки, полупрозрачное («стеклянная» подложка рисуется самой страницей);
  - ПЕРЕМЕЩАЕТСЯ мышкой за шапку (в т.ч. между мониторами) и МЕНЯЕТ РАЗМЕР за
    края/углы. Рамки у окна нет, поэтому это делает страница: при перетаскивании
    шапки/края она шлёт сюда "move" / "resize:<край>" через
    window.webkit.messageHandlers.widget, а окно отдаёт перетаскивание оконному
    менеджеру (begin_move_drag / begin_resize_drag);
  - ЗАПОМИНАЕТ положение и размер (widget-state.json рядом со скриптом) и при
    следующем запуске встаёт туда же. Первый запуск (или --reset) — по центру
    внизу монитора, где курсор;
  - кнопка-«замок» ЗАКРЕПЛЯЕТ окно: двигать/растягивать нельзя, и оно держится
    под всеми окнами. Состояние замка тоже в widget-state.json. Если окно сдвинули
    в обход страницы (Alt+перетаскивание в mutter) — оно возвращается на место;
  - колонки делят ширину окна поровну сами (flex: 1 на странице);
  - видно на всех рабочих столах, не мозолит в панели задач;
  - ⤢ на плашке (или «Показать целиком») — отдельное окно СООБЩЕНИЯ (/message?id=N): текст и лог целиком;
  - ✨ в шапке — окно АССИСТЕНТА (/assistant): чат с локальной моделью (Ollama / LM Studio) по базе;
  - кнопка-«шестерёнка» открывает отдельное окно НАСТРОЕК (/settings): источники и
    правила, что показывать в виджете (см. rules.py);
  - кнопка-«глаз» на странице размывает все сообщения (для показа экрана);
  - ссылки из сообщений открываются в браузере по умолчанию (decide-policy);
  - клик по имени на плашке переключает на окно приложения-источника (libwnck:
    окно ищется по классу WM_CLASS), нет окна — запускает приложение по .desktop;
    у веб-уведомлений (MAX и т.п.) открывает сайт в браузере;
  - кнопка-«галочка» на сообщении отмечает его прочитанным в БД и скрывает.

Требует запущенный сбор+сервер (сервис messhub или `python3 collect.py`).
Полностью работает на X11. На Wayland — упрощённый режим: окно двигается и
растягивается мышкой (это делает композитор), но приложение не может само
поставить окно на место, держать его под окнами и переключать на чужие окна —
поэтому место не восстанавливается, замок только фиксирует размер, а «перейти в
приложение» запускает его по ярлыку (обычно это поднимает уже открытое окно).

Второй виджет с отбором колонок: --only express,telegram --state ~/.config/…/work.json

    python3 widget.py
    python3 widget.py --reset                   # забыть сохранённое место и размер
    python3 widget.py --width 1200 --height 400 # размер для первого запуска / --reset
    python3 widget.py --below
    python3 widget.py --only express --state ~/.config/messhub/widget-work.json
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
from urllib.parse import urlsplit
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gtk, Gdk, GdkX11, Gio, WebKit2, GLib  # noqa: E402
try:
    gi.require_version("Wnck", "3.0")
    from gi.repository import Wnck  # noqa: E402  — окна других приложений (X11)
except (ValueError, ImportError):
    Wnck = None

import applog  # noqa: E402
import paths  # noqa: E402
import screen  # noqa: E402
import version  # noqa: E402

# для тестов: не переключать окна и не запускать приложения, только писать в лог
DRY_OPEN = bool(os.environ.get(f"{paths.ENV_PREFIX}_DRY_OPEN"))
# для тестов: вести себя как на Wayland, даже если под нами X11
FORCE_NOX11 = bool(os.environ.get(f"{paths.ENV_PREFIX}_FORCE_NOX11"))


def is_x11():
    return not FORCE_NOX11 and isinstance(Gdk.Display.get_default(), GdkX11.X11Display)
_RE_SITE = re.compile(r"^(?:[a-z0-9-]+\.)+[a-z]{2,}$")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STATE = paths.WIDGET_STATE       # ~/.config/<APP_ID>/widget-state.json

MIN_W, MIN_H = 260, 140      # меньше мышкой не сжать
SETTINGS_W, SETTINGS_H = 1000, 680   # окно настроек по умолчанию
MESSAGE_W, MESSAGE_H = 900, 640      # окно одного сообщения (/message?id=N)
ASSIST_W, ASSIST_H = 1120, 760       # окно ассистента (/assistant)
GEOM_KEYS = ("x", "y", "w", "h")

# край/угол, за который тянут на странице → край окна для оконного менеджера
EDGES = {
    "n": Gdk.WindowEdge.NORTH, "s": Gdk.WindowEdge.SOUTH,
    "e": Gdk.WindowEdge.EAST, "w": Gdk.WindowEdge.WEST,
    "ne": Gdk.WindowEdge.NORTH_EAST, "nw": Gdk.WindowEdge.NORTH_WEST,
    "se": Gdk.WindowEdge.SOUTH_EAST, "sw": Gdk.WindowEdge.SOUTH_WEST,
}


def log(*a):
    print("[widget]", *a, file=sys.stderr, flush=True)


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def app_keys(app):
    """Имена, по которым ищем окно приложения: само app, части snap-имени
    ("telegram-desktop_telegram-desktop") и StartupWMClass из .desktop, если он есть."""
    keys = {_norm(app)} | {_norm(p) for p in re.split(r"[_]", app or "")}
    info = desktop_info(app)
    if info is not None and info.get_startup_wm_class():
        keys.add(_norm(info.get_startup_wm_class()))
    return {k for k in keys if len(k) >= 3}


def desktop_info(app):
    """.desktop приложения: сначала <app>.desktop, потом поиск по имени — но только если
    найденный ярлык действительно про это приложение (имя совпадает с id или названием).
    Иначе поиск по «CI» или «Сборки» запустил бы что-нибудь постороннее."""
    try:
        return Gio.DesktopAppInfo.new(f"{app}.desktop")
    except TypeError:          # такого файла нет — конструктор вернул NULL
        pass
    key = _norm(app)
    if len(key) < 3:
        return None
    for group in Gio.DesktopAppInfo.search(app or ""):
        for desktop_id in group:
            try:
                info = Gio.DesktopAppInfo.new(desktop_id)
            except TypeError:
                continue
            if key in _norm(desktop_id) or key == _norm(info.get_name()):
                return info
    return None


def find_window(app):
    """Обычное окно приложения, чей класс совпадает с одним из имён app_keys."""
    if Wnck is None:
        return None
    scr = Wnck.Screen.get_default()
    scr.force_update()
    keys, me = app_keys(app), os.getpid()
    wins = [w for w in scr.get_windows()
            if w.get_window_type() == Wnck.WindowType.NORMAL and w.get_pid() != me]
    for w in wins:
        if {_norm(w.get_class_group_name()), _norm(w.get_class_instance_name())} & keys:
            return w
    return None


def window_titles():
    """Заголовки чужих окон (X11, libwnck) — для «идёт ли показ экрана»."""
    if Wnck is None:
        return []
    scr = Wnck.Screen.get_default()
    scr.force_update()
    me = os.getpid()
    return [w.get_name() or "" for w in scr.get_windows() if w.get_pid() != me] + \
        [w.get_class_instance_name() or "" for w in scr.get_windows() if w.get_pid() != me]


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            s = json.load(f)
        st = {k: int(s[k]) for k in GEOM_KEYS}
        st["locked"] = bool(s.get("locked", False))
        return st
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_state(path, geom):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(geom, f)
    os.replace(tmp, path)


class Widget(Gtk.Window):
    def __init__(self, url, state_path, reset, width, height, bottom_margin, below):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.state_path = state_path
        self.x11 = is_x11()
        if not self.x11:
            log("не X11 (Wayland?): место окна не восстанавливается, под окна не уходит")
        u = urlsplit(url)
        self.base_url = f"{u.scheme}://{u.netloc}"   # тот же сервер отдаёт и /settings
        self.settings_win = None
        self.page_wins = {}          # отдельные окна страниц: message, assistant (по одному каждого)
        self.find_win = None         # окно результатов поиска из шапки (над панелью)
        self.share = {"on": False, "patterns": [], "active": False, "tick": 0, "id": 0}
        self.saved = None if reset else load_state(state_path)   # что сейчас в файле
        self.locked = bool(self.saved and self.saved["locked"])  # --reset снимает и замок
        self.below = below
        saved_geom = {k: self.saved[k] for k in GEOM_KEYS} if self.saved else None
        self.geom = self._fit_saved(saved_geom) \
            or self._default_geom(width, height, bottom_margin)
        self.placed = False       # до своей расстановки configure-события не запоминаем
        self._save_id = 0
        self._snap_id = 0
        self._snapping = False

        self.set_title(version.version_line())
        self.set_decorated(False)
        self.set_resizable(True)
        self.set_size_request(MIN_W, MIN_H)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_position(Gtk.WindowPosition.NONE)
        if self.x11:
            self.stick()
            self.set_keep_below(below or self.locked)
        # стартовый размер — ДО показа, иначе GTK даёт 200x200
        self.set_default_size(self.geom["w"], self.geom["h"])

        vis = self.get_screen().get_rgba_visual()
        if vis is not None:
            self.set_visual(vis)
        self.set_app_paintable(True)

        # канал страница → окно: window.webkit.messageHandlers.widget.postMessage(...)
        ucm = WebKit2.UserContentManager()
        ucm.connect("script-message-received::widget", self._on_page_msg)
        ucm.register_script_message_handler("widget")
        self.web = WebKit2.WebView.new_with_user_content_manager(ucm)
        self.web.set_background_color(Gdk.RGBA(0, 0, 0, 0))
        self.web.connect("load-changed", self._on_load)
        self.web.connect("decide-policy", self._on_policy)
        self.web.load_uri(url)
        self.add(self.web)

        self.connect("destroy", lambda *_: self._quit())
        self.connect("configure-event", self._on_configure)
        self.connect("map-event", lambda *_: self._schedule_place())

    # ── геометрия по умолчанию / сохранённая ──
    def _default_geom(self, width, height, bottom_margin):
        geo = self._pointer_monitor().get_geometry()
        w = max(MIN_W, min(width, geo.width - 40))
        h = max(MIN_H, min(height, geo.height - 40))
        return {"x": geo.x + (geo.width - w) // 2,
                "y": geo.y + geo.height - h - bottom_margin, "w": w, "h": h}

    def _pointer_monitor(self):
        disp = Gdk.Display.get_default()
        try:
            _scr, x, y = disp.get_default_seat().get_pointer().get_position()
            mon = disp.get_monitor_at_point(x, y)
            if mon is not None:
                return mon
        except Exception:
            pass
        return disp.get_primary_monitor() or disp.get_monitor(0)

    def _fit_saved(self, g):
        """Сохранённое место годится, если центр окна на одном из текущих мониторов
        (монитор могли отключить — тогда встаём по умолчанию)."""
        if not g:
            return None
        disp = Gdk.Display.get_default()
        cx, cy = g["x"] + g["w"] // 2, g["y"] + g["h"] // 2
        for i in range(disp.get_n_monitors()):
            geo = disp.get_monitor(i).get_geometry()
            if geo.x <= cx < geo.x + geo.width and geo.y <= cy < geo.y + geo.height:
                g["w"] = max(MIN_W, min(g["w"], geo.width))
                g["h"] = max(MIN_H, min(g["h"], geo.height))
                return g
        log("сохранённое место вне мониторов — ставлю по умолчанию")
        return None

    # ── события ──
    def _on_policy(self, _web, decision, dtype):
        """Ссылки из сообщений — в браузер по умолчанию; сам виджет со своей страницы
        никуда не уходит."""
        if dtype not in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                         WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            return False
        uri = decision.get_navigation_action().get_request().get_uri() or ""
        if uri.startswith(self.base_url + "/") or uri == self.base_url:
            return False
        if uri.startswith(("http://", "https://", "mailto:")):
            try:
                Gio.AppInfo.launch_default_for_uri(uri, None)
                log("открыл ссылку в браузере")
            except GLib.Error as e:
                log("не смог открыть ссылку:", e.message)
        decision.ignore()
        return True

    def _on_load(self, web, event):
        # сказать странице, закреплено ли окно (замок в шапке)
        if event == WebKit2.LoadEvent.FINISHED:
            js = f"window.hostSetLocked && hostSetLocked({'true' if self.locked else 'false'})"
            web.evaluate_javascript(js, -1, None, None, None, None)

    def _on_page_msg(self, _ucm, res):
        try:
            cmd = res.get_js_value().to_string()
        except Exception:
            return
        if cmd in ("lock:1", "lock:0"):
            self._set_locked(cmd == "lock:1")
            return
        if cmd == "settings" or cmd.startswith("settings:"):
            self._open_settings(cmd.partition(":")[2])
            return
        if cmd.startswith("share:"):         # страница: следить ли за показом экрана и по каким признакам
            try:
                cfg = json.loads(cmd[6:])
            except ValueError:
                return
            self.share.update(on=bool(cfg.get("on")), patterns=[str(x) for x in cfg.get("patterns") or []])
            if self.share["on"] and not self.share["id"]:
                self.share["id"] = GLib.timeout_add_seconds(3, self._check_share)
            return
        if cmd.startswith("search:"):
            try:
                self._search(json.loads(cmd[7:]))
            except ValueError:
                pass
            return
        if cmd.startswith("search-nav:") and self.find_win is not None:
            self.find_win.get_child().evaluate_javascript(
                f"window.hostNav && hostNav({json.dumps(cmd[11:])})", -1, None, None, None, None)
            return
        if cmd == "search-close":
            self._search_close()
            return
        if self._page_cmd(cmd):
            return
        if cmd.startswith("open:"):
            try:
                req = json.loads(cmd[5:])
                self._open_source(str(req.get("app") or ""), str(req.get("site") or ""))
            except ValueError:
                pass
            return
        if self.locked:
            return        # закреплено — ни двигать, ни тянуть
        # кнопка ещё зажата — отдаём перетаскивание оконному менеджеру с места курсора
        _scr, x, y = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()
        if cmd == "move":
            self.begin_move_drag(1, x, y, Gdk.CURRENT_TIME)
        elif cmd.startswith("resize:") and cmd[7:] in EDGES:
            self.begin_resize_drag(EDGES[cmd[7:]], 1, x, y, Gdk.CURRENT_TIME)

    def _on_configure(self, *_):
        if not self.placed:
            return False
        self._search_close()                  # окно двигают или тянут — результаты поиска не висят в стороне
        if self.locked:
            # закреплено, но окно сдвинули в обход страницы — вернуть, когда утихнет
            if self._snap_id:
                GLib.source_remove(self._snap_id)
            self._snap_id = GLib.timeout_add(400, self._snap_back)
            return False
        # окно передвинули/растянули — запомнить, когда движение утихнет
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(500, self._save)
        return False

    def _set_locked(self, locked):
        self.locked = locked
        if self.x11:
            self.set_keep_below(locked or self.below)
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save()      # зафиксировать текущее место/размер вместе с замком
        log(("закреплено: не двигается, под всеми окнами" if self.x11 else
             "закреплено: мышкой не двигается и не тянется") if locked else "откреплено")

    def _snap_back(self):
        self._snap_id = 0
        if not self.x11:             # на Wayland своё положение не узнать и не задать
            return False
        x, y = self.get_position()
        w, h = self.get_size()
        cur = {"x": x, "y": y, "w": w, "h": h}
        if cur == self.geom:
            self._snapping = False
        elif self._snapping:
            # уже возвращали, а WM всё равно держит иначе (упёрлось в край экрана
            # и т.п.) — не воюем с ним бесконечно, принимаем как есть
            self._snapping = False
            self._save()
        else:
            self._snapping = True
            g = self.geom
            self.resize(g["w"], g["h"])
            self.move(g["x"], g["y"])
            log(f"закреплено — вернул на место {g['w']}x{g['h']} @ {g['x']},{g['y']}")
        return False

    def _save(self):
        self._save_id = 0
        x, y = self.get_position()
        w, h = self.get_size()
        self.geom = {"x": x, "y": y, "w": w, "h": h}
        state = dict(self.geom, locked=self.locked)
        if state != self.saved:
            try:
                save_state(self.state_path, state)
                self.saved = state
                log(f"запомнил {w}x{h} @ {x},{y}" + (" [закреплено]" if self.locked else ""))
            except OSError as e:
                log("не смог сохранить положение:", e)
        return False

    def _quit(self):
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._save()
        Gtk.main_quit()

    # ── перейти в приложение-источник ──
    def _page_toast(self, key, params=None, err=True, web=None):
        """Подсказка на странице (доски или окна сообщения): key — русская фраза-ключ перевода (i18n.js)."""
        js = (f"window.hostToast && hostToast({json.dumps(key)}, {json.dumps(params or {})}, "
              f"{'true' if err else 'false'})")
        (web or self.web).evaluate_javascript(js, -1, None, None, None, None)

    def _open_source(self, app, site, web=None):
        toast = lambda key, params=None: self._page_toast(key, params, web=web)  # noqa: E731
        if site:
            if not _RE_SITE.match(site):
                return
            uri = f"https://{site}"
            log(("открыл бы " if DRY_OPEN else "открываю ") + uri)
            if not DRY_OPEN:
                try:
                    Gio.AppInfo.launch_default_for_uri(uri, None)
                except GLib.Error as e:
                    toast("Не удалось открыть {site}: {e}", {"site": site, "e": e.message})
            return
        win = find_window(app) if self.x11 else None
        if win is not None:
            log(f"{'переключил бы' if DRY_OPEN else 'переключаю'} на окно «{win.get_class_group_name()}»")
            if not DRY_OPEN:
                # настоящая метка времени X-сервера: с нулём mutter не отдаст фокус,
                # а только подсветит окно как «требует внимания»
                ts = GdkX11.x11_get_server_time(self.get_window())
                ws = win.get_workspace()
                if ws is not None and ws != Wnck.Screen.get_default().get_active_workspace():
                    ws.activate(ts)
                win.activate(ts)
            return
        info = desktop_info(app)
        if info is not None:
            log(f"{'запустил бы' if DRY_OPEN else 'запускаю'} {info.get_id()}")
            if not DRY_OPEN:
                try:
                    info.launch([], self.get_display().get_app_launch_context())
                except GLib.Error as e:
                    toast("Не удалось запустить: {e}", {"e": e.message})
            return
        log(f"не нашёл ни окна, ни ярлыка для «{app}»")
        toast("Не нашёл окно «{app}» — приложение закрыто?", {"app": app})

    # ── окно настроек ──
    def _open_settings(self, section=""):
        """Обычное окно с рамкой (двигать/закрывать — средствами WM). Одно на всех:
        если уже открыто — просто поднять (и перейти в раздел, если он указан)."""
        hash_ = ("#" + section) if re.match(r"^[a-z-]{1,20}$", section or "") else ""
        if self.settings_win is not None:
            if hash_:                          # тот же раздел — перерисовать (например, новый запрос поиска)
                h = json.dumps(hash_)
                self.settings_win.get_child().evaluate_javascript(
                    f"location.hash==={h}?route():location.hash={h}", -1, None, None, None, None)
            self.settings_win.present()
            return
        win = Gtk.Window(title=f"{version.version_line()} — настройки")
        geo = self.get_display().get_monitor_at_window(self.get_window()).get_geometry()
        win.set_default_size(min(SETTINGS_W, geo.width - 80), min(SETTINGS_H, geo.height - 80))
        win.set_position(Gtk.WindowPosition.CENTER)   # на мониторе под курсором = у виджета
        web = WebKit2.WebView()
        web.set_background_color(Gdk.RGBA(0.09, 0.10, 0.13, 1))   # как фон страницы
        web.connect("decide-policy", self._on_policy)
        web.connect("notify::title", lambda w, _p: w.get_title() and win.set_title(w.get_title()))
        web.load_uri(self.base_url + "/settings" + hash_)
        win.add(web)
        win.connect("destroy", lambda *_: setattr(self, "settings_win", None))
        win.connect("key-press-event",
                    lambda w, ev: ev.keyval == Gdk.KEY_Escape and w.destroy())
        win.show_all()
        self.settings_win = win
        log("открыл настройки")

    # ── поиск из шапки: окно результатов над панелью ──
    def _search(self, cfg):
        """Окно без рамки прямо над полем поиска (не хватает места сверху — под панелью). Фокус не забирает:
        ввод остаётся в шапке, стрелки и Enter приходят сюда командами search-nav."""
        q = str(cfg.get("q") or "").strip()[:200]
        if not q:
            self._search_close()
            return
        if not self.x11:                       # Wayland: окно не поставить у панели — обычное окно
            self._open_page("find", "/find?q=" + urllib.parse.quote(q), 640, 480)
            return
        wx, wy = self.get_position()
        _ww, wh = self.get_size()
        geo = self.get_display().get_monitor_at_window(self.get_window()).get_geometry()
        width = max(460, min(640, geo.width - 40))
        x = min(max(wx + int(cfg.get("x") or 0) - 10, geo.x + 8), geo.x + geo.width - width - 8)
        above, below = wy - geo.y - 12, geo.y + geo.height - (wy + wh) - 12
        if above >= 220:
            height = min(440, above)
            y = wy - height - 6
        elif below >= 220:
            height = min(440, below)
            y = wy + wh + 6
        else:
            height = min(440, geo.height - 40)
            y = geo.y + 20
        win = self.find_win
        if win is None:
            win = Gtk.Window(type=Gtk.WindowType.POPUP)       # мимо оконного менеджера: без рамки, поверх, без фокуса
            win.set_app_paintable(True)
            vis = win.get_screen().get_rgba_visual()
            if vis is not None:
                win.set_visual(vis)
            ucm = WebKit2.UserContentManager()
            web = WebKit2.WebView.new_with_user_content_manager(ucm)
            web.set_background_color(Gdk.RGBA(0, 0, 0, 0))

            def on_msg(_ucm, res):
                try:
                    c = res.get_js_value().to_string()
                except Exception:
                    return
                self._page_cmd(c, web=web, win=win)
            ucm.connect("script-message-received::widget", on_msg)
            ucm.register_script_message_handler("widget")
            web.connect("decide-policy", self._on_policy)
            web.load_uri(f"{self.base_url}/find?q={urllib.parse.quote(q)}")
            win.add(web)
            win.connect("destroy", lambda *_: setattr(self, "find_win", None))
            self.find_win = win
        else:
            win.get_child().evaluate_javascript(f"window.hostSearch && hostSearch({json.dumps(q)})",
                                                -1, None, None, None, None)
        win.resize(width, height)
        win.move(x, y)
        win.show_all()

    def _search_close(self):
        if self.find_win is not None:
            self.find_win.destroy()
            self.find_win = None

    # ── показ экрана на созвоне → доска размывается сама ──
    def _check_share(self):
        sh = self.share
        if not sh["on"]:
            sh["id"] = 0
            if sh["active"]:
                sh["active"] = False
                self.web.evaluate_javascript("window.hostSetShare && hostSetShare(false)", -1, None, None, None, None)
            return False
        sh["tick"] += 1
        hit = screen.title_match(window_titles(), sh["patterns"]) if self.x11 else ""
        if not hit and sh["tick"] % 2 == 0:          # PipeWire (Wayland, портал) — через раз: pw-dump тяжелее
            hit = "pipewire" if screen.pipewire_sharing() else ""
        active = bool(hit) or (sh["active"] and sh["tick"] % 2 == 1)   # не мигать между проверками PipeWire
        if active != sh["active"]:
            sh["active"] = active
            log(f"показ экрана: {'начался' if active else 'кончился'}")
            self.web.evaluate_javascript(f"window.hostSetShare && hostSetShare({'true' if active else 'false'})",
                                         -1, None, None, None, None)
        return True

    # ── отдельные окна страниц: сообщение целиком, ассистент ──
    def _page_cmd(self, cmd, web=None, win=None):
        """Команды, общие для доски и отдельных окон. → обработана ли."""
        if cmd.startswith("message:") and cmd[8:].isdigit():
            self._open_page("message", f"/message?id={int(cmd[8:])}", MESSAGE_W, MESSAGE_H)
        elif cmd == "assistant":
            self._open_page("assistant", "/assistant", ASSIST_W, ASSIST_H)
        elif cmd == "close" and win is not None:
            win.destroy()
        elif cmd == "search-close":
            self._search_close()
        elif cmd.startswith("settings") and win is not None:
            self._open_settings(cmd.partition(":")[2])
        elif cmd.startswith("open:") and win is not None:
            try:
                req = json.loads(cmd[5:])
                self._open_source(str(req.get("app") or ""), str(req.get("site") or ""), web=web)
            except ValueError:
                pass
        else:
            return False
        return True

    def _open_page(self, kind, path, width, height):
        """Обычное окно с рамкой, как настройки; каждого вида — одно (уже открыто — показать в нём
        новый адрес и поднять). Страница шлёт close, open:{…}, message:<id>, settings, assistant."""
        url = self.base_url + path
        win = self.page_wins.get(kind)
        if win is not None:
            if kind == "message":
                win.get_child().load_uri(url)
            win.present()
            return
        win = Gtk.Window(title=version.APP_NAME)
        geo = self.get_display().get_monitor_at_window(self.get_window()).get_geometry()
        win.set_default_size(min(width, geo.width - 80), min(height, geo.height - 80))
        win.set_position(Gtk.WindowPosition.CENTER)
        ucm = WebKit2.UserContentManager()
        web = WebKit2.WebView.new_with_user_content_manager(ucm)

        def on_msg(_ucm, res):
            try:
                cmd = res.get_js_value().to_string()
            except Exception:
                return
            self._page_cmd(cmd, web=web, win=win)
        ucm.connect("script-message-received::widget", on_msg)
        ucm.register_script_message_handler("widget")
        web.set_background_color(Gdk.RGBA(0.09, 0.10, 0.13, 1))
        web.connect("decide-policy", self._on_policy)        # ссылки — в браузер
        web.connect("notify::title", lambda w, _p: w.get_title() and win.set_title(w.get_title()))
        web.load_uri(url)
        win.add(web)
        win.connect("destroy", lambda *_: self.page_wins.pop(kind, None))
        if kind == "message":                                  # у ассистента Esc — для поля ввода
            win.connect("key-press-event", lambda w, ev: ev.keyval == Gdk.KEY_Escape and w.destroy())
        win.show_all()
        self.page_wins[kind] = win
        log(f"открыл окно {path}")

    # ── расстановка ──
    def _schedule_place(self):
        # ставим после маппинга: mutter иначе ставит окно по-своему
        self.placed = False
        GLib.timeout_add(40, self._place_once, False)
        GLib.timeout_add(250, self._place_once, True)

    def _place_once(self, last):
        g = self.geom
        self.resize(g["w"], g["h"])
        if self.x11:
            self.move(g["x"], g["y"])
        if last:
            self.placed = True
            log(f"позиция {g['w']}x{g['h']} @ {g['x']},{g['y']}")
            self._on_configure()      # записать, куда встали на самом деле
        return False   # одноразово


def main():
    ap = argparse.ArgumentParser(description="Десктоп-виджет ленты сообщений")
    ap.add_argument("--url", default="http://127.0.0.1:8765/widget")
    ap.add_argument("--state", default=DEFAULT_STATE,
                    help="файл с запомненным положением и размером")
    ap.add_argument("--reset", action="store_true",
                    help="не брать сохранённое место — встать по центру внизу (и снять замок)")
    ap.add_argument("--width", type=int, default=812,
                    help="ширина при первом запуске / --reset, px")
    ap.add_argument("--height", type=int, default=300,
                    help="высота при первом запуске / --reset, px")
    ap.add_argument("--bottom-margin", type=int, default=64,
                    help="отступ снизу при первом запуске / --reset, px")
    ap.add_argument("--below", action="store_true", help="держать под другими окнами")
    ap.add_argument("--only", default="",
                    help="показывать только эти колонки (ключи источников через запятую: express,telegram)")
    ap.add_argument("--version", action="version", version=version.version_line())
    args = ap.parse_args()
    applog.setup("widget", stderr_is_info=True)       # настройки → «Логи»
    log(version.version_line())
    # в первых сборках место виджета лежало рядом с кодом; базу переносит сбор, а свой файл — сам виджет
    if args.state == DEFAULT_STATE and paths.move_legacy_file("widget-state.json", DEFAULT_STATE):
        log(f"перенёс widget-state.json → {DEFAULT_STATE}")

    # имя и значок приложения: окна группируются с ярлыком messhub.desktop в панели задач
    GLib.set_prgname(version.APP_ID)
    GLib.set_application_name(version.APP_NAME)
    icon = os.path.join(paths.HERE, "icons", "messhub-128.png")
    if os.path.exists(icon):
        Gtk.Window.set_default_icon_from_file(icon)
    else:
        Gtk.Window.set_default_icon_name(version.APP_ID)          # из темы значков (пакет .deb/.rpm)
    # тёмная рамка у окна настроек — под тёмные страницы
    Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme", True)
    url = args.url
    if args.only:
        only = ",".join(k.strip() for k in args.only.split(",") if k.strip())
        url += ("&" if "?" in url else "?") + "only=" + urllib.parse.quote(only, safe=",:")
    win = Widget(url, args.state, args.reset, args.width, args.height,
                 args.bottom_margin, args.below)
    win.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
