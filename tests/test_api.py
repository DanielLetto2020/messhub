"""HTTP API целиком: настоящий сервер на свободном порту, временная база."""
import json
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import common
import ingest
import serve


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = common.new_db("api.db")
        conn = sqlite3.connect(cls.db)
        common.put(conn, "eXpress", "Команда", "Иван Петров: Анна, созвон в 15:00")
        common.put(conn, "eXpress", "Флуд", "Олег: кто на обед?")
        common.put(conn, "yandex-browser", "Двор", "web.max.ru\n\nСосед: воды не будет")
        conn.close()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(cls.db))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, body=None, ctype="application/json", headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = dict(headers or {})
        if data is not None:
            h["Content-Type"] = ctype
        r = urllib.request.Request(self.base + path, data=data, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, json.load(resp), resp.headers
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw), e.headers
            except ValueError:
                return e.code, raw.decode(), e.headers

    def test_version_header_and_json_only(self):
        code, v, h = self.req("/api/version")
        self.assertEqual(h["X-App-Version"], v["version"])
        self.assertEqual(self.req("/api/read", {"ids": [1]}, ctype="text/plain")[0], 415)

    def test_rules_filter_widget_and_search(self):
        code, err, _ = self.req("/api/rules", {"src": "*", "action": "hide"})
        self.assertEqual(code, 400)
        self.assertIn("error", err)
        self.req("/api/rules", {"src": "*", "text": "обед", "action": "hide"})
        _, rows, h = self.req("/api/messages?unread=1&rules=1")
        self.assertNotIn("Флуд", [m["chat"] for m in rows])
        self.assertTrue(h["X-Rules-Ver"])
        srcs = {m["src"] for m in rows}
        self.assertIn("max", srcs)                                           # сайт → своя колонка
        _, res, _ = self.req("/api/search?q=%D0%90%D0%9D%D0%9D%D0%90")   # «АННА»
        self.assertEqual(res["total"], 1)
        _, res, _ = self.req("/api/search?q=%D0%BE%D0%B1%D0%B5%D0%B4")               # «обед» — скрытое тоже ищется
        self.assertFalse(res["rows"][0]["visible"])

    def test_read_undo_pin_snooze(self):
        _, rows, _ = self.req("/api/messages?unread=1&rules=1")
        mid = rows[0]["id"]
        self.req("/api/read", {"ids": [mid]})
        self.assertNotIn(mid, self.req("/api/visible")[1]["ids"])
        self.req("/api/read", {"ids": [mid], "unread": True})
        self.assertIn(mid, self.req("/api/visible")[1]["ids"])
        self.req("/api/snooze", {"ids": [mid], "preset": "1h"})
        self.assertNotIn(mid, self.req("/api/visible")[1]["ids"])
        self.req("/api/restore", {"ids": [mid]})
        self.assertIn(mid, self.req("/api/visible")[1]["ids"])
        self.assertEqual(self.req("/api/pin", {"ids": [mid], "pinned": True})[1]["updated"], 1)
        self.assertEqual(self.req("/api/why?id=%d" % mid)[1]["id"], mid)

    def test_ingest(self):
        self.assertEqual(self.req("/api/ingest", {"source": "CI", "text": "x"})[0], 401)
        token = ingest.new_token()
        code, r, _ = self.req("/api/ingest", {"source": "CI", "chat": "main", "text": "Сборка прошла"},
                              headers={"Authorization": "Bearer " + token})
        self.assertEqual(code, 200)
        _, rows, _ = self.req("/api/messages?ids=%d" % r["id"])
        self.assertEqual((rows[0]["app"], rows[0]["chat"]), ("CI", "main"))
        self.assertEqual(self.req("/api/ingest", {"source": "CI"}, headers={"Authorization": "Bearer " + token})[0], 400)

    def test_backups_and_config(self):
        name = self.req("/api/backups/make", {})[1]["name"]
        self.assertIn(name, [b["name"] for b in self.req("/api/backups")[1]])
        self.assertIn("before", self.req("/api/backups/restore", {"name": name})[1])
        self.assertEqual(self.req("/api/backups/restore", {"name": "../x.db"})[0], 400)
        path = self.req("/api/config/export", {})[1]["path"]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(self.req("/api/config/import", {"data": data, "replace": False})[1]["errors"], [])

    def test_forward_is_not_configured(self):
        with mock.patch("actions.send", side_effect=AssertionError("в Telegram из тестов не ходим")):
            _, r, _ = self.req("/api/report/preview")
        self.assertIn("📊", r["text"])
        self.assertFalse(self.req("/api/forward")[1]["configured"])

    def test_english(self):
        code, err, _ = self.req("/api/rules", {"src": "*", "action": "hide"}, headers={"Accept-Language": "en-US"})
        self.assertIn("condition", err["error"])


if __name__ == "__main__":
    unittest.main()
