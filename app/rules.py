#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Источники, правила, профили и настройки виджета («фильтры как в почте»).

ИСТОЧНИК — нормализованное приложение: разные написания одного приложения
(snap-Telegram, telegram-desktop, …) сводятся к одному ключу (express, telegram, …).
У браузерных уведомлений источник — САЙТ (web.max.ru → MAX), а не сам браузер.
Название и значок любого источника можно переопределить в настройках
(prefs.source_names) — так своим notify-send -a "Сборки" можно дать понятную колонку.

ПРАВИЛО (таблица rules): условие + действие (+ профиль).
  Условие: источник src ('*' = любой), чат chat, отправитель sender, текст text
  (подстрока без учёта регистра или регулярное выражение). Пустое поле = «любой».
  Действия:
    show / hide  — видно ли в виджете. Если совпало несколько, главнее самое узкое:
                   текст > отправитель > чат > весь источник, и конкретный источник
                   главнее «всех источников»; при равенстве побеждает «показывать».
    highlight    — подсветить цветом (param), решает самое узкое правило;
    read         — сразу отметить прочитанным (при записи);
    pin          — закрепить (при записи; главнее read);
    sound        — проиграть звук (при записи);
    forward      — переслать в Telegram (при записи, см. actions.py).
  Правило без chat/sender/text в конкретном источнике = режим всего источника
  («скрывать всё, кроме разрешённого»).

ПРОФИЛЬ («Работа», «Дом», «Созвон»…) — набор правил: правило с profile = '' действует
всегда, с id профиля — только когда этот профиль активен. Активный профиль выбирают
вручную или «авто» — по расписанию профилей (дни недели + время, МСК).

