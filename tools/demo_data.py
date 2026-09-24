#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Демо-данные для скриншотов и знакомства с программой — ВСЁ ВЫМЫШЛЕННОЕ.

    python3 tools/demo_data.py --home /tmp/messhub-demo            # русские данные
    python3 tools/demo_data.py --home /tmp/messhub-demo-en --lang en
    MESSHUB_HOME=/tmp/messhub-demo python3 app/serve.py --db /tmp/messhub-demo/share/messages.db --port 8799

Создаёт в --home (как MESSHUB_HOME) базу, настройки, правила, профили, два почтовых ящика
(несуществующие адреса example.com), ключ приёма событий, резервную копию, карточки
тематических колонок (контейнеры, службы, команды) и журнал программы. Живые данные
программы не трогает: всё, что пишется, — внутри --home. Имена, чаты и тексты придуманы;
настоящие уведомления сюда класть нельзя (см. CONTRIBUTING.md, «Что можно публиковать»).
"""

import argparse
import json
import os
import random
import sqlite3
import sys
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── тексты: свежие (видны в виджете) и неделя истории (статистика, поиск) ──────
# (app, заголовок уведомления, тело, минут назад, доп. поля)
RECENT = {
    "ru": [
        ("eXpress", "Команда разработки", "Ирина Соколова: Алексей, посмотри, пожалуйста, ревью до обеда", 12, {}),
        ("eXpress", "Команда разработки", "Павел Орлов: Сборка 2.4 ушла на тестовый стенд", 26, {}),
        ("eXpress", "Команда разработки", "Ирина Соколова: И ещё: созвон переносим на 16:00", 41, {}),
        ("eXpress", "Марина Кузнецова", "Скинешь макет главной? Прошлая версия — https://example.com/mockups/v3", 55, {}),
        ("eXpress", "Олег Никитин", "Нужен отчёт по проекту к пятнице", 190, {"pinned": 1}),
        ("eXpress", "Флуд", "Дмитрий Белов: Кто идёт на обед?", 20, {}),
        ("telegram-desktop", "Мама", "Позвони, как освободишься", 33, {}),
        ("telegram-desktop", "Семья", "Папа: Купил билеты на субботу 🎉", 64, {}),
        ("telegram-desktop", "Книжный клуб", "Лена: В четверг обсуждаем вторую часть", 125, {}),
        ("yandex-browser", "Чат дома", "web.max.ru\n\nУправляющая: Завтра с 10 до 14 отключат воду", 118, {}),
        ("yandex-browser", "Тренер", "web.whatsapp.com\n\nТренировка в среду в 19:30, не опаздывай", 250, {}),
        ("mail-imap", "Работа", "Бухгалтерия\nРасчётный листок за сентябрь\nДобрый день! Во вложении расчётный листок.", 70, {"has_media": 1}),
        ("mail-imap", "Личная", "Интернет-провайдер\nСчёт за октябрь\nСумма к оплате — 650 ₽, срок до 10 числа.", 300, {}),
        ("CI", "CI: main", "Сборка #413 прошла за 6 мин", 15, {}),
    ],
    "en": [
        ("eXpress", "Dev team", "Emma Wilson: Alex, could you look at the review before lunch?", 12, {}),
        ("eXpress", "Dev team", "Paul Carter: Build 2.4 is on the staging server", 26, {}),
        ("eXpress", "Dev team", "Emma Wilson: Also, the call moves to 4 pm", 41, {}),
        ("eXpress", "Mary Brooks", "Can you send the home page mockup? Last version — https://example.com/mockups/v3", 55, {}),
        ("eXpress", "Oliver Grant", "I need the project report by Friday", 190, {"pinned": 1}),
        ("eXpress", "Random", "David Hall: Who's up for lunch?", 20, {}),
        ("telegram-desktop", "Mom", "Call me when you're free", 33, {}),
        ("telegram-desktop", "Family", "Dad: Got the tickets for Saturday 🎉", 64, {}),
        ("telegram-desktop", "Book club", "Kate: On Thursday we discuss part two", 125, {}),
        ("yandex-browser", "Building chat", "web.max.ru\n\nManager: Water will be off tomorrow 10 am – 2 pm", 118, {}),
        ("yandex-browser", "Coach", "web.whatsapp.com\n\nPractice on Wednesday at 7:30 pm, don't be late", 250, {}),
        ("mail-imap", "Work", "Payroll\nYour September payslip\nHello! Your payslip is attached.", 70, {"has_media": 1}),
        ("mail-imap", "Personal", "Internet provider\nOctober invoice\nAmount due: $12, due by the 10th.", 300, {}),
        ("CI", "CI: main", "Build #413 passed in 6 min", 15, {}),
    ],
}

# тематические колонки: (колонка, чат, отправитель, текст, минут назад, хвост лога, ключ, «починилось» минут назад)
SHOP_LOG = """2026-09-24 18:41:07 INFO  shop-api: listening on :8080
2026-09-24 18:41:09 INFO  connecting to postgres://shop-db:5432/shop
2026-09-24 18:41:39 ERROR connection to shop-db timed out after 30s
2026-09-24 18:41:39 FATAL cannot start without a database, exiting"""
BACKUP_LOG = """2026-09-24T03:00:01 backup-nightly[4120]: rsync -a /srv/photos nas:/backup/photos
2026-09-24T03:12:44 backup-nightly[4120]: rsync: write failed on "/backup/photos": No space left on device (28)
2026-09-24T03:12:44 backup-nightly[4120]: rsync error: error in file IO (code 11)
2026-09-24T03:12:44 systemd[1]: backup-nightly.service: Main process exited, status=23"""
BUILD_LOG = """src/cart/Total.vue:41:7
  error  'discount' is not defined  no-undef
