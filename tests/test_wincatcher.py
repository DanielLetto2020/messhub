"""Сбор на Windows: логика отбора новых уведомлений и разбор — без самой Windows (поддельные объекты WinRT)."""
import os
import sqlite3
import types
import unittest

import common
import catcher
import wincatcher


def note(nid, created, app, texts, aumid="App.Id"):
    """Поддельный UserNotification в форме пакета winrt."""
    binding = types.SimpleNamespace(get_text_elements=lambda: [types.SimpleNamespace(text=t) for t in texts])
    visual = types.SimpleNamespace(get_binding=lambda kind: binding)
    info = types.SimpleNamespace(display_info=types.SimpleNamespace(display_name=app), app_user_model_id=aumid)
    return types.SimpleNamespace(id=nid, creation_time=types.SimpleNamespace(timestamp=lambda: created),
                                 app_info=info, notification=types.SimpleNamespace(visual=visual))


W = (None, None, None, types.SimpleNamespace(toast_generic="ToastGeneric"))


class WinCatcherTest(unittest.TestCase):
    def setUp(self):
        self.db = common.new_db("win.db")
        self.conn = sqlite3.connect(self.db)
        self.state = os.path.join(common.TMP, "win-listener.json")
        self.apps = os.path.join(common.TMP, "win-apps.json")
        for f in (self.state, self.apps):
            if os.path.exists(f):
                os.remove(f)

    def tearDown(self):
        self.conn.close()

    def poller(self, now):
        return wincatcher.Poller(catcher.make_handler(self.conn), self.state, self.apps, now=now)

    def rows(self):
        return self.conn.execute("SELECT app, chat, sender, message, site FROM messages ORDER BY id").fetchall()

    def test_parse_and_only_new(self):
        p = self.poller(now=1000)
        old = note(1, 900, "Telegram Desktop", ["Семья", "Мама: Позвони"])      # было до первого запуска
        self.assertEqual(p.feed([wincatcher.item_of(old, W)]), 0)
        items = [wincatcher.item_of(n, W) for n in (
            old,
            note(2, 1001, "Telegram Desktop", ["Команда", "Иван Петров: созвон в 15:00"]),
            note(3, 1002, "eXpress", ["Марина", "Скинешь макет?"]),
            note(4, 1003, "Google Chrome", ["Чат дома", "Сосед: воды не будет", "web.max.ru"]),
            note(5, 1004, "Windows", ["Обновления установлены"]))]
        self.assertEqual(p.feed(items), 4)
        self.assertEqual(p.feed(items), 0)                     # тот же список ещё раз — ничего нового
        self.assertEqual(self.rows(), [
            ("Telegram Desktop", "Команда", "Иван Петров", "созвон в 15:00", ""),
            ("eXpress", "Марина", "Марина", "Скинешь макет?", ""),
            ("Google Chrome", "Чат дома", "Сосед", "воды не будет", "web.max.ru"),
            ("Windows", "Windows", "Windows", "Обновления установлены", "")])
        self.assertEqual(wincatcher._load(self.apps, {})["eXpress"], "App.Id")

    def test_restart_picks_up_missed(self):
        p = self.poller(now=1000)
        p.feed([wincatcher.item_of(note(2, 1001, "eXpress", ["Анна", "привет"]), W)])
        # перезапуск: в центре уведомлений старое (уже записано) и пришедшее, пока программа не работала
        p2 = self.poller(now=5000)
        n = p2.feed([wincatcher.item_of(note(2, 1001, "eXpress", ["Анна", "привет"]), W),
                     wincatcher.item_of(note(7, 1500, "eXpress", ["Анна", "ты тут?"]), W)])
        self.assertEqual(n, 1)
        self.assertEqual([r[3] for r in self.rows()], ["привет", "ты тут?"])

    def test_telegram_bots_skipped_and_empty_ignored(self):
        p = self.poller(now=0)
        p.feed([wincatcher.item_of(note(1, 1, "Telegram Desktop", ["SomeBot", "новости"]), W),
                wincatcher.item_of(note(2, 2, "eXpress", []), W)])
        self.assertEqual(self.rows(), [])

    def test_blank_and_invisible_texts(self):
        """Строки из пробелов и невидимых меток направления — не текст: пустой карточки на доске нет;
        старые шаблоны — текст из другой привязки."""
        self.assertIsNone(wincatcher.item_of(note(1, 1, "App", [" ", "\u2068\u2069", "\u200e"]), W))
        n = note(2, 2, "App", [])
        legacy = types.SimpleNamespace(get_text_elements=lambda: [types.SimpleNamespace(text="Обновление готово")])
        n.notification.visual.bindings = [types.SimpleNamespace(get_text_elements=lambda: []), legacy]
        self.assertEqual(wincatcher.item_of(n, W)[4], ["Обновление готово"])
        self.assertEqual(wincatcher.item_of(note(3, 3, "App", ["\u2068Анна\u2069", "привет"]), W)[4], ["Анна", "привет"])
        h = catcher.make_handler(self.conn)
        self.assertIsNone(h(catcher.record("App", " \u200f", "\u2066 \u2069")))
        self.assertEqual(self.rows(), [])

    def test_time_formats(self):
        self.assertEqual(wincatcher._ts(types.SimpleNamespace(universal_time=wincatcher.EPOCH_1601 + 10 ** 7)), 1.0)
        if wincatcher._winrt() is None:                                  # на Linux WinRT нет
            self.assertEqual(wincatcher.access_status(), "unavailable")


if __name__ == "__main__":
    unittest.main()