Правила влияют на виджет и на действия при записи; сами сообщения сохраняются
всегда (их видно в «Поиске»). Удалил правило — скрытое снова видно.
"""

import hashlib
import json
import re
from datetime import datetime

import catcher
import version
from i18n import L, lang

SOURCES = (
    # (подстрока в app, ключ, название (рус, англ), иконка, порядок колонок) — порядок проверки важен
    # тематические колонки (events.py, настройки → «Тематические колонки») — первыми, их app уникальны
    ("messhub-containers", "containers", ("Контейнеры", "Containers"), "🐳", 7),
    ("messhub-services", "services", ("Службы", "Services"), "⚙️", 7),
    ("messhub-commands", "commands", ("Команды", "Commands"), "⌨️", 7),
    ("express", "express", ("eXpress", "eXpress"), "💬", 0),
    ("telegram", "telegram", ("Telegram", "Telegram"), "✈️", 1),
    ("max", "max", ("MAX", "MAX"), "🅼", 2),
    ("alarm-notify", "calendar", ("Календарь", "Calendar"), "📅", 3),   # evolution-alarm-notify — до evolution
    ("org.gnome.calendar", "calendar", ("Календарь", "Calendar"), "📅", 3),
    ("mail-imap", "mail", ("Почта", "Mail"), "✉️", 3),        # письма из ящиков (mail.py)
    ("thunderbird", "mail", ("Почта", "Mail"), "✉️", 3),
    ("geary", "mail", ("Почта", "Mail"), "✉️", 3),
    ("evolution", "mail", ("Почта", "Mail"), "✉️", 3),
    ("outlook", "mail", ("Почта", "Mail"), "✉️", 3),          # Windows: Outlook и «Почта»
    ("yandex", "yandex", ("Яндекс", "Yandex"), "🌐", 6),
    ("chrome", "chrome", ("Chrome", "Chrome"), "🌐", 6),
    ("chromium", "chrome", ("Chrome", "Chrome"), "🌐", 6),
    ("firefox", "firefox", ("Firefox", "Firefox"), "🦊", 6),
    ("slack", "slack", ("Slack", "Slack"), "💼", 4),
    ("discord", "discord", ("Discord", "Discord"), "🎮", 4),
)

SITES = (
    # (домен или его хвост, ключ, название (рус, англ), иконка, порядок) — веб-уведомления браузера
    ("max.ru", "max", ("MAX", "MAX"), "🅼", 2),
    ("web.telegram.org", "telegram", ("Telegram", "Telegram"), "✈️", 1),
    ("whatsapp.com", "whatsapp", ("WhatsApp", "WhatsApp"), "🟢", 2),
    ("vk.com", "vk", ("ВКонтакте", "VK"), "🔵", 2),
    ("vk.ru", "vk", ("ВКонтакте", "VK"), "🔵", 2),
    ("mail.google.com", "mail", ("Почта", "Mail"), "✉️", 3),
    ("mail.yandex.ru", "mail", ("Почта", "Mail"), "✉️", 3),
    ("mail.ru", "mail", ("Почта", "Mail"), "✉️", 3),
    ("calendar.google.com", "calendar", ("Календарь", "Calendar"), "📅", 3),
    ("calendar.yandex.ru", "calendar", ("Календарь", "Calendar"), "📅", 3),
    ("slack.com", "slack", ("Slack", "Slack"), "💼", 4),
    ("discord.com", "discord", ("Discord", "Discord"), "🎮", 4),
    ("teams.microsoft.com", "teams", ("Teams", "Teams"), "🟣", 4),
)

VIS_ACTIONS = ("show", "hide")
INSERT_ACTIONS = ("read", "pin", "sound", "forward")      # выполняются при записи
ACTIONS = VIS_ACTIONS + ("highlight",) + INSERT_ACTIONS
TEXT_MODES = ("contains", "regex")
HIGHLIGHT_COLORS = ("red", "orange", "yellow", "green", "blue", "purple")

PREF_DEFAULTS = {
    "language": "auto",       # auto | ru | en — язык страниц и сообщений сервера
    "opacity": 0.72,          # непрозрачность подложки виджета
    "font_size": 13,          # px
    "compact": False,         # плотнее плашки
    "theme": "dark",          # dark | light
    "group_by_chat": True,    # сворачивать сообщения одного чата в одну плашку
    "avatars": True,          # показывать картинки отправителей из уведомлений
    "col_order": [],          # порядок колонок (ключи источников); остальные — по умолчанию
    "hidden_cols": [],        # скрытые насовсем колонки (ключи источников)
    "closed_cols": [],        # закрытые до нового сообщения (снова открывает apply_on_insert)
    "mail_channel": "notify", # почта: notify — уведомления почтовых программ, imap — ящики (mail.py)
    "mentions": [],           # моё имя/ник/ключевые слова — подсветка «упоминаний»
    "source_names": {},       # {ключ источника: {"name": …, "ico": …}}
    "profiles": [],           # [{"id", "name", "schedule": [{"days": [0..6], "from": "09:00", "to": "18:00"}]}]
    "profile": "",            # активный: "" — без профиля, "auto" — по расписанию, иначе id
    "retention_days": 0,      # хранить N дней (0 — всё); закреплённые не удаляются
    "backup": {"enabled": True, "keep": 7},                   # ежедневные копии базы
    "report": {"enabled": False, "weekday": 0, "time": "09:00"},  # недельный отчёт в Telegram
    "rag": {"enabled": False, "model": "bge-m3", "chat_model": ""},  # умный поиск (rag.py)
    "ingest_bind": "",        # приём событий из сети: "0.0.0.0:8766"; "" — только локально
    "update_check": True,     # раз в 12 ч узнавать у GitHub номер последнего выпуска (updates.py)
    # тематические колонки для ИТ (events.py): каждая включается отдельно, по умолчанию выключены
    "themed": {
        "containers": {"enabled": False, "startstop": False, "log_lines": 20, "ignore": []},
        "services": {"enabled": False, "system": True, "user": True, "log_lines": 20},
        "commands": {"enabled": False, "log_lines": 20},
    },
    # служебное — не настройки, в выгрузку и в версию настроек не входит:
    "backup_last": "", "report_last": "", "services_win_last": "",
}
STATE_PREFS = ("backup_last", "report_last", "services_win_last")
# от этих настроек зависит вид доски — по их хэшу (X-Prefs-Ver) виджет перечитывает её
DISPLAY_PREFS = ("language", "opacity", "font_size", "compact", "theme", "group_by_chat",
                 "avatars", "col_order", "hidden_cols", "closed_cols", "mail_channel", "mentions",
                 "source_names", "profiles", "profile")


# ── источники ───────────────────────────────────────────────────────────────

def source_of(app, site="", names=None):
    """app (+ сайт для браузерных уведомлений) → {key, name, ico, rank}.
    names — переименования из настроек: {key: {"name": …, "ico": …}}."""
    en = lang() == "en"
    meta = None
    if site:
        meta = next(({"key": k, "name": n[en], "ico": i, "rank": r} for dom, k, n, i, r in SITES
                     if site == dom or site.endswith("." + dom)),
                    {"key": "site:" + site, "name": site, "ico": "🌐", "rank": 5})
    else:
        a = (app or "").lower()
        meta = next(({"key": k, "name": n[en], "ico": i, "rank": r} for sub, k, n, i, r in SOURCES
                     if sub in a),
                    {"key": "other:" + a, "name": app or "—", "ico": "🔔", "rank": 9})
    over = (names or {}).get(meta["key"])
    if over:
        meta = dict(meta, name=over.get("name") or meta["name"], ico=over.get("ico") or meta["ico"])
    return meta


# ── профили ─────────────────────────────────────────────────────────────────

def _in_slot(slot, now):
    """Попадает ли момент в интервал расписания (через полночь — тоже)."""
    hm = now.strftime("%H:%M")
    frm, to = slot.get("from", "00:00"), slot.get("to", "24:00")
    day = now.weekday()
    if frm <= to:
        return day in slot.get("days", []) and frm <= hm < to
    # «22:00–07:00»: вечер дня из списка или утро следующего за ним
    return (day in slot.get("days", []) and hm >= frm) or \
        (((day - 1) % 7) in slot.get("days", []) and hm < to)


def active_profile(prefs, now=None):
    """id активного профиля ('' — без профиля)."""
    sel, profiles = prefs.get("profile") or "", prefs.get("profiles") or []
    if sel == "auto":
        now = now or datetime.now(catcher.MSK).replace(tzinfo=None)
        for p in profiles:
            if any(_in_slot(s, now) for s in p.get("schedule") or []):
                return p["id"]
        return ""
    return sel if any(p["id"] == sel for p in profiles) else ""


# ── правила ─────────────────────────────────────────────────────────────────

RULE_COLS = ("id", "src", "chat", "sender", "text", "text_mode", "action", "param", "profile")


class Rules:
    """Правила, действующие сейчас (всегдашние + активного профиля). ver — хэш:
    меняется при любой правке и при смене профиля, по нему виджет перечитывает доску."""

    def __init__(self, rows, profile=""):
        self.profile = profile
        self.rows = [r for r in rows if r["profile"] in ("", profile)]
        self.ver = hashlib.md5(json.dumps([self.rows, profile], ensure_ascii=False)
                               .encode()).hexdigest()[:12]
        self._re = {}
        for r in self.rows:
            if r["text"] and r["text_mode"] == "regex":
                try:
                    self._re[r["id"]] = re.compile(r["text"], re.I)
                except re.error:
                    self._re[r["id"]] = None      # битое выражение просто не срабатывает

    def _hit(self, r, src, chat, sender, text):
        """text/sender = None — «неизвестно» (строка чата в настройках): правила с
        таким условием не срабатывают."""
        if r["src"] not in (src, "*"):
            return False
        if r["chat"] and r["chat"] != chat:
            return False
        if r["sender"] and (sender is None or r["sender"] != sender):
            return False
        if r["text"]:
            if text is None:
                return False
            if r["text_mode"] == "regex":
                rx = self._re.get(r["id"])
                return bool(rx and rx.search(text))
            return r["text"].casefold() in text.casefold()
        return True

    @staticmethod
    def weight(r):
        return ((8 if r["text"] else 0) + (4 if r["sender"] else 0)
                + (2 if r["chat"] else 0) + (1 if r["src"] != "*" else 0))

    def matching(self, actions, src, chat, sender, text):
        return [r for r in self.rows
                if r["action"] in actions and self._hit(r, src, chat, sender, text)]

    def vis_rule(self, src, chat, sender, text):
        rs = self.matching(VIS_ACTIONS, src, chat, sender, text)
        return max(rs, key=lambda r: (self.weight(r), r["action"] == "show")) if rs else None

    def visible(self, src, chat, sender, text):
        r = self.vis_rule(src, chat, sender, text)
        return r is None or r["action"] == "show"

    def highlight_rule(self, src, chat, sender, text):
        rs = self.matching(("highlight",), src, chat, sender, text)
        return max(rs, key=self.weight) if rs else None

    def highlight(self, src, chat, sender, text):
        r = self.highlight_rule(src, chat, sender, text)
        return r["param"] if r else ""

    def mode(self, src):
        return "hide" if any(is_mode_rule(r) and r["src"] == src and r["action"] == "hide"
                             and r["profile"] == "" for r in self.rows) else "show"

    def source_hidden(self, src):
        """Источник скрыт целиком: режим-«скрывать» (в т.ч. профиля) и ни одного
        разрешающего правила — тогда виджет не рисует колонку."""
        hidden = any(is_mode_rule(r) and r["src"] == src and r["action"] == "hide" for r in self.rows)
        return hidden and not any(r["action"] == "show" and r["src"] in (src, "*")
                                  and not is_mode_rule(r) for r in self.rows)


def is_mode_rule(r):
    return r["src"] != "*" and not r["chat"] and not r["sender"] and not r["text"]


def all_rules(conn):
    return [dict(zip(RULE_COLS, row)) for row in conn.execute(
        f"SELECT {', '.join(RULE_COLS)} FROM rules ORDER BY id")]


def load(conn, prefs=None):
    """Правила, действующие сейчас (с учётом активного профиля)."""
    prefs = prefs or get_prefs(conn)
    return Rules(all_rules(conn), active_profile(prefs))


def clean_rule(d):
    """Правило из запроса → проверенный dict. ValueError — с текстом для человека."""
    def s(key, limit=500):
        v = d.get(key, "")
        if not isinstance(v, str) or len(v) > limit:
            raise ValueError(L(f"Поле «{key}» слишком длинное или не строка",
                               f"Field “{key}” is too long or not a string"))
        return v
    r = {"src": s("src", 200).strip(), "chat": s("chat"), "sender": s("sender"),
         "text": s("text"), "text_mode": d.get("text_mode") or "contains",
         "action": d.get("action"), "param": s("param", 20), "profile": s("profile", 40)}
    if not r["src"]:
        raise ValueError(L("Не указан источник", "No source given"))
    if r["action"] not in ACTIONS:
        raise ValueError(L("Неизвестное действие", "Unknown action"))
    if r["text_mode"] not in TEXT_MODES:
        raise ValueError(L("Неизвестный способ сравнения текста", "Unknown text match mode"))
    if not (r["chat"] or r["sender"] or r["text"]) and \
            not (r["src"] != "*" and r["action"] in VIS_ACTIONS):
        # без условия можно только «показывать/скрывать весь источник» (режим)
        raise ValueError(L("Нужно условие: чат, отправитель или текст",
                           "A condition is needed: chat, sender or text"))
    if r["action"] == "highlight":
        if r["param"] not in HIGHLIGHT_COLORS:
            raise ValueError(L("Не выбран цвет подсветки", "Pick a highlight colour"))
    else:
        r["param"] = ""
    if r["text"] and r["text_mode"] == "regex":
        try:
            re.compile(r["text"])
        except re.error as e:
            raise ValueError(L(f"В регулярном выражении ошибка: {e}", f"Regular expression error: {e}"))
    return r


def save_rule(conn, r):
    """Создать правило (или обновить param у такого же). Для show/hide у одного
    условия может быть только одно из двух — противоположное удаляем."""
    cond = (r["src"], r["chat"], r["sender"], r["text"], r["text_mode"])
    prof = r.get("profile", "")
    if r["action"] in VIS_ACTIONS:
        conn.execute("""DELETE FROM rules WHERE src = ? AND chat = ? AND sender = ? AND text = ?
                        AND text_mode = ? AND profile = ? AND action IN ('show', 'hide')
                        AND action != ?""", (*cond, prof, r["action"]))
    conn.execute(
        """INSERT INTO rules (src, chat, sender, text, text_mode, action, param, profile, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)
           ON CONFLICT(src, chat, sender, text, text_mode, action, profile)
           DO UPDATE SET param = excluded.param""",
        (*cond, r["action"], r["param"], prof, catcher.msk_time()))


def delete_rule(conn, rule_id):
    return conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,)).rowcount


def set_mode(conn, src, new_mode, profile=""):
    # «показывать всё» — поведение по умолчанию, отдельное правило не храним
    conn.execute("""DELETE FROM rules WHERE src = ? AND chat = '' AND sender = '' AND text = ''
                    AND profile = ? AND action IN ('show', 'hide')""", (src, profile))
    if new_mode == "hide":
        conn.execute("INSERT INTO rules (src, action, profile, created_at) VALUES (?, 'hide', ?, ?)",
                     (src, profile, catcher.msk_time()))


# ── настройки ───────────────────────────────────────────────────────────────

def get_prefs(conn):
    prefs = json.loads(json.dumps(PREF_DEFAULTS))
    for k, v in conn.execute("SELECT key, value FROM prefs"):
        if k in prefs:
            try:
                val = json.loads(v)
            except ValueError:
                continue
            if isinstance(prefs[k], dict) and isinstance(val, dict):
                prefs[k].update(val)          # вложенные: новые ключи получают значения по умолчанию
            else:
                prefs[k] = val
    try:
        prefs["themed"] = clean_themed(prefs["themed"])
    except (ValueError, TypeError, AttributeError):
        prefs["themed"] = json.loads(json.dumps(PREF_DEFAULTS["themed"]))
    return prefs


def prefs_ver(prefs):
    view = {k: prefs.get(k) for k in DISPLAY_PREFS}
    return hashlib.md5(json.dumps(view, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


_RE_HM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")
_RE_ID = re.compile(r"^[a-z0-9_-]{1,40}$")
_RE_BIND = re.compile(r"^(\d{1,3}(\.\d{1,3}){3}|localhost|\[[0-9a-f:]+\]):\d{2,5}$")


def _clean_pref(k, v):
    bad = ValueError(L(f"Неверное значение настройки «{k}»", f"Invalid value for setting “{k}”"))
    if k == "language":
        if v not in ("auto", "ru", "en"):
            raise bad
        return v
    if k == "opacity":
        return round(min(1.0, max(0.3, float(v))), 2)
    if k == "font_size":
        return int(min(18, max(11, int(v))))
    if k in ("compact", "group_by_chat", "avatars", "update_check"):
        return bool(v)
    if k == "theme":
        if v not in ("dark", "light"):
            raise bad
        return v
    if k == "mail_channel":
        if v not in ("notify", "imap"):
            raise bad
        return v
    if k in ("col_order", "hidden_cols", "closed_cols"):
        return [str(x)[:200] for x in list(v)][:100]
    if k == "mentions":
        out = []
        for x in v:
            x = str(x).strip()
            if x and len(x) <= 60 and x.casefold() not in (o.casefold() for o in out):
                out.append(x)
        return out[:50]
    if k == "source_names":
        out = {}
        for key, o in dict(v).items():
            name, ico = str(o.get("name", "")).strip()[:40], str(o.get("ico", "")).strip()[:8]
            if name or ico:
                out[str(key)[:200]] = {"name": name, "ico": ico}
        return out
    if k == "profiles":
        out = []
        for p in list(v)[:20]:
            pid, name = str(p.get("id", "")), str(p.get("name", "")).strip()[:40]
            if not _RE_ID.match(pid) or not name or any(o["id"] == pid for o in out):
                raise ValueError(L("У профиля нужны уникальный id и название",
                                   "A profile needs a unique id and a name"))
            sched = []
            for slot in list(p.get("schedule") or [])[:14]:
                days = sorted({int(d) for d in slot.get("days", []) if 0 <= int(d) <= 6})
                frm, to = str(slot.get("from", "")), str(slot.get("to", ""))
                if not days or not _RE_HM.match(frm) or not _RE_HM.match(to) or frm == to:
                    raise ValueError(L("В расписании профиля нужны дни и время «с–по»",
                                       "A profile schedule needs days and a from–to time"))
                sched.append({"days": days, "from": frm, "to": to})
            out.append({"id": pid, "name": name, "schedule": sched})
        return out
    if k == "profile":
        v = str(v)
        if v not in ("", "auto") and not _RE_ID.match(v):
            raise bad
        return v
    if k == "retention_days":
        return int(min(3650, max(0, int(v))))
    if k == "backup":
        return {"enabled": bool(v.get("enabled", True)), "keep": int(min(60, max(1, int(v.get("keep", 7)))))}
    if k == "report":
        t = str(v.get("time", "09:00"))
        if not _RE_HM.match(t) or t == "24:00":
            raise bad
        return {"enabled": bool(v.get("enabled")), "weekday": int(min(6, max(0, int(v.get("weekday", 0))))),
                "time": t}
    if k == "rag":
        model = str(v.get("model", "bge-m3")).strip()[:100] or "bge-m3"
        return {"enabled": bool(v.get("enabled")), "model": model,
                "chat_model": str(v.get("chat_model", "")).strip()[:100]}
    if k == "ingest_bind":
        v = str(v).strip()
        if v and not _RE_BIND.match(v):
            raise ValueError(L("Адрес — в виде 0.0.0.0:8766", "Address must look like 0.0.0.0:8766"))
        return v
    if k == "themed":
        return clean_themed(v)
    if k in STATE_PREFS:
        return str(v)[:40]
    raise ValueError(L(f"Неизвестная настройка «{k}»", f"Unknown setting “{k}”"))


LOG_LINES = (0, 10, 20, 50)


def clean_themed(v, base=None):
    """Настройки тематических колонок: недостающее — по умолчанию (или из base — текущих)."""
    base = base or PREF_DEFAULTS["themed"]
    out = {}
    for col, defaults in PREF_DEFAULTS["themed"].items():
        cur = dict(defaults, **(base.get(col) or {}))
        new = dict(v.get(col) or {}) if isinstance(v, dict) else {}
        for key, dv in defaults.items():
            val = new.get(key, cur.get(key, dv))
            if isinstance(dv, bool):
                val = bool(val)
            elif key == "log_lines":
                val = int(val)
                if val not in LOG_LINES:
                    raise ValueError(L("Строк лога — 0, 10, 20 или 50", "Log lines must be 0, 10, 20 or 50"))
            elif key == "ignore":
                items = val.split(",") if isinstance(val, str) else list(val)
                val = [str(x).strip()[:80] for x in items if str(x).strip()][:30]
            out.setdefault(col, {})[key] = val
    return out


def themed(prefs):
    """Настройки тематических колонок с умолчаниями на месте (get_prefs вкладывает только верхний уровень)."""
    return clean_themed(prefs.get("themed") or {})


def set_prefs(conn, patch):
    if not isinstance(patch, dict):
        raise ValueError(L("Ожидался объект настроек", "Expected a settings object"))
    for k, v in patch.items():
        try:
            # тематические колонки меняют по одной настройке — остальное берём из сохранённого
            val = clean_themed(v, get_prefs(conn)["themed"]) if k == "themed" else _clean_pref(k, v)
        except (TypeError, AttributeError, KeyError):
            raise ValueError(L(f"Неверное значение настройки «{k}»", f"Invalid value for setting “{k}”"))
        conn.execute("INSERT INTO prefs (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (k, json.dumps(val, ensure_ascii=False)))
        if k == "profiles":       # удалённые профили забирают с собой свои правила
            ids = [p["id"] for p in val]
            if ids:
                conn.execute("DELETE FROM rules WHERE profile != '' AND profile NOT IN "
                             f"({','.join('?' * len(ids))})", ids)
            else:
                conn.execute("DELETE FROM rules WHERE profile != ''")


def mention_re(names):
    """Упоминания: совпадение с НАЧАЛА слова, без учёта регистра — «Иван»
    найдёт и «Ивану», но не «Диван»."""
    names = sorted({n.strip() for n in names if n.strip()}, key=len, reverse=True)
    if not names:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, names)) + ")", re.I)


# ── действия при записи (collect.py → catcher.run(on_insert=…), приём событий) ──

def apply_on_insert(conn, rec):
    """Выполнить действия правил «сразу прочитано», «закрепить», «звук»,
    «переслать в Telegram» для только что записанного уведомления и записать,
    что сработало (rule_hits — для «почему так»)."""
    import actions   # тут, а не наверху: serve/settings без collect звук и сеть не трогают
    prefs = get_prefs(conn)
    rs = load(conn, prefs)
    meta = source_of(rec["app"], rec.get("site", ""), prefs["source_names"])
    hits = rs.matching(INSERT_ACTIONS, meta["key"], rec["chat"], rec["sender"], rec["message"] or "")
    done = {r["action"] for r in hits}
    # закрытая колонка открывается снова, как только в ней появится что показать
    if meta["key"] in prefs["closed_cols"] and "read" not in done and \
            rs.visible(meta["key"], rec["chat"], rec["sender"], rec["message"] or ""):
        set_prefs(conn, {"closed_cols": [k for k in prefs["closed_cols"] if k != meta["key"]]})
    if "pin" in done:
        done.discard("read")                     # закрепить главнее «сразу прочитано»
        conn.execute("UPDATE messages SET pinned = 1 WHERE id = ?", (rec["id"],))
    if "read" in done:
        conn.execute("UPDATE messages SET is_read = 1, read_at = ? WHERE id = ?",
                     (catcher.msk_time(), rec["id"]))
    now = catcher.msk_time()
    for r in hits:
        if r["action"] in done:
            conn.execute("INSERT INTO rule_hits (message_id, rule_id, action, at) VALUES (?,?,?,?)",
                         (rec["id"], r["id"], r["action"], now))
    conn.commit()
    if "sound" in done:
        actions.play_sound()
    if "forward" in done:
        actions.forward(meta, rec)
    return sorted(done)


def why(conn, mid):
    """Почему сообщение видно/скрыто/подсвечено/закреплено — для виджета и истории."""
    row = conn.execute("""SELECT id, app, COALESCE(site, ''), chat, sender, message, is_read,
                                 read_at, pinned, snooze_until FROM messages WHERE id = ?""",
                       (mid,)).fetchone()
    if not row:
        return None
    _, app, site, chat, sender, text, is_read, read_at, pinned, snooze = row
    prefs = get_prefs(conn)
    rs = load(conn, prefs)
    meta = source_of(app, site, prefs["source_names"])
    by_id = {r["id"]: r for r in all_rules(conn)}
    hits = [{"action": a, "at": at, "rule": by_id.get(rid)}
            for rid, a, at in conn.execute(
                "SELECT rule_id, action, at FROM rule_hits WHERE message_id = ? ORDER BY rowid", (mid,))]
    return {"id": mid, "source": meta, "visible": rs.visible(meta["key"], chat, sender, text or ""),
            "vis_rule": rs.vis_rule(meta["key"], chat, sender, text or ""),
            "highlight_rule": rs.highlight_rule(meta["key"], chat, sender, text or ""),
            "insert_hits": hits, "is_read": is_read, "read_at": read_at, "pinned": pinned,
            "snooze_until": snooze, "profile": rs.profile}


# ── выгрузка / загрузка правил и настроек ───────────────────────────────────

def export_config(conn):
    prefs = get_prefs(conn)
    return {"app": version.APP_NAME, "version": version.__version__, "exported_at": catcher.msk_time(),
            "prefs": {k: v for k, v in prefs.items() if k not in STATE_PREFS},
            "rules": [{k: r[k] for k in RULE_COLS if k != "id"} for r in all_rules(conn)]}


def import_config(conn, data, replace=False):
    """Загрузить выгрузку export_config. replace — сначала удалить все правила.
    Битые правила пропускаются и попадают в errors — остальное загружается."""
    if not isinstance(data, dict) or not isinstance(data.get("rules", []), list):
        raise ValueError(L("Это не файл настроек этой программы", "This is not a settings file of this app"))
    prefs = {k: v for k, v in (data.get("prefs") or {}).items()
             if k in PREF_DEFAULTS and k not in STATE_PREFS}
    if "profiles" in prefs:
        set_prefs(conn, {"profiles": prefs.pop("profiles")})   # сначала профили — к ним привязаны правила
    if replace:
        conn.execute("DELETE FROM rules")
    added, errors = 0, []
    for i, raw in enumerate(data.get("rules", [])):
        try:
            save_rule(conn, clean_rule(raw))
            added += 1
        except ValueError as e:
            errors.append(f"#{i + 1}: {e}")
    set_prefs(conn, prefs)
    return {"rules": added, "errors": errors}


# ── данные для окна настроек ────────────────────────────────────────────────

def _names(conn):
    return get_prefs(conn)["source_names"]


def all_sources(conn):
    """Все источники, что когда-либо писали: {key: meta + apps}."""
    names, out = _names(conn), {}
    for app, site in conn.execute("SELECT DISTINCT app, COALESCE(site, '') FROM messages"):
        s = source_of(app, site, names)
        o = out.setdefault(s["key"], dict(s, apps=[]))
        label = site or app
        if label not in o["apps"]:
            o["apps"].append(label)
    return out


def overview(conn):
    """Список источников: сколько сообщений и чатов, режим, число правил."""
    prefs = get_prefs(conn)
    rs, names, rows, out = load(conn, prefs), prefs["source_names"], all_rules(conn), {}
    for app, site, chat, n, last in conn.execute(
            """SELECT app, COALESCE(site, ''), chat, COUNT(*), MAX(received_at)
               FROM messages GROUP BY app, site, chat"""):
        s = source_of(app, site, names)
        o = out.setdefault(s["key"], dict(s, apps=[], n=0, chats=set(), last=""))
        if (site or app) not in o["apps"]:
            o["apps"].append(site or app)
        o["n"] += n
        o["chats"].add(chat or "")
        o["last"] = max(o["last"], last or "")
    res = []
    for o in out.values():
        o["chats"] = len(o["chats"])
        o["mode"] = rs.mode(o["key"])
        o["rules"] = sum(1 for r in rows if r["src"] == o["key"] and not
                         (is_mode_rule(r) and r["profile"] == ""))
        res.append(o)
    return sorted(res, key=lambda o: (o["rank"], o["name"]))


def detail(conn, src):
    """Один источник: режим, правила и «кто писал» — чаты с отправителями внутри,
    для каждой строки — видно ли её в виджете сейчас и каким правилом это решено
    (правила по тексту тут не учитываются: у строки нет конкретного текста)."""
    prefs = get_prefs(conn)
    rs, names = load(conn, prefs), prefs["source_names"]
    meta, chats = None, {}
    for app, site, chat, sender, bot, n, last in conn.execute(
            """SELECT app, COALESCE(site, ''), chat, sender, MAX(is_bot), COUNT(*),
                      MAX(received_at) FROM messages GROUP BY app, site, chat, sender"""):
        s = source_of(app, site, names)
        if s["key"] != src:
            continue
        meta = meta or s
        chat, sender = chat or "", sender or ""
        c = chats.setdefault(chat, {"chat": chat, "n": 0, "last": "", "bot": 0, "senders": {}})
        e = c["senders"].setdefault(sender, {"sender": sender, "n": 0, "last": "", "bot": 0})
        for x in (c, e):
            x["n"] += n
            x["last"] = max(x["last"], last or "")
            x["bot"] = max(x["bot"], bot or 0)

    res = []
    for c in chats.values():
        senders = sorted(c["senders"].values(), key=lambda e: e["last"], reverse=True)
        # личка: единственный отправитель и есть собеседник (= название чата)
        c["personal"] = len(senders) == 1 and senders[0]["sender"] == c["chat"]
        for e in senders:
            e["rule"] = rs.vis_rule(src, c["chat"], e["sender"], None)
            e["show"] = e["rule"] is None or e["rule"]["action"] == "show"
        c["senders"] = senders
        # групповой чат: что будет с сообщением от «нового» отправителя;
        # личка: пишет только собеседник — решает то же, что для него
        c["rule"] = senders[0]["rule"] if c["personal"] else rs.vis_rule(src, c["chat"], None, None)
        c["show"] = c["rule"] is None or c["rule"]["action"] == "show"
        res.append(c)
    res.sort(key=lambda c: c["last"], reverse=True)
    if meta is None:   # сообщений из источника нет (например, удалены) — знаем только ключ
        over = names.get(src, {})
        meta = {"key": src, "name": over.get("name") or src, "ico": over.get("ico") or "🔔", "rank": 9}
    rows = all_rules(conn)
    return {
        "source": meta,
        "custom": names.get(src, {}),
        "mode": rs.mode(src),
        "rules": [r for r in rows if r["src"] == src and not (is_mode_rule(r) and r["profile"] == "")],
        "global_rules": sum(1 for r in rows if r["src"] == "*"),
        "profiles": prefs["profiles"],
        "active_profile": rs.profile,
        "chats": res,
    }


def global_rules(conn):
    """Правила для всех источников + список источников (для подсказок в форме)."""
    prefs = get_prefs(conn)
    srcs = sorted(all_sources(conn).values(), key=lambda s: (s["rank"], s["name"]))
    rows = all_rules(conn)
    counts = {}
    for r in rows:
        if r["profile"]:
            counts[r["profile"]] = counts.get(r["profile"], 0) + 1
    return {"rules": [r for r in rows if r["src"] == "*"],
            "profiles": prefs["profiles"], "profile_counts": counts,
            "sources": [{k: s[k] for k in ("key", "name", "ico")} for s in srcs]}
