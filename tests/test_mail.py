"""Почта из ящиков: поддельный IMAP-сервер на 127.0.0.1 (без шифрования — это можно
только локально), разбор писем, «старую почту не тащим», пропуск уведомлений почтовых программ."""
import os
import socketserver
import sqlite3
import threading
import unittest
from email.message import EmailMessage

import common
import collect
import mail
import rules
import serve


def letter(subject, sender, text, html=False, attach=False):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, "me@example.org", subject
    m["Date"] = "Thu, 24 Sep 2026 12:00:00 +0300"
    if html:
        m.set_content("<p>Привет, <b>это</b> письмо</p><style>p{}</style>", subtype="html")
    else:
        m.set_content(text)
    if attach:
        m.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="счёт.pdf")
    return m.as_bytes()


class FakeImap(socketserver.ThreadingTCPServer):
    """Ровно столько IMAP4rev1, сколько нужно imaplib: LOGIN, EXAMINE, UID SEARCH/FETCH."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        self.box = {1: letter("Старое", "a@example.org", "old")}
        self.uidvalidity = 7
        self.password = "app-pass"
        self.seen_flags_changed = False
        super().__init__(("127.0.0.1", 0), Handler)


class Handler(socketserver.StreamRequestHandler):
    def out(self, s):
        self.wfile.write(s.encode() + b"\r\n")

    def handle(self):
        srv = self.server
        self.out("* OK fake ready")
        while True:
            line = self.rfile.readline().decode().strip()
            if not line:
                return
            tag, cmd, *rest = line.split(" ", 2)
            cmd, arg = cmd.upper(), rest[0] if rest else ""
            if cmd == "CAPABILITY":
                self.out("* CAPABILITY IMAP4rev1")
                self.out(f"{tag} OK done")
            elif cmd == "LOGIN":
                ok = arg.split(" ", 1)[1].strip('"') == srv.password
                self.out(f"{tag} OK logged in" if ok else f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials")
            elif cmd == "EXAMINE":
                if arg.strip('"') != "INBOX":
                    self.out(f"{tag} NO no such folder")
                    continue
                self.out(f"* {len(srv.box)} EXISTS")
                self.out(f"* OK [UIDVALIDITY {srv.uidvalidity}] ok")
                self.out(f"{tag} OK [READ-ONLY] done")
            elif cmd == "UID" and arg.upper().startswith("SEARCH"):
                self.out("* SEARCH " + " ".join(map(str, sorted(srv.box))))
                self.out(f"{tag} OK done")
            elif cmd == "UID" and arg.upper().startswith("FETCH"):
                _, uid, what = arg.split(" ", 2)
                if "PEEK" not in what.upper():
                    srv.seen_flags_changed = True        # без PEEK письмо стало бы прочитанным
                raw = srv.box[int(uid)]
                self.wfile.write(f"* 1 FETCH (UID {uid} BODY[]<0> {{{len(raw)}}}\r\n".encode() + raw + b")\r\n")
                self.out(f"{tag} OK done")
            elif cmd == "LOGOUT":
                self.out("* BYE")
                self.out(f"{tag} OK bye")
                return
            else:
                self.out(f"{tag} BAD unknown")


class MailTest(unittest.TestCase):
    def setUp(self):
        self.srv = FakeImap()
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.db = common.new_db("mail.db")
        if os.path.exists(mail.CFG):
            os.remove(mail.CFG)
        mail.state.clear()
        self.conn = sqlite3.connect(self.db)
        self.acc = {"label": "Работа", "host": "127.0.0.1", "port": self.srv.server_address[1],
                    "security": "none", "user": "me", "password": "app-pass", "interval": 1}

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.conn.close()

    def test_account_validation_and_secrets(self):
        with self.assertRaises(ValueError):          # без шифрования — только к этому компьютеру
            mail.clean_account(dict(self.acc, host="imap.example.org"))
        with self.assertRaises(ValueError):
            mail.clean_account(dict(self.acc, host="imap.example.org", security="ssl", insecure=True))
        with self.assertRaises(ValueError):
            mail.clean_account(dict(self.acc, password=""))
        a = mail.save_account(self.conn, self.acc)
        if os.name != "nt":                         # на Windows прав «600» нет — там профиль пользователя
            self.assertEqual(oct(os.stat(mail.CFG).st_mode & 0o777), "0o600")
        pub = mail.public_accounts(self.conn)[0]
        self.assertNotIn("password", pub)
        self.assertTrue(pub["has_password"])
        # пустой пароль при правке — прежний остаётся
        mail.save_account(self.conn, dict(self.acc, id=a["id"], password="", label="Офис"))
        self.assertEqual(mail.load_accounts()[0]["password"], "app-pass")

    def test_test_connection(self):
        self.assertEqual(mail.test(self.acc), (True, "", 1))
        ok, err, _ = mail.test(dict(self.acc, password="wrong"))
        self.assertFalse(ok)
        self.assertIn("пароль", err)
        ok, err, _ = mail.test(dict(self.acc, folder="Нет такой"))
        self.assertFalse(ok)

    def test_first_check_skips_old_mail_then_new_arrives(self):
        a = mail.save_account(self.conn, self.acc)
        self.assertEqual(mail.check(self.db, a), 0)              # запомнил последнее, старое не взял
        self.srv.box[2] = letter("Счёт за сентябрь", "Бухгалтерия <buh@example.org>", "Добрый день, счёт во вложении",
                                 attach=True)
        self.srv.box[3] = letter("=?utf-8?b?0J/RgNC40LLQtdGC?=", "x@example.org", "", html=True)
        self.assertEqual(mail.check(self.db, a), 2)
        self.assertEqual(mail.check(self.db, a), 0)              # второй раз те же не приходят
        self.assertFalse(self.srv.seen_flags_changed)            # только PEEK — на сервере не прочитано
        rows = self.conn.execute("SELECT app, chat, sender, message, has_media FROM messages ORDER BY id").fetchall()
        self.assertEqual(rows[0][:3], ("mail-imap", "Работа", "Бухгалтерия"))
        self.assertTrue(rows[0][3].startswith("Счёт за сентябрь\nДобрый день"))
        self.assertEqual(rows[0][4], 1)
        self.assertTrue(rows[1][3].startswith("Привет\nПривет, это письмо"))
        self.assertEqual(rules.source_of("mail-imap", "")["key"], "mail")
        # ящик пересоздали (другой UIDVALIDITY) — снова только запоминаем
        self.srv.uidvalidity = 8
        self.srv.box[4] = letter("После пересоздания", "x@example.org", "…")
        self.assertEqual(mail.check(self.db, a), 0)

    def test_folder_change_and_channel_switch_forget_position(self):
        a = mail.save_account(self.conn, self.acc)
        mail.check(self.db, a)
        self.conn.commit()
        n = lambda: self.conn.execute("SELECT COUNT(*) FROM mail_state").fetchone()[0]
        self.assertEqual(n(), 1)
        mail.save_account(self.conn, dict(self.acc, id=a["id"], label="Другое имя"))
        self.assertEqual(n(), 1)                                  # имя — не повод
        mail.save_account(self.conn, dict(self.acc, id=a["id"], folder="Archive"))
        self.assertEqual(n(), 0)                                  # другая папка — начать заново

    def test_diag_lists_mailboxes(self):
        import diag
        rules.set_prefs(self.conn, {"mail_channel": "imap"})
        self.conn.commit()
        self.assertEqual([c["state"] for c in diag.checks(self.db)["checks"] if c["id"] == "mail"], ["warn"])
        a = mail.save_account(self.conn, self.acc)
        mail.check(self.db, a)
        self.conn.commit()
        c = next(c for c in diag.checks(self.db)["checks"] if c["id"] == "mail-" + a["id"])
        self.assertEqual(c["state"], "ok")

    def test_channel_skip_and_mail_column(self):
        skip = collect.make_skip(self.db)
        tb = {"app": "thunderbird", "site": ""}
        collect._mail_mode["t"] = 0
        self.assertFalse(skip(tb))                                # канал — уведомления
        rules.set_prefs(self.conn, {"mail_channel": "imap"})
        self.conn.commit()
        collect._mail_mode["t"] = 0
        self.assertTrue(skip(tb))                                 # ящики — уведомления почты не пишем
        self.assertFalse(skip({"app": "telegram", "site": ""}))
        self.assertFalse(skip({"app": "yandex-browser", "site": "web.max.ru"}))
        self.assertTrue(skip({"app": "yandex-browser", "site": "mail.yandex.ru"}))
        self.assertNotIn("mail", [s["key"] for s in serve.sources(self.db)])
        mail.save_account(self.conn, self.acc)
        self.assertIn("mail", [s["key"] for s in serve.sources(self.db)])   # колонка «Почта» зарезервирована


if __name__ == "__main__":
    unittest.main()