✖ 1 problem (1 error, 0 warnings)
ERROR: build failed"""
THEMED = {
    "ru": [
        ("containers", "shop-api", "shop", "упал с кодом 1 · 3-й раз за 10 минут", 3, SHOP_LOG, "container:podman:shop-api", None, 2),
        ("containers", "shop-db", "shop", "healthcheck: нездоров (unhealthy)", 9, "", "container:podman:shop-db", 5, 2),
        ("services", "backup-nightly.service", "системная служба",
         "служба завершилась с кодом 23\nНочная копия фотографий на NAS", 400, BACKUP_LOG, "unit:system:backup-nightly.service", None, 2),
        ("commands", "make release", "shop", "готово за 4 мин 12 с", 8, "", "", None, 1),
        ("commands", "npm run build", "shop-web", "ошибка (код 1) через 38 с", 30, BUILD_LOG, "cmd:~/shop-web\nnpm run build", 14, 2),
    ],
    "en": [
        ("containers", "shop-api", "shop", "crashed with code 1 · 3 times in 10 minutes", 3, SHOP_LOG, "container:podman:shop-api", None, 2),
        ("containers", "shop-db", "shop", "healthcheck: unhealthy", 9, "", "container:podman:shop-db", 5, 2),
        ("services", "backup-nightly.service", "system service",
         "service exited with code 23\nNightly photo backup to the NAS", 400, BACKUP_LOG, "unit:system:backup-nightly.service", None, 2),
        ("commands", "make release", "shop", "done in 4m 12s", 8, "", "", None, 1),
        ("commands", "npm run build", "shop-web", "failed (code 1) after 38s", 30, BUILD_LOG, "cmd:~/shop-web\nnpm run build", 14, 2),
    ],
}

# журнал программы (раздел «Логи»): (минут назад, уровень, процесс, текст)
LOGS = {
    "ru": [
        (1440, "info", "collect", "messhub — сбор → ~/.local/share/messhub/messages.db"),
        (1439, "info", "collect", "Контейнеры: слушаю события podman"),
        (1439, "error", "collect", "Контейнеры: docker events завершился: permission denied while trying to connect to the Docker daemon socket"),
        (1438, "info", "collect", "Службы: слежу за упавшими службами"),
        (1437, "info", "widget", "[widget] messhub — окно доски"),
        (720, "info", "collect", "Резервная копия: messages-auto.db"),
        (95, "warn", "collect", "Почта «Личная»: сервер не отвечает (таймаут), попробую через 2 мин"),
        (93, "info", "collect", "Почта «Личная»: новых писем 1"),
        (70, "info", "collect", "Почта «Работа»: новых писем 1"),
        (12, "info", "collect", "Правила для #412: highlight"),
        (2, "info", "collect", "Правила для #431: pin"),
    ],
    "en": [
        (1440, "info", "collect", "messhub — collector → ~/.local/share/messhub/messages.db"),
        (1439, "info", "collect", "Containers: listening to podman events"),
        (1439, "error", "collect", "Containers: docker events exited: permission denied while trying to connect to the Docker daemon socket"),
        (1438, "info", "collect", "Services: watching for failed services"),
        (1437, "info", "widget", "[widget] messhub — board window"),
        (720, "info", "collect", "Backup: messages-auto.db"),
        (95, "warn", "collect", "Mail “Personal”: server not responding (timeout), retrying in 2 min"),
        (93, "info", "collect", "Mail “Personal”: 1 new message"),
        (70, "info", "collect", "Mail “Work”: 1 new message"),
        (12, "info", "collect", "Rules for #412: highlight"),
        (2, "info", "collect", "Rules for #431: pin"),
    ],
}

HISTORY = {
    "ru": {
        "work": [("eXpress", "Команда разработки", ["Ирина Соколова", "Павел Орлов", "Сергей Лебедев"]),
                 ("eXpress", "Флуд", ["Дмитрий Белов", "Света Морозова"]),
                 ("eXpress", "Марина Кузнецова", None), ("eXpress", "Олег Никитин", None)],
        "home": [("telegram-desktop", "Мама", None), ("telegram-desktop", "Семья", ["Папа", "Брат"]),
                 ("telegram-desktop", "Книжный клуб", ["Лена", "Ника"]),
                 ("yandex-browser/web.max.ru", "Чат дома", ["Сосед", "Управляющая"])],
        "texts": ["Ок, понял", "Сделаю к вечеру", "Посмотри, когда будет минутка", "Созвон в 11:00",
                  "Спасибо!", "Выложил новую версию", "Кто сегодня в офисе?", "Напомни про документы",
                  "Готово", "Завтра созвон переносится", "Отправил на почту", "Давай обсудим после обеда",
                  "Плюс", "Нашёл ошибку в расчёте, поправлю", "Во сколько встречаемся?", "Купи хлеба, пожалуйста"],
    },
    "en": {
        "work": [("eXpress", "Dev team", ["Emma Wilson", "Paul Carter", "Sam Taylor"]),
                 ("eXpress", "Random", ["David Hall", "Lucy Moore"]),
                 ("eXpress", "Mary Brooks", None), ("eXpress", "Oliver Grant", None)],
        "home": [("telegram-desktop", "Mom", None), ("telegram-desktop", "Family", ["Dad", "Ben"]),
                 ("telegram-desktop", "Book club", ["Kate", "Nina"]),
                 ("yandex-browser/web.max.ru", "Building chat", ["Neighbor", "Manager"])],
        "texts": ["OK, got it", "Will do by tonight", "Take a look when you have a minute", "Call at 11:00",
                  "Thanks!", "Pushed a new version", "Who's in the office today?", "Remind me about the papers",
                  "Done", "Tomorrow's call is moved", "Sent it by email", "Let's discuss after lunch",
                  "+1", "Found a bug in the numbers, fixing", "What time do we meet?", "Please buy bread"],
    },
}

L10N = {
    "ru": {"mentions": ["Алексей", "Лёша"], "names": {"other:ci": {"name": "Сборки", "ico": "🔔"}},
           "profiles": ("Работа", "Дом"), "flood": "Флуд", "boss": "Олег Никитин", "lead": "Ирина Соколова",
           "club": "Книжный клуб", "water": "отключат", "urgent": "срочно", "fail": "упала",
           "accounts": [("Работа", "alex@example.com", "imap.example.com"),
                        ("Личная", "alex.home@example.org", "imap.example.org")]},
    "en": {"mentions": ["Alex"], "names": {"other:ci": {"name": "Builds", "ico": "🔔"}},
           "profiles": ("Work", "Home"), "flood": "Random", "boss": "Oliver Grant", "lead": "Emma Wilson",
           "club": "Book club", "water": "off tomorrow", "urgent": "urgent", "fail": "failed",
           "accounts": [("Work", "alex@example.com", "imap.example.com"),
                        ("Personal", "alex.home@example.org", "imap.example.org")]},
}

COLORS = [(91, 155, 255), (62, 201, 143), (245, 159, 69), (184, 132, 255), (255, 107, 107), (226, 194, 59)]


def avatar_png(rgb, size=48):
    """Кружок с мягким градиентом — вместо фотографий (настоящих лиц в демо нет)."""
    import avatars
    rows, r = [], size / 2
    for y in range(size):
        row = bytearray()
        for x in range(size):
            d = ((x - r + .5) ** 2 + (y - r + .5) ** 2) ** .5
            k = 1 - 0.35 * y / size
            a = 255 if d < r - 1 else (int(255 * (r - d)) if d < r else 0)
            row += bytes((int(rgb[0] * k), int(rgb[1] * k), int(rgb[2] * k), max(0, a)))
        rows.append(bytes(row))
    return avatars.png_bytes(size, size, rows, True)


def build(home, lang):
    os.environ["MESSHUB_HOME"] = home
    for k in ("MESSHUB_MAIL_CFG", "MESSHUB_FORWARD_CFG"):
        os.environ.pop(k, None)
    sys.path.insert(0, os.path.join(HERE, "app"))
    import avatars
    import backup
    import catcher
    import ingest
    import mail
    import paths
    import rules

    paths.ensure_dirs()
    db = paths.DB_PATH
    for s in ("", "-wal", "-shm"):
        if os.path.exists(db + s):
            os.remove(db + s)
    catcher.init_db(db).close()
    conn = sqlite3.connect(db)
    rnd = random.Random(413)
    now = datetime.now()
    t = L10N[lang]

    av = {}

    def face(name):
        if name not in av:
            av[name] = avatars._save(avatar_png(COLORS[len(av) % len(COLORS)]))
        return av[name]

    def put(app, summary, body, when, read, extra=None):
        site = ""
        if "/" in app:                        # «приложение/сайт» — веб-уведомление браузера
            app, site = app.split("/")
            body = f"{site}\n\n{body}"
        if app == "mail-imap":
            sender, subject, rest = (body.split("\n", 2) + ["", ""])[:3]
            chat, message = summary, subject + ("\n" + rest if rest else "")
        else:
            chat, sender, message, site = catcher.parse_fields(app, summary, body)
        rec = {"app": app, "chat": chat, "sender": sender, "is_bot": 0, "message": message,
               "notification_id": 0, "urgency": 1, "has_media": 0, "event_ts": when.timestamp(),
               "event_iso": when.isoformat(timespec="seconds"), "raw_summary": summary, "raw_body": body,
               "site": site, "avatar": face(sender) if app in ("eXpress", "telegram-desktop") else None}
        rec.update({k: v for k, v in (extra or {}).items() if k in ("has_media",)})
        mid = catcher.insert(conn, rec)
        hours = (datetime.now() - when).total_seconds() / 3600
        conn.execute("UPDATE messages SET received_at = ?, is_read = ?, read_at = ?, pinned = ? WHERE id = ?",
                     (catcher.msk_time(hours), read, catcher.msk_time(max(0, hours - 1)) if read else None,
                      (extra or {}).get("pinned", 0), mid))
        return mid

    # неделя истории: рабочие чаты — будни днём, личные — вечером и в выходные
    hist = HISTORY[lang]
    for day in range(7, 0, -1):
        date = now - timedelta(days=day)
        weekend = date.weekday() >= 5
        for _ in range(rnd.randint(14, 22)):
            if not weekend and rnd.random() < 0.62:
                app, chat, who = rnd.choice(hist["work"])
                hour = rnd.choice([9, 10, 10, 11, 11, 12, 14, 15, 15, 16, 17, 18])
            else:
                app, chat, who = rnd.choice(hist["home"])
                hour = rnd.choice([8, 12, 19, 19, 20, 20, 21, 21, 22] if not weekend else [10, 12, 13, 15, 17, 19, 20])
            when = date.replace(hour=hour, minute=rnd.randint(0, 59), second=0, microsecond=0)
            text = rnd.choice(hist["texts"])
            put(app, chat, f"{rnd.choice(who)}: {text}" if who else text, when, 1)

    for app, summary, body, ago, extra in RECENT[lang]:
        put(app, summary, body, now - timedelta(minutes=ago), 0, extra)
    conn.commit()

    # тематические колонки: контейнеры, службы, команды (одна карточка уже «починилась»)
    import events
    for col, chat, sender, text, ago, details, key, fixed, urg in THEMED[lang]:
        mid = events.emit(conn, col, chat, text, sender=sender, details=details, key=key, urgency=urg)
        when = now - timedelta(minutes=ago)
        conn.execute("UPDATE messages SET received_at = ?, event_ts = ?, event_iso = ?, resolved_at = ? WHERE id = ?",
                     (catcher.msk_time(ago / 60), when.timestamp(), when.isoformat(timespec="seconds"),
                      catcher.msk_time(fixed / 60) if fixed is not None else None, mid))
    conn.commit()

    # журнал программы: несколько записей за сутки
    os.makedirs(paths.LOG_DIR, exist_ok=True)
    for src in ("collect", "widget"):
        with open(os.path.join(paths.LOG_DIR, f"{src}.log"), "w", encoding="utf-8") as f:
            for ago, lvl, s_, text in LOGS[lang]:
                if s_ == src:
                    t_ = (now - timedelta(minutes=ago)).strftime("%Y-%m-%d %H:%M:%S")
                    f.write(json.dumps({"t": t_, "lvl": lvl, "src": src, "msg": text}, ensure_ascii=False) + "\n")

    # правила «как в почте» — вид в настройках и подсветка на доске
    def rule(**r):
        rules.save_rule(conn, rules.clean_rule(r))
    fwd = {"token": "123456789:demo-token-not-real", "chat_id": "-1001234567890", "thread_id": ""}
    paths.write_private(paths.FORWARD_CFG, json.dumps(fwd))
    rule(src="express", chat=t["flood"], action="hide")
    rule(src="express", sender=t["boss"], action="pin")
    rule(src="express", sender=t["lead"], action="highlight", param="blue")
    rule(src="max", text=t["water"], action="highlight", param="orange")
    rule(src="*", text=t["urgent"], action="sound")
    rule(src="other:ci", text=t["fail"], action="forward")
    rule(src="telegram", chat=t["club"], action="hide", profile="work")
    rule(src="express", action="hide", profile="home")
    conn.commit()

    rules.set_prefs(conn, {
        "language": lang, "mentions": t["mentions"], "source_names": t["names"],
        "col_order": ["express", "telegram", "mail", "max", "whatsapp", "containers", "services", "commands"],
        # общие снимки — без тематических колонок; для снимка ИТ-колонок screenshots.py скрывает остальные
        "hidden_cols": ["containers", "services", "commands"],
        "themed": {"containers": {"enabled": True}, "services": {"enabled": True}, "commands": {"enabled": True}},
        "profiles": [{"id": "work", "name": t["profiles"][0],
                      "schedule": [{"days": [0, 1, 2, 3, 4], "from": "09:00", "to": "18:00"}]},
                     {"id": "home", "name": t["profiles"][1],
                      "schedule": [{"days": [0, 1, 2, 3, 4], "from": "18:00", "to": "24:00"},
                                   {"days": [5, 6], "from": "00:00", "to": "24:00"}]}],
        "profile": "", "mail_channel": "imap", "retention_days": 180,
        "report": {"enabled": True, "weekday": 0, "time": "09:00"}, "update_check": True,
    })
    conn.commit()

    # почта: два ящика на несуществующих серверах example.com/.org, «проверены» только что
    accounts = []
    for i, (label, user, host) in enumerate(t["accounts"]):
        accounts.append({"id": f"demo{i}", "label": label, "host": host, "port": 993, "security": "ssl",
                         "user": user, "password": "demo", "folder": "INBOX", "interval": 2,
                         "enabled": True, "insecure": False})
        conn.execute("INSERT OR REPLACE INTO mail_state (account, uidvalidity, last_uid, checked_at) "
                     "VALUES (?, 1, 100, ?)", (f"demo{i}", catcher.msk_time(0.02)))
    mail._write(accounts)
    conn.commit()
    conn.close()

    ingest.new_token()
    backup.make(db, "auto")
    time.sleep(1.1)
    backup.make(db, "manual")
    return db


def main():
    ap = argparse.ArgumentParser(description="Вымышленные данные messhub для скриншотов")
    ap.add_argument("--home", required=True, help="папка вроде MESSHUB_HOME (будет перезаписана)")
    ap.add_argument("--lang", choices=("ru", "en"), default="ru")
    a = ap.parse_args()
    print(build(os.path.abspath(a.home), a.lang))


if __name__ == "__main__":
    main()
