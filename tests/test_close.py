"""Закрыть колонку: сообщения прочитаны, колонка возвращается с новым сообщением;
с закреплённым или отложенным — закрыть нельзя (409)."""
import json
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import common
import rules
import serve


class CloseColumnTest(unittest.TestCase):
    def setUp(self):
        self.db = common.new_db("close.db")
        self.conn = sqlite3.connect(self.db)
        self.tg = [common.put(self.conn, "Telegram", "Аня", "привет")["id"],
                   common.put(self.conn, "Telegram", "Боря", "как дела")["id"]]
        self.ex = common.put(self.conn, "eXpress", "Команда", "Иван: созвон")["id"]
        self.conn.commit()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(self.db))
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.conn.close()

    def req(self, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def closed(self):
        return {s["key"] for s in self.req("/api/sources?rules=1")[1] if s["closed"]}

    def test_close_and_reopen_by_new_message(self):
        code, st = self.req("/api/column?src=telegram")
        self.assertEqual((code, st["unread"], st["pinned"], st["snoozed"]), (200, 2, 0, 0))
        self.assertNotIn("ids", st)                     # список id наружу не отдаём
        code, r = self.req("/api/close-column", {"src": "telegram"})
        self.assertEqual((code, r["read"], sorted(r["ids"])), (200, 2, sorted(self.tg)))
        self.assertEqual(r["_ver"], self.req("/api/prefs")[1]["_ver"])
        self.assertEqual(self.closed(), {"telegram"})
        vis = self.req("/api/visible")[1]["ids"]
        self.assertFalse(set(self.tg) & set(vis))
        self.assertIn(self.ex, vis)
        # новое сообщение из того же источника — колонка снова открыта
        rec = common.put(self.conn, "Telegram", "Аня", "ещё")
        rules.apply_on_insert(self.conn, rec)
        self.assertEqual(self.closed(), set())

    def test_new_message_read_by_rule_keeps_column_closed(self):
        self.req("/api/close-column", {"src": "telegram"})
        rules.save_rule(self.conn, rules.clean_rule({"src": "telegram", "chat": "Аня", "action": "read"}))
        self.conn.commit()
        rules.apply_on_insert(self.conn, common.put(self.conn, "Telegram", "Аня", "ещё"))
        self.assertEqual(self.closed(), {"telegram"})

    def test_pinned_or_snoozed_block_closing(self):
        self.req("/api/pin", {"ids": [self.ex], "pinned": True})
        code, r = self.req("/api/close-column", {"src": "express"})
        self.assertEqual((code, r["pinned"]), (409, 1))
        self.assertIn("error", r)
        self.assertEqual(self.closed(), set())
        self.req("/api/pin", {"ids": [self.ex], "pinned": False})
        self.req("/api/snooze", {"ids": [self.tg[0]], "preset": "1h"})
        code, r = self.req("/api/close-column", {"src": "telegram"})
        self.assertEqual((code, r["snoozed"], r["unread"]), (409, 1, 1))
        # ничего не прочитано
        self.assertIn(self.tg[1], self.req("/api/visible")[1]["ids"])

    def test_undo_and_restore_reopen(self):
        _, r = self.req("/api/close-column", {"src": "telegram"})
        self.req("/api/reopen-column", {"src": "telegram", "ids": r["ids"]})
        self.assertEqual(self.closed(), set())
        self.assertTrue(set(self.tg) <= set(self.req("/api/visible")[1]["ids"]))
        # «Вернуть в виджет» из поиска тоже открывает колонку
        self.req("/api/close-column", {"src": "telegram"})
        self.req("/api/restore", {"ids": [self.tg[0]]})
        self.assertEqual(self.closed(), set())


if __name__ == "__main__":
    unittest.main()
