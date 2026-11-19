"""Диагностика и настройка уведомлений приложений и браузеров (app/appsetup.py)."""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

import common
import appsetup


class AppSetupTest(unittest.TestCase):
    def test_parse_chromium_prefs_hides_private_sites(self):
        data = {
            "profile": {
                "name": "Работа",
                "default_content_setting_values": {"notifications": 2},
                "content_settings": {
                    "exceptions": {
                        "notifications": {
                            "https://web.max.ru:443,*": {"setting": 1},
                            "https://web.telegram.org:443,*": {"setting": 2},
                            "https://secret-bank.example.org:443,*": {"setting": 1},
                        }
                    }
                },
            }
        }
        p = appsetup.parse_chromium_prefs(data)
        self.assertEqual(p["default"], "blocked")
        self.assertEqual(p["allowed_total"], 2)
        self.assertEqual(p["blocked_total"], 1)
        domains = {s["domain"]: s["status"] for s in p["sites"]}
        self.assertEqual(domains, {"web.telegram.org": "blocked", "web.max.ru": "allowed"})
        self.assertNotIn("secret-bank.example.org", json.dumps(p))

    def test_parse_firefox_prefs_and_sqlite_permissions(self):
        self.assertEqual(appsetup.parse_firefox_prefs(""), (True, "ask"))
        self.assertEqual(
            appsetup.parse_firefox_prefs('user_pref("dom.webnotifications.enabled", false);'),
            (False, "ask"),
        )
        self.assertEqual(
            appsetup.parse_firefox_prefs('user_pref("permissions.default.desktop-notification", 2);'),
            (True, "blocked"),
        )

        root = tempfile.mkdtemp(dir=common.TMP)
        pdir = os.path.join(root, "abc123.default-release")
        os.makedirs(pdir)
        with open(os.path.join(pdir, "prefs.js"), "w", encoding="utf-8") as f:
            f.write('user_pref("dom.webnotifications.enabled", true);\n')
        pdb = os.path.join(pdir, "permissions.sqlite")
        conn = sqlite3.connect(pdb)
        try:
            conn.execute("CREATE TABLE moz_perms (origin TEXT, type TEXT, permission INTEGER)")
            conn.execute("INSERT INTO moz_perms VALUES ('https://web.telegram.org', 'desktop-notification', 2)")
            conn.execute("INSERT INTO moz_perms VALUES ('https://mail.yandex.ru', 'desktop-notification', 1)")
            conn.execute("INSERT INTO moz_perms VALUES ('https://private.internal', 'desktop-notification', 1)")
            conn.commit()
        finally:
            conn.close()

        profs = appsetup._read_firefox(root)
        self.assertEqual(len(profs), 1)
        self.assertEqual(profs[0]["name"], "default-release")
        self.assertEqual(profs[0]["default"], "ask")
        self.assertEqual(profs[0]["allowed_total"], 2)
        self.assertEqual(profs[0]["blocked_total"], 1)
        sites = {s["domain"]: s["status"] for s in profs[0]["sites"]}
        self.assertEqual(sites, {"web.telegram.org": "blocked", "mail.yandex.ru": "allowed"})
        self.assertNotIn("private.internal", json.dumps(profs))

    def test_gnome_parsers_and_slug_validation(self):
        self.assertEqual(
            appsetup.parse_gnome_children("['google-chrome', 'bad/slug', 'telegram-desktop_telegram-desktop']"),
            ["google-chrome", "telegram-desktop_telegram-desktop"],
        )
        sample = (
            "org.gnome.desktop.notifications.application application-id 'google-chrome.desktop'\n"
            "org.gnome.desktop.notifications.application enable false\n"
            "org.gnome.desktop.notifications.application show-banners true\n"
        )
        self.assertEqual(
            appsetup.parse_gnome_app_lines(sample),
            {"app_id": "google-chrome.desktop", "enable": False, "banners": True},
        )
        with mock.patch.object(appsetup, "WINDOWS", False):
            for bad in ("", "../evil", "a b", "foo;bar"):
                with self.assertRaises(ValueError):
                    appsetup.set_gnome_app(bad, True)

    def test_demo_inspect(self):
        db = common.new_db("setup-demo.db")
        with mock.patch.dict(os.environ, {"MESSHUB_THEMED_DEMO": "1"}):
            d = appsetup.inspect(db)
        self.assertIn("system", d)
        self.assertTrue(len(d["browsers"]) >= 1)
        self.assertTrue(len(d["apps"]) >= 1)


if __name__ == "__main__":
    unittest.main()
