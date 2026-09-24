import sqlite3
import unittest
from datetime import datetime
from unittest import mock

import common
import rules


def R(**kw):
    base = dict(id=0, src="express", chat="", sender="", text="", text_mode="contains",
                action="hide", param="", profile="")
    base.update(kw)
    return base


class PriorityTest(unittest.TestCase):
    def test_narrowest_wins(self):
        rs = rules.Rules([R(id=1, chat="Флуд"), R(id=2, sender="Начальник", action="show"),
                          R(id=3, src="*", text="срочно", action="show"), R(id=4, src="express")])
        self.assertFalse(rs.visible("express", "Флуд", "Олег", "обед"))
        self.assertTrue(rs.visible("express", "Флуд", "Начальник", "обед"))      # отправитель > чат
        self.assertTrue(rs.visible("express", "Флуд", "Олег", "СРОЧНО глянь"))   # текст > всё
        self.assertFalse(rs.visible("express", "Другой", "Кто-то", "x"))         # режим источника
        self.assertTrue(rs.visible("telegram", "Флуд", "Олег", "x"))            # чужой источник

    def test_tie_prefers_show(self):
        rs = rules.Rules([R(id=1, src="*", text="обед"), R(id=2, src="*", text="срочно", action="show")])
        self.assertTrue(rs.visible("express", "c", "s", "срочно про обед"))

    def test_regex_and_highlight(self):
        rs = rules.Rules([R(id=1, src="*", text=r"отч[её]т", text_mode="regex", action="highlight", param="red"),
                          R(id=2, src="*", text="([bad", text_mode="regex")])
        self.assertEqual(rs.highlight("x", "c", "s", "Отчёт к пятнице"), "red")
        self.assertTrue(rs.visible("x", "c", "s", "([bad"))          # битое выражение не срабатывает

    def test_clean_rule(self):
        with self.assertRaises(ValueError):
            rules.clean_rule({"src": "*", "action": "hide"})           # без условия для всех — нельзя
        with self.assertRaises(ValueError):
            rules.clean_rule({"src": "*", "text": "([", "text_mode": "regex", "action": "hide"})
        with self.assertRaises(ValueError):
            rules.clean_rule({"src": "*", "text": "x", "action": "highlight", "param": "pink"})
        self.assertEqual(rules.clean_rule({"src": "express", "action": "hide", "profile": "home"})["profile"], "home")


class ProfileTest(unittest.TestCase):
    PREFS = {"profile": "auto", "profiles": [
        {"id": "night", "name": "Ночь", "schedule": [{"days": [0, 1, 2, 3, 4], "from": "22:00", "to": "07:00"}]},
        {"id": "work", "name": "Работа", "schedule": [{"days": [0, 1, 2, 3, 4], "from": "09:00", "to": "18:00"}]}]}

    def test_schedule(self):
        at = lambda s: rules.active_profile(self.PREFS, datetime.strptime(s, "%Y-%m-%d %H:%M"))  # noqa: E731
        self.assertEqual(at("2026-09-21 10:00"), "work")      # понедельник
        self.assertEqual(at("2026-09-21 23:00"), "night")
        self.assertEqual(at("2026-09-22 06:30"), "night")     # вторник утро — продолжение ночи с понедельника
        self.assertEqual(at("2026-09-27 10:00"), "")          # воскресенье
        self.assertEqual(rules.active_profile(dict(self.PREFS, profile="work")), "work")
        self.assertEqual(rules.active_profile(dict(self.PREFS, profile="gone")), "")

    def test_rules_by_profile(self):
        rows = [R(id=1, chat="Флуд", profile="work"), R(id=2, chat="Семья")]
        self.assertTrue(rules.Rules(rows, "").visible("express", "Флуд", "a", "b"))
        self.assertFalse(rules.Rules(rows, "work").visible("express", "Флуд", "a", "b"))
        self.assertFalse(rules.Rules(rows, "").visible("express", "Семья", "a", "b"))


class MentionTest(unittest.TestCase):
    def test_word_start(self):
        rx = rules.mention_re(["Иван", " "])
        self.assertTrue(rx.search("Ивану привет"))
        self.assertTrue(rx.search("эй, иван!"))
        self.assertFalse(rx.search("Диван"))
        self.assertIsNone(rules.mention_re([]))


class DbTest(unittest.TestCase):
    def setUp(self):
        self.db = common.new_db("rules.db")
        self.conn = sqlite3.connect(self.db)

    def tearDown(self):
        self.conn.close()

    def test_insert_actions_and_why(self):
        rules.save_rule(self.conn, rules.clean_rule({"src": "*", "text": "отчёт", "action": "pin"}))
        rules.save_rule(self.conn, rules.clean_rule({"src": "express", "sender": "Анна", "action": "read"}))
        rules.save_rule(self.conn, rules.clean_rule({"src": "express", "sender": "Анна", "action": "sound"}))
        with mock.patch("actions.play_sound") as snd:
            rec = common.put(self.conn, "eXpress", "Анна", "Нужен отчёт")
            done = rules.apply_on_insert(self.conn, rec)
        self.assertEqual(done, ["pin", "sound"])                          # pin главнее read
        snd.assert_called_once()
        self.assertEqual(self.conn.execute("SELECT pinned, is_read FROM messages WHERE id=?", (rec["id"],)).fetchone(), (1, 0))
        w = rules.why(self.conn, rec["id"])
        self.assertEqual(sorted(h["action"] for h in w["insert_hits"]), ["pin", "sound"])

    def test_vis_pair_is_exclusive(self):
        rules.save_rule(self.conn, rules.clean_rule({"src": "express", "chat": "Флуд", "action": "hide"}))
        rules.save_rule(self.conn, rules.clean_rule({"src": "express", "chat": "Флуд", "action": "show"}))
        self.assertEqual([r["action"] for r in rules.all_rules(self.conn)], ["show"])

    def test_export_import_roundtrip(self):
        rules.set_prefs(self.conn, {"profiles": [{"id": "home", "name": "Дом", "schedule": []}], "mentions": ["Аня"]})
        rules.save_rule(self.conn, rules.clean_rule({"src": "express", "chat": "Флуд", "action": "hide", "profile": "home"}))
        data = rules.export_config(self.conn)
        self.assertNotIn("backup_last", data["prefs"])
        self.conn.execute("DELETE FROM rules")
        rules.set_prefs(self.conn, {"profiles": [], "mentions": []})
        res = rules.import_config(self.conn, data, replace=True)
        self.assertEqual((res["rules"], res["errors"]), (1, []))
        self.assertEqual(rules.get_prefs(self.conn)["mentions"], ["Аня"])
        self.assertEqual(rules.all_rules(self.conn)[0]["profile"], "home")

    def test_deleting_profile_drops_its_rules(self):
        rules.set_prefs(self.conn, {"profiles": [{"id": "home", "name": "Дом", "schedule": []}]})
        rules.save_rule(self.conn, rules.clean_rule({"src": "express", "chat": "X", "action": "hide", "profile": "home"}))
        rules.set_prefs(self.conn, {"profiles": []})
        self.assertEqual(rules.all_rules(self.conn), [])


if __name__ == "__main__":
    unittest.main()
