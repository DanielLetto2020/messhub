"""Сбор на macOS без Mac: поддельная база Центра уведомлений (схема и plist — как у macOS 14–27)."""
import os
import plistlib
import sqlite3
import tempfile
import unittest

import common
import catcher
import maccatcher


def fake_db(path, rows):
    """rows: [(bundle id, {plist}, delivered_date)] — как пишет usernoted."""
    if os.path.exists(path):
        os.remove(path)
    c = sqlite3.connect(path)
    c.executescript("CREATE TABLE app (app_id INTEGER PRIMARY KEY, identifier VARCHAR, badge INTEGER);"
                    "CREATE TABLE record (rec_id INTEGER PRIMARY KEY, app_id INTEGER, uuid BLOB, data BLOB, "
                    "request_date REAL, request_last_date REAL, delivered_date REAL, presented Bool, style INTEGER);"
                    "CREATE TABLE dbinfo (key VARCHAR, value VARCHAR);")
    add(c, rows)
    c.close()


def add(c, rows):
    for app, payload, delivered in rows:
        row = c.execute("SELECT app_id FROM app WHERE identifier = ?", (app,)).fetchone()
        app_id = row[0] if row else c.execute("INSERT INTO app (identifier) VALUES (?)", (app,)).lastrowid
        c.execute("INSERT INTO record (app_id, uuid, data, delivered_date, presented) VALUES (?,?,?,?,1)",
                  (app_id, os.urandom(16), plistlib.dumps(payload, fmt=plistlib.FMT_BINARY), delivered))
    c.commit()


def req(title="", sub="", body="", app=None):
    d = {"req": {"titl": title, "subt": sub, "body": body}, "date": 800000000.0}
    if app:
        d["app"] = app
    return d


class MacCatcherTest(unittest.TestCase):
    def test_parse_and_map(self):
        tg = "ru.keepcoder.Telegram"
        item = maccatcher.parse(7, tg, plistlib.dumps(req("Рабочий чат", "Ирина", "Созвон в 15:00"),
                                                      fmt=plistlib.FMT_BINARY), 800000000.0)
        self.assertEqual(item[:5], (7, tg, "Рабочий чат", "Ирина", "Созвон в 15:00"))
        self.assertEqual(item[5], 800000000.0 + maccatcher.EPOCH_2001)
        r = maccatcher.to_record(item)
        self.assertEqual((r["app"], r["chat"], r["sender"], r["message"]), (tg, "Рабочий чат", "Ирина", "Созвон в 15:00"))
        # браузер: сайт в подзаголовке → колонка сайта
        r = maccatcher.to_record(maccatcher.parse(8, "com.google.Chrome", plistlib.dumps(
            req("Чат двора", "web.max.ru", "Сосед: воды не будет")), None))
        self.assertEqual((r["site"], r["sender"], r["message"]), ("web.max.ru", "Сосед", "воды не будет"))
        # почта Apple: заголовок — от кого, подзаголовок — тема
        r = maccatcher.to_record(maccatcher.parse(9, "com.apple.mail", plistlib.dumps(
            req("Бухгалтерия", "Зарплата за сентябрь", "Добрый день!")), None))
        self.assertEqual((r["sender"], r["message"]), ("Бухгалтерия", "Зарплата за сентябрь\nДобрый день!"))
        # от имени другого приложения (app в plist), без текста — пропуск, битый plist — пропуск
        self.assertEqual(maccatcher.parse(1, "com.apple.helper", plistlib.dumps(req("A", body="b", app="org.x.App")), 1)[1],
                         "org.x.App")
        self.assertIsNone(maccatcher.parse(1, "x", plistlib.dumps(req()), 1))
        self.assertIsNone(maccatcher.parse(1, "x", b"not a plist", 1))

    def test_poller_first_run_new_rows_and_recreated_db(self):
        d = tempfile.mkdtemp(dir=common.TMP)
        nc, state = os.path.join(d, "db"), os.path.join(d, "state.json")
        fake_db(nc, [("ru.keepcoder.Telegram", req("Старое", body="было до запуска"), 700000000.0)])
        conn = catcher.init_db(common.new_db("mac.db"))
        got = []
        handle = catcher.make_handler(conn)
        poller = maccatcher.Poller(lambda rec: got.append(rec) or handle(rec), state_file=state)
        self.assertEqual(poller.step(nc), 0)                      # первый запуск: старое не тащим
        c = sqlite3.connect(nc)
        add(c, [("ru.keepcoder.Telegram", req("Семья", "Мама", "Позвони"), 800000000.0),
                ("com.apple.MobileSMS", req("Олег", body="Буду в 7"), 800000001.0),
                ("com.example.Empty", {"req": {}}, 800000002.0)])
        c.close()
        self.assertEqual(poller.step(nc), 2)
        self.assertEqual([(r["chat"], r["sender"], r["message"]) for r in got],
                         [("Семья", "Мама", "Позвони"), ("Олег", "Олег", "Буду в 7")])
        # перезапуск: с запомненного места, повторов нет
        self.assertEqual(maccatcher.Poller(handle, state_file=state).step(nc), 0)
        rows = conn.execute("SELECT app, chat FROM messages ORDER BY id").fetchall()
        self.assertEqual(rows, [("ru.keepcoder.Telegram", "Семья"), ("com.apple.MobileSMS", "Олег")])
        # базу пересоздали (номера снова с 1) — продолжаем с её конца, старое не дублируем
        fake_db(nc, [("ru.keepcoder.Telegram", req("Новая база", body="x"), 800000010.0)])
        self.assertEqual(maccatcher.Poller(handle, state_file=state).step(nc), 0)
        conn.close()

    def test_snapshot_and_access(self):
        d = tempfile.mkdtemp(dir=common.TMP)
        nc = os.path.join(d, "db")
        fake_db(nc, [("com.apple.iCal", req("Планёрка", body="через 10 минут"), 800000000.0)])
        self.assertEqual(maccatcher.access_status(nc), "allowed")
        self.assertEqual(maccatcher.access_status(os.path.join(d, "нет")), "missing")
        tmp = tempfile.mkdtemp(dir=common.TMP)
        copy = maccatcher.snapshot(nc, tmp)
        self.assertEqual(maccatcher.max_rec_id(copy), 1)
        self.assertNotEqual(maccatcher._signature(nc), (None, None))
        self.assertEqual(maccatcher.to_record(maccatcher.parse(*maccatcher.read_records(copy, 0)[0]))["app"],
                         "com.apple.iCal")


if __name__ == "__main__":
    unittest.main()
