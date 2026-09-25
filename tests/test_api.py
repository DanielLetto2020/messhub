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
import catcher
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

    def test_pages_served(self):
        """Страницы и переводы отдаются (после переноса файлов было «not found»)."""
        for path, marker in (("/", b"id=\"board\""), ("/widget", b"id=\"board\""),
                             ("/settings", b"id=\"page\""), ("/message?id=1", b"id=\"foot\""),
                             ("/i18n.js", b"const EN")):
            with urllib.request.urlopen(self.base + path, timeout=10) as r:
                body = r.read()
                self.assertEqual(r.status, 200, path)
                self.assertIn(marker, body, path)
        code, v, _ = self.req("/api/version")
        self.assertEqual((v["author"], v["email"]), ("Кузьминский Максим", "i@m-letto.ru"))

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

    def test_restore_old_message_stays(self):
        """«Вернуть в виджет» у старого сообщения: авто-прочтение не забирает его снова (раньше — через час)."""
        conn = sqlite3.connect(self.db)
        mid = common.put(conn, "eXpress", "Архив", "старое")["id"]
        conn.execute("UPDATE messages SET is_read = 1, received_at = ? WHERE id = ?", (catcher.msk_time(72), mid))
        conn.commit()
        conn.close()
        self.req("/api/restore", {"ids": [mid]})
        orig = catcher.msk_time
        with mock.patch("catcher.msk_time", side_effect=lambda h=0: orig(h - 2)):
            serve.auto_read(self.db)                      # «через два часа»
        self.assertIn(mid, self.req("/api/visible")[1]["ids"])

    def test_openrouter_only_with_consent(self):
        """Облако не включается ни общими настройками, ни загрузкой файла настроек."""
        self.req("/api/prefs", {"ai": {"openrouter": True, "openrouter_consent": "2026-01-01 00:00:00"}})
        self.req("/api/config/import", {"data": {"prefs": {"ai": {"openrouter": True}}, "rules": []}})
        ai = self.req("/api/prefs")[1]["ai"]
        self.assertEqual((ai["openrouter"], ai["openrouter_consent"]), (False, ""))
        self.assertEqual(self.req("/api/prefs", {"ai": [["openrouter", True]]})[0], 400)

    def test_mentions_as_string_and_bad_date(self):
        self.assertEqual(self.req("/api/prefs", {"mentions": "Анна, Олег"})[1]["mentions"], ["Анна", "Олег"])
        self.req("/api/prefs", {"mentions": []})
        self.assertEqual(self.req("/api/search?to=31-12-2026")[0], 400)      # не дата — ответ, а не обрыв

    def test_ingest_key_non_ascii(self):
        ingest.new_token()
        self.assertFalse(ingest.authorized("Bearer \u0430\u0431\u0432"))   # не TypeError

    def test_purge_takes_reminders(self):
        conn = sqlite3.connect(self.db)
        try:
            mid = common.put(conn, "eXpress", "Старое", "в пятницу в 11")["id"]
            conn.execute("UPDATE messages SET received_at = ? WHERE id = ?", (catcher.msk_time(24 * 40), mid))
            conn.execute("INSERT INTO reminders (message_id, at) VALUES (?, '2099-01-01 10:00')", (mid,))
            self.assertGreaterEqual(serve.purge(conn, 30), 1)
            conn.commit()
            self.assertIsNone(conn.execute("SELECT 1 FROM reminders WHERE message_id = ?", (mid,)).fetchone())
        finally:
            conn.rollback()
            conn.close()

    def test_english(self):
        code, err, _ = self.req("/api/rules", {"src": "*", "action": "hide"}, headers={"Accept-Language": "en-US"})
        self.assertIn("condition", err["error"])


if __name__ == "__main__":
    unittest.main()
