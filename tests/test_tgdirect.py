"""Прямой канал Telegram (MTProto): настройки, фильтры, полный текст без обрезки, пропуск дублей, API."""
import inspect
import json
import os
import sqlite3
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import common
import collect
import rules
import serve
import session
import tgdirect


class TgDirectTest(unittest.TestCase):
    def setUp(self):
        self.db = common.new_db("tgdirect.db")
        self.conn = sqlite3.connect(self.db)
        self.cfg_path = os.path.join(common.TMP, f"tg-{id(self)}.json")
        self._orig_cfg = os.environ.get("MESSHUB_TG_CFG")
        os.environ["MESSHUB_TG_CFG"] = self.cfg_path
        tgdirect._sess_cache["sig"] = None

    def tearDown(self):
        self.conn.close()
        if self._orig_cfg is None:
            os.environ.pop("MESSHUB_TG_CFG", None)
        else:
            os.environ["MESSHUB_TG_CFG"] = self._orig_cfg
        if os.path.exists(self.cfg_path):
            os.remove(self.cfg_path)
        tgdirect._sess_cache["sig"] = None

    def test_secrets_masked_and_mode_600(self):
        tgdirect._save_cfg({
            "api_id": 1234567,
            "api_hash": "0123456789abcdef0123456789abcdef",
            "session": "1BQANOTE_FAKE_SESSION_STRING",
            "account": {"id": 42, "name": "Иван Иванов", "username": "ivan", "phone": "+79991234567"},
        })
        if os.name != "nt":
            self.assertEqual(os.stat(self.cfg_path).st_mode & 0o777, 0o600)
        st = tgdirect.public_status(self.conn)
        dump = json.dumps(st, ensure_ascii=False)
        self.assertTrue(st["authorized"])
        self.assertTrue(st["has_api_hash"])
        self.assertEqual(st["api_hash_hint"], "…cdef")
        self.assertNotIn("0123456789abcdef", dump)
        self.assertNotIn("FAKE_SESSION_STRING", dump)
        self.assertNotIn("+79991234567", dump)
        self.assertEqual(st["account"]["phone"], "+799***4567")

    def test_skip_notifications_only_with_session(self):
        skip = collect.make_skip(self.db)
        tg_rec = {"app": "telegram-desktop", "site": ""}
        web_tg = {"app": "yandex-browser", "site": "web.telegram.org"}
        exp_rec = {"app": "eXpress", "site": ""}
        mt_rec = {"app": tgdirect.APP, "site": ""}

        # По умолчанию (notify): системные уведомления Telegram идут на доску
        self.assertFalse(skip(tg_rec))
        self.assertFalse(skip(web_tg))
        self.assertFalse(skip(exp_rec))

        # Переключили на mtproto, но сессии ещё нет: системные уведомления НЕ глушим
        rules.set_prefs(self.conn, {"telegram_channel": "mtproto"})
        self.conn.commit()
        collect._mode["t"] = 0
        self.assertFalse(skip(tg_rec))

        # Авторизованная сессия появилась: системные уведомления Telegram пропускаем (защита от дублей)
        tgdirect._save_cfg({"api_id": 1234567, "api_hash": "0123456789abcdef0123456789abcdef", "session": "abc"})
        self.assertTrue(skip(tg_rec))
        self.assertTrue(skip(web_tg))
        self.assertFalse(skip(mt_rec))
        self.assertFalse(skip(exp_rec))

    def test_process_event_full_text_and_filters(self):
        long_text = "Длинный абзац.\n" + ("Очень важное подробное сообщение. " * 105)
        self.assertGreater(len(long_text), 3000)

        # Личный чат — 3500 символов сохраняется целиком без обрезки
        mid = tgdirect.process_event(self.conn, {}, {
            "chat_id": 1001, "msg_id": 10, "is_private": True, "is_group": False, "is_channel": False,
            "is_bot": False, "chat_title": "Мария Соколова", "sender_name": "Мария Соколова",
            "text": long_text, "media_label": "", "has_media": False, "ts": 1760000000.0,
        })
        self.assertIsNotNone(mid)
        row = self.conn.execute("SELECT app, chat, sender, message, raw_body FROM messages WHERE id = ?",
                                (mid,)).fetchone()
        self.assertEqual(row[0], "telegram-mtproto")
        self.assertEqual((row[1], row[2]), ("Мария Соколова", "Мария Соколова"))
        self.assertEqual(row[3], long_text.strip())
        self.assertGreater(len(row[3]), 3000)
        self.assertEqual(rules.source_of("telegram-mtproto")["key"], "telegram")
        self.assertEqual(rules.sub_of("telegram-mtproto"), ("tg:mtproto", "MTProto"))

        # Группа с медиа и подписью + правило при записи
        rules.save_rule(self.conn, rules.clean_rule({"src": "telegram", "text": "дедлайн", "action": "pin"}))
        self.conn.commit()
        gid = tgdirect.process_event(self.conn, {}, {
            "chat_id": -2002, "msg_id": 11, "is_private": False, "is_group": True, "is_channel": False,
            "is_bot": False, "chat_title": "Команда", "sender_name": "Алексей",
            "text": "Напоминаю про дедлайн завтра", "media_label": "📷 Фото", "has_media": True, "ts": 1760000010.0,
        })
        grow = self.conn.execute("SELECT chat, sender, message, has_media, pinned FROM messages WHERE id = ?",
                                 (gid,)).fetchone()
        self.assertEqual((grow[0], grow[1], grow[3], grow[4]), ("Команда", "Алексей", 1, 1))
        self.assertEqual(grow[2], "📷 Фото\nНапоминаю про дедлайн завтра")

        # Фильтры: каналы, боты и беззвучные по умолчанию отключены
        ch_info = {"chat_id": -3003, "msg_id": 12, "is_private": False, "is_group": False, "is_channel": True,
                   "is_bot": False, "chat_title": "Новости", "sender_name": "Новости", "text": "Новость", "ts": 1.0}
        self.assertIsNone(tgdirect.process_event(self.conn, {}, ch_info))
        self.assertIsNotNone(tgdirect.process_event(self.conn, {"settings": {"channels": True}}, ch_info))

        bot_info = {"chat_id": 4004, "msg_id": 13, "is_private": True, "is_group": False, "is_channel": False,
                    "is_bot": True, "chat_title": "CI Bot", "sender_name": "CI Bot", "text": "ок", "ts": 1.0}
        self.assertIsNone(tgdirect.process_event(self.conn, {}, bot_info))
        self.assertIsNotNone(tgdirect.process_event(self.conn, {"settings": {"bots": True}}, bot_info))

        mute_info = {"chat_id": 5005, "msg_id": 14, "is_private": True, "is_group": False, "is_channel": False,
                     "is_bot": False, "chat_title": "Флуд", "sender_name": "Олег", "text": "привет", "ts": 1.0}
        self.assertIsNone(tgdirect.process_event(self.conn, {}, mute_info, muted_peers={5005}))
        self.assertIsNotNone(tgdirect.process_event(self.conn, {"settings": {"include_muted": True}},
                                                    mute_info, muted_peers={5005}))

    def test_strictly_read_only_no_read_receipts_in_code(self):
        """В tgdirect.py никогда не вызываются методы отправки отметки прочтения или сообщений."""
        src = inspect.getsource(tgdirect)
        for forbidden in ("send_read_acknowledge", "ReadHistoryRequest",
                          "ReadMessageContentsRequest", "send_message"):
            self.assertNotIn(forbidden, src)

    def test_http_api(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(self.db))
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        try:
            with urllib.request.urlopen(base + "/api/telegram", timeout=10) as r:
                st = json.load(r)
            self.assertEqual(st["channel"], "notify")
            self.assertFalse(st["authorized"])

            def post(path, body, with_tok=True):
                h = {"Content-Type": "application/json"}
                if with_tok:
                    h["Cookie"] = f"{session.COOKIE}={session.token()}"
                req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=h)
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        return resp.status, json.load(resp)
                except urllib.error.HTTPError as e:
                    return e.code, json.load(e)

            self.assertEqual(post("/api/telegram/channel", {"channel": "mtproto"}, with_tok=False)[0], 401)
            code, res = post("/api/telegram/channel", {"channel": "mtproto"})
            self.assertEqual((code, res["channel"]), (200, "mtproto"))
            self.assertEqual(post("/api/telegram/channel", {"channel": "bad"})[0], 400)

            code, st = post("/api/telegram/settings", {"channels": True, "bots": True})
            self.assertEqual(code, 200)
            self.assertTrue(st["settings"]["channels"] and st["settings"]["bots"])

            tgdirect._save_cfg({"api_id": 123, "api_hash": "0123456789abcdef0123456789abcdef",
                                "session": "fake", "account": {"name": "X", "phone": "+79991112233"}})
            code, st = post("/api/telegram/logout", {"remote": False})
            self.assertEqual(code, 200)
            self.assertEqual(st["channel"], "notify")
            self.assertFalse(st["authorized"])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
