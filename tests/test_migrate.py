import os
import sqlite3
import unittest

import common
import catcher

V1 = """CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, chat TEXT, sender TEXT,
  is_bot INTEGER DEFAULT 0, message TEXT, notification_id INTEGER, urgency INTEGER, has_media INTEGER DEFAULT 0,
  event_ts REAL, event_iso TEXT, received_at TEXT, raw_summary TEXT, raw_body TEXT, processed INTEGER DEFAULT 0);
CREATE TABLE rules (id INTEGER PRIMARY KEY AUTOINCREMENT, src TEXT NOT NULL, chat TEXT NOT NULL DEFAULT '',
  sender TEXT NOT NULL DEFAULT '', action TEXT NOT NULL, created_at TEXT, UNIQUE (src, chat, sender));"""


class MigrateTest(unittest.TestCase):
    def test_from_first_versions(self):
        path = os.path.join(common.TMP, "old.db")
        if os.path.exists(path):
            os.remove(path)
        c = sqlite3.connect(path)
        c.executescript(V1)
        c.execute("INSERT INTO messages (app, chat, sender, message, raw_summary, raw_body) VALUES "
                  "('yandex-browser', 'Двор', 'Двор', 'web.max.ru\n\nСосед: вода', 'Двор', 'web.max.ru\n\nСосед: вода')")
        c.execute("INSERT INTO rules (src, chat, sender, action) VALUES ('express', 'Флуд', '', 'hide')")
        c.commit()
        c.close()
        conn = catcher.init_db(path)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
        self.assertTrue({"is_read", "pinned", "snooze_until", "site", "avatar"} <= cols)
        rcols = [r[1] for r in conn.execute("PRAGMA table_info(rules)")]
        self.assertIn("profile", rcols)
        self.assertEqual(conn.execute("SELECT src, chat, action, profile FROM rules").fetchall(),
                         [("express", "Флуд", "hide", "")])
        self.assertEqual(conn.execute("SELECT site, sender, message FROM messages").fetchone(),
                         ("web.max.ru", "Сосед", "вода"))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse({"rules_v1", "rules_old"} & tables)
        self.assertTrue({"prefs", "rule_hits", "embeddings"} <= tables)
        conn.close()
        catcher.init_db(path).close()          # повторный запуск ничего не ломает


if __name__ == "__main__":
    unittest.main()


class RulesActionMigrateTest(unittest.TestCase):
    def test_new_action_allowed_rules_kept(self):
        """База до 1.0.22: в CHECK таблицы правил нет «move» — таблица пересоздаётся, правила — с теми же id."""
        path = os.path.join(common.TMP, "rules-1021.db")
        if os.path.exists(path):
            os.remove(path)
        c = catcher.init_db(path)
        ddl = c.execute("SELECT sql FROM sqlite_master WHERE name = 'rules'").fetchone()[0]
        c.execute("DROP TABLE rules")
        c.execute(ddl.replace("'highlight', 'move', ", "'highlight', "))          # как было в 1.0.21
        c.execute("INSERT INTO rules (id, src, chat, action, param) VALUES (7, 'express', 'Флуд', 'highlight', 'red')")
        c.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            c.execute("INSERT INTO rules (src, chat, action, param) VALUES ('telegram', 'Мама', 'move', 'Личное')")
        c.close()
        c = catcher.init_db(path)
        self.assertEqual(c.execute("SELECT id, action, param FROM rules").fetchall(), [(7, "highlight", "red")])
        c.execute("INSERT INTO rules (src, chat, action, param) VALUES ('telegram', 'Мама', 'move', 'Личное')")
        self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name = 'rules_old'").fetchone())
        c.close()
