"""Время в тексте и напоминания, тихие часы, календарь, ресурсы, журналы, свои скрипты, показ экрана,
умный поиск (RAG). Без сети и рабочего стола."""
import json
import os
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
import urllib.error
from datetime import datetime, timedelta
from unittest import mock

import common
import calendar_src
import logwatch
import quiet
import rag
import reminders
import resources
import rules
import screen
import scripts
import serve
import when


def prefs(db, patch):
    conn = sqlite3.connect(db)
    rules.set_prefs(conn, dict({"language": "ru"}, **patch))
    conn.commit()
    conn.close()


def rows(db, where="1"):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM messages WHERE {where} ORDER BY id")]
    finally:
        conn.close()


class WhenTest(unittest.TestCase):
    base, now = datetime(2026, 9, 25, 12, 0), datetime(2026, 9, 25, 12, 5)   # пятница

    def f(self, text):
        return [(h["at"], h["date_only"]) for h in when.find(text, self.base, self.now)]

    def test_phrases(self):
        self.assertEqual(self.f("Созвон в 15:00"), [("2026-09-25 15:00", False)])
        self.assertEqual(self.f("завтра в 10 встречаемся"), [("2026-09-26 10:00", False)])
        self.assertEqual(self.f("в пятницу в 11:30 демо"), [("2026-10-02 11:30", False)])
        self.assertEqual(self.f("Отчёт нужен к пятнице"), [("2026-10-02 09:00", True)])
        self.assertEqual(self.f("30 сентября в 11:30"), [("2026-09-30 11:30", False)])
        self.assertEqual(self.f("через 2 часа позвоню"), [("2026-09-25 14:00", False)])
        self.assertEqual(self.f("tomorrow at 10 am"), [("2026-09-26 10:00", False)])
        self.assertEqual(self.f("Meeting at 3 pm"), [("2026-09-25 15:00", False)])
        self.assertEqual(self.f("в 9:00"), [("2026-09-26 09:00", False)])            # 9 утра, написанное днём, — завтра

    def test_not_times(self):
        for text in ("Сборка #413 прошла за 6 мин", "версия 2.4 ушла", "IP 192.168.1.10", "650 ₽, срок до 10 числа"):
            self.assertEqual(self.f(text), [], text)
        # прошедшее время не предлагаем
        self.assertEqual(when.find("созвон был в 11:00", self.base, datetime(2026, 9, 26, 12, 0)), [])


class QuietTest(unittest.TestCase):
    q = {"enabled": True, "schedule": [{"days": [0, 1, 2, 3, 4], "from": "22:00", "to": "08:00"}],
         "manual_until": "", "follow_dnd": True}

    def test_schedule_and_manual(self):
        ev = lambda s, **kw: quiet.evaluate(kw.get("q", self.q), datetime.strptime(s, "%Y-%m-%d %H:%M"), kw.get("dnd"))  # noqa: E731
        self.assertEqual(ev("2026-09-25 23:10"), (True, "schedule", "08:00"))     # пятница вечер
        self.assertEqual(ev("2026-09-26 07:59"), (True, "schedule", "08:00"))     # утро субботы — хвост пятницы
        self.assertEqual(ev("2026-09-27 01:00")[0], False)                         # воскресенье ночью — нет
        self.assertEqual(ev("2026-09-25 12:00", q=dict(self.q, enabled=False), dnd=True), (True, "dnd", ""))
        self.assertTrue(ev("2026-09-25 12:00", q=dict(self.q, manual_until="2099-01-01 00:00:00"))[0])
        self.assertFalse(ev("2026-09-25 23:10", q=dict(self.q, manual_until="-2099-01-01 00:00:00"))[0])

    def test_off_while_dnd(self):
        """«Выключить сейчас» при «Не беспокоить» GNOME работает, пока оно включено; выключили его —
        тихие часы снова идут за ним."""
        db = common.new_db("quiet-dnd.db")
        conn = sqlite3.connect(db)
        dnd = {"on": True}
        with mock.patch.object(quiet, "gnome_dnd", side_effect=lambda: dnd["on"]):
            self.assertFalse(quiet.step(conn)["active"])           # по умолчанию «Не беспокоить» не наша тишина
            self.assertTrue(quiet.step(conn)["dnd"])               # но видно, что оно включено
            rules.set_prefs(conn, {"quiet": {"follow_dnd": True}})
            conn.commit()
            self.assertEqual(quiet.step(conn)["reason"], "dnd")
            self.assertFalse(quiet.set_manual(conn, "off")["active"])
            self.assertFalse(quiet.step(conn)["active"])           # «Не беспокоить» всё ещё включено
            dnd["on"] = False
            quiet.step(conn)
            self.assertEqual(rules.get_prefs(conn)["quiet"]["manual_until"], "")
            dnd["on"] = True
            self.assertTrue(quiet.step(conn)["active"])            # включили снова — снова тихо
        conn.close()

    def test_quiet_mutes_sound_and_summary(self):
        db = common.new_db("quiet.db")
        prefs(db, {"quiet": {"enabled": True, "manual_until": "2099-01-01 00:00:00", "summary": True}})
        conn = sqlite3.connect(db)
        with mock.patch.object(quiet, "gnome_dnd", return_value=None):
            quiet.step(conn)
            self.assertTrue(quiet.current["active"])
            rules.save_rule(conn, rules.clean_rule({"src": "*", "text": "срочно", "action": "sound"}))
            conn.commit()
            rec = common.put(conn, "eXpress", "Команда", "Иван: срочно созвон")
            with mock.patch("actions.play_sound") as snd:
                rules.apply_on_insert(conn, rec)
                snd.assert_not_called()                    # тихо — звук правила молчит
            rules.set_prefs(conn, {"quiet": {"manual_until": ""}})
            conn.commit()
            quiet.step(conn)
        conn.close()
        self.assertFalse(quiet.current["active"])
        digest = rows(db, "app = 'messhub-digest'")
        self.assertEqual(len(digest), 1)
        self.assertIn("Пока было тихо, пришло 1", digest[0]["message"])


class RemindersTest(unittest.TestCase):
    def test_add_fire_and_rows(self):
        db = common.new_db("remind.db")
        prefs(db, {})
        conn = sqlite3.connect(db)
        rec = common.put(conn, "eXpress", "Команда", "Иван: созвон завтра в 10:00")
        soon = (datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
        reminders.add(conn, rec["id"], soon, soon)
        with self.assertRaises(ValueError):
            reminders.add(conn, rec["id"], "2000-01-01 00:00")
        conn.commit()
        self.assertEqual(reminders.for_ids(conn, [rec["id"]]), {rec["id"]: soon})
        conn.execute("UPDATE reminders SET at = '2000-01-01 00:00'")    # «наступило»
        with mock.patch("actions.play_sound"), mock.patch.object(reminders, "popup") as pop:
            self.assertEqual(reminders.fire_due(conn), 1)
            pop.assert_called_once()
        conn.close()
        card = rows(db, "app = 'messhub-reminders'")[0]
        self.assertIn("созвон завтра", card["message"])
        # на доске у сообщения со временем — «times»
        conn = sqlite3.connect(db)
        common.put(conn, "eXpress", "Команда", "Иван: встречаемся послезавтра в 11:00", event_ts=time.time(),
                   event_iso=datetime.now().isoformat(timespec="seconds"))
        conn.close()
        out, _, _ = serve.query(db, limit=10, widget=True, unread=True)
        self.assertTrue(any(r["times"] for r in out))


class CalendarTest(unittest.TestCase):
    ICS = ("BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a1\nDTSTART:{start}\nDTEND:{end}\nSUMMARY:Планёрка\n"
           "LOCATION:Zoom\\, комната 2\nRRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR\nEND:VEVENT\n"
           "BEGIN:VEVENT\nUID:c1\nDTSTART:{start}\nSUMMARY:Отменено\nSTATUS:CANCELLED\nEND:VEVENT\nEND:VCALENDAR\n")

    def test_parse_and_card(self):
        evs = calendar_src.parse_events(self.ICS.format(start="20260925T110000", end="20260925T113000"))
        self.assertEqual(evs[0]["location"], "Zoom, комната 2")
        occ = calendar_src.occurrences(evs[0], datetime(2026, 9, 25), datetime(2026, 10, 3))
        self.assertEqual([d.strftime("%a %H:%M") for d in occ], ["Fri 11:00", "Mon 11:00", "Wed 11:00", "Fri 11:00"])
        # DTSTART во вторник, повтор по пн/ср/пт: сам вторник — первое повторение (RFC 5545)
        tue = calendar_src.parse_events(self.ICS.format(start="20260929T110000", end="20260929T113000"))[0]
        occ = calendar_src.occurrences(tue, datetime(2026, 9, 28), datetime(2026, 10, 3))
        self.assertEqual([d.strftime("%a %d") for d in occ], ["Tue 29", "Wed 30", "Fri 02"])
        # давний повтор (ежедневный с 2005 года) — не теряется за пределом 5000 шагов
        old = calendar_src.parse_events(self.ICS.format(start="20050103T093000", end="20050103T100000")
                                        .replace("FREQ=WEEKLY;BYDAY=MO,WE,FR", "FREQ=DAILY"))[0]
        occ = calendar_src.occurrences(old, datetime(2026, 9, 25), datetime(2026, 9, 27))
        self.assertEqual([d.strftime("%d %H:%M") for d in occ], ["25 09:30", "26 09:30"])
        # за 10 минут до начала — карточка; второй проверкой — не повторяется
        start = (datetime.now() + timedelta(minutes=7)).replace(second=0, microsecond=0)
        d = tempfile.mkdtemp(dir=common.TMP)
        path = os.path.join(d, "work.ics")
        with open(path, "w", encoding="utf-8") as f:          # без повтора: день недели не важен
            f.write(self.ICS.replace("RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR\n", "").format(
                start=start.strftime("%Y%m%dT%H%M%S"), end=(start + timedelta(minutes=30)).strftime("%Y%m%dT%H%M%S")))
        db = common.new_db("cal.db")
        prefs(db, {"themed": {"calendar": {"enabled": True, "before": 10, "agenda": False, "files": [path]}}})
        conn = sqlite3.connect(db)
        cfg = rules.themed(rules.get_prefs(conn))["calendar"]
        with mock.patch.object(calendar_src, "HOME", d):          # без настоящих календарей Evolution
            calendar_src.step(conn, cfg)
            calendar_src.step(conn, cfg)
        conn.close()
        cards = rows(db, "app = 'messhub-calendar'")
        self.assertEqual([c["chat"] for c in cards], ["Планёрка"])
        self.assertRegex(cards[0]["message"], r"через [678] мин")
        self.assertEqual(rules.source_of("messhub-calendar")["key"], "calendar")


class ResourcesTest(unittest.TestCase):
    def test_threshold_and_fixed(self):
        db = common.new_db("res.db")
        prefs(db, {"themed": {"resources": {"enabled": True, "disk_pct": 90}}})
        conn = sqlite3.connect(db)
        cfg = rules.themed(rules.get_prefs(conn))["resources"]
        usage = {"/": (95, 5 * 1024 ** 3, 100 * 1024 ** 3)}
        patches = (mock.patch.object(resources, "mounts", return_value=["/"]),
                   mock.patch.object(resources, "disk_usage", side_effect=lambda p: usage),
                   mock.patch.object(resources, "memory", return_value=(40, 0, 16 * 1024 ** 3)),
                   mock.patch.object(resources, "cpu_temp", return_value=60),
                   mock.patch.object(resources, "gpu_temps", return_value=[]),
                   mock.patch.object(resources, "containers_df", return_value="$ podman system df\nImages 40GB"))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        resources.Checker(conn, cfg).run()
        resources.Checker(conn, cfg).run()                  # всё ещё полон — вторая карточка не нужна
        r = rows(db, "app = 'messhub-resources'")
        self.assertEqual(len(r), 1)
        self.assertIn("заполнен на 95%", r[0]["message"])
        self.assertIn("podman system df", r[0]["details"])
        usage["/"] = (88, 12 * 1024 ** 3, 100 * 1024 ** 3)  # 88 > 90−3 — ещё не «починилось»
        resources.Checker(conn, cfg).run()
        self.assertFalse(rows(db, "app = 'messhub-resources'")[0]["resolved_at"])
        usage["/"] = (80, 20 * 1024 ** 3, 100 * 1024 ** 3)
        resources.Checker(conn, cfg).run()
        conn.close()
        self.assertTrue(rows(db, "app = 'messhub-resources'")[0]["resolved_at"])


class LogwatchTest(unittest.TestCase):
    def test_follow_file_and_card(self):
        path = os.path.join(common.TMP, "app.log")
        with open(path, "w") as f:
            f.write("old ERROR line — до начала слежки\n")
        stop = threading.Event()
        gen = logwatch._follow_file(path, stop)
        got = []

        def reader():
            for line in gen:
                got.append(line)
                if len(got) >= 2:
                    stop.set()
        th = threading.Thread(target=reader, daemon=True)
        th.start()
        time.sleep(0.5)
        with open(path, "a") as f:
            f.write("ok\nERROR: boom\n")
        th.join(10)
        stop.set()
        self.assertEqual(got, ["ok", "ERROR: boom"])      # старые строки не читаем, новые — да
        db = common.new_db("lw.db")
        prefs(db, {})
        b = logwatch.Bucket()
        for i in range(3):
            b.add(f"ERROR {i}", time.time())
        snap = b.take_if_due(time.time() + logwatch.EVERY_S + 1, logwatch.EVERY_S)
        w = rules.clean_watch({"id": "w1", "name": "app", "target": path, "pattern": "ERROR"})
        logwatch.card(db, w, *snap)
        c = rows(db, "app = 'messhub-logwatch'")[0]
        self.assertIn("3 совпадений за час", c["message"])
        self.assertEqual(c["details"].splitlines(), ["ERROR 0", "ERROR 1", "ERROR 2"])
        pv = logwatch.preview({"target": path, "pattern": "error"})
        self.assertEqual(pv["matches"], 2)
        with self.assertRaises(ValueError):
            rules.clean_watch({"target": path, "pattern": "("})


@unittest.skipIf(os.name == "nt", "скрипт-пример — sh")
class ScriptsTest(unittest.TestCase):
    def test_script_cards(self):
        db = common.new_db("scripts.db")
        prefs(db, {})
        os.makedirs(scripts.DIR, exist_ok=True)
        path = os.path.join(scripts.DIR, "check.sh")
        with open(path, "w") as f:
            f.write('#!/bin/sh\n# messhub: interval=60\n'
                    'echo \'{"source": "Мой сервер", "chat": "диск", "text": "занято 97%", "key": "my:disk", "urgency": 2}\'\n'
                    'echo "мусор, не JSON"\necho \'{"bad": 1}\'\n')
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        found = {n: iv for n, _, iv in scripts.discover()}
        self.assertEqual(found.get("check.sh"), 60)
        cards, err = scripts.run_one(db, "check.sh", path)
        self.assertEqual(cards, 1)
        self.assertIn("строк с ошибкой: 1", err)
        self.assertEqual(rows(db, "app = 'Мой сервер'")[0]["event_key"], "ingest:my:disk")
        ex = scripts.make_example()
        self.assertTrue(ex.endswith(".off") and os.path.exists(ex))
        self.assertNotIn(os.path.basename(ex), [n for n, _, _ in scripts.discover()])   # пример выключен


class ScreenTest(unittest.TestCase):
    def test_titles_and_pipewire(self):
        self.assertTrue(screen.title_match(["Терминал", "meet.google.com is sharing your screen."]))
        self.assertTrue(screen.title_match(["Приложению meet.google.com предоставлен доступ к вашему экрану."]))
        self.assertTrue(screen.title_match(["Демонстрация"], extra=["демонстрация"]))
        self.assertFalse(screen.title_match(["Firefox", "Документ.odt — LibreOffice"]))
        dump = json.dumps([{"type": "PipeWire:Interface:Node", "info": {"state": "running", "props": {
            "media.class": "Video/Source", "node.name": "gnome-shell-screencast"}}}])
        self.assertTrue(screen.pipewire_sharing(dump))
        self.assertFalse(screen.pipewire_sharing(json.dumps([{"type": "PipeWire:Interface:Node", "info": {
            "state": "suspended", "props": {"media.class": "Video/Source", "node.name": "gnome-shell-screencast"}}}])))


class RagTest(unittest.TestCase):
    """Умный поиск: сбойный текст (NaN у bge-m3 → 500 на всю порцию) не держит очередь."""

    def test_bad_text_does_not_block_queue(self):
        db = common.new_db("rag.db")
        prefs(db, {"rag": {"enabled": True, "model": "bge-m3"}})
        conn = sqlite3.connect(db)
        common.put(conn, "eXpress", "Команда", "Иван: обычный текст про отчёт")
        common.put(conn, "eXpress", "Команда", "Иван: СБОЙ целиком")
        common.put(conn, "eXpress", "Команда", "Иван: начало со СБОЙ. А тут нормальный хвост")
        conn.commit()
        calls = []

        def fake_call(path, body=None, timeout=30, method=None):
            if body is None:                                               # список моделей Ollama
                return {"models": [{"name": "bge-m3:latest"}]}
            calls.append(len(body["input"]))
            if any("СБОЙ" in x for x in body["input"]):
                raise urllib.error.HTTPError("u", 500, "Internal Server Error", {}, None)
            return {"embeddings": [[1.0, float(len(x))] for x in body["input"]]}
        with mock.patch.object(rag, "_call", fake_call):
            self.assertEqual(rag.index_step(db), 3)
            self.assertEqual(rag.index_step(db), 0)
            st = rag.status(conn)
            self.assertEqual((st["indexed"], st["skipped"], st["error"]), (2, 1, ""))
            self.assertEqual(calls[0], 3)                                  # сначала вся порция
            self.assertEqual(len(rag.search(conn, "отчёт", 5)), 2)         # пропущенное не мешает поиску
            self.assertEqual(rag.retry_skipped(db), 1)                     # и снова пробуется позже
            self.assertEqual(rag.status(conn)["skipped"], 0)
            # Вектор другой размерности пропускается без падения search()
            from array import array
            conn.execute("INSERT INTO embeddings (message_id, model, vec) VALUES (999999, 'bge-m3', ?)",
                         (array("f", [1.0, 2.0, 3.0]).tobytes(),))
            conn.commit()
            self.assertEqual(len(rag.search(conn, "отчёт", 5)), 2)
        conn.close()
        e = urllib.error.HTTPError("u", 404, "nf", {}, None)
        self.assertIn("Установить", rag.human_error(e))
        self.assertIn("не запущена", rag.human_error(urllib.error.URLError(ConnectionRefusedError("refused"))))

    def test_urls_only_local(self):
        """Адрес Ollama для RAG — строго на этом компьютере (localhost / 127.0.0.1 / [::1])."""
        self.assertTrue(rules.ai_url_ok("http://127.0.0.1:11434"))
        self.assertTrue(rules.ai_url_ok("http://localhost:1234"))
        self.assertTrue(rules.ai_url_ok("http://[::1]:11434"))
        for bad in ("http://192.168.1.5:11434", "http://10.0.0.2:11434",
                    "https://api.openai.com", "http://evil.example:11434", "http://8.8.8.8:11434"):
            self.assertFalse(rules.ai_url_ok(bad), bad)
        db = common.new_db("rag_local.db")
        conn = sqlite3.connect(db)
        try:
            with self.assertRaises(ValueError):
                rules.set_prefs(conn, {"rag": {"ollama_url": "http://192.168.1.5:11434"}})
            with self.assertRaises(ValueError):
                rules.set_prefs(conn, {"rag": {"ollama_url": "http://evil.example:11434"}})
            conn.execute("INSERT OR REPLACE INTO prefs (key, value) VALUES (?, ?)", ("rag", json.dumps({
                "enabled": True,
                "ollama_url": "http://192.168.1.5:11434",
            })))
            conn.commit()
            p = rules.get_prefs(conn)["rag"]
            self.assertEqual(p["ollama_url"], "http://127.0.0.1:11434")
        finally:
            conn.close()

    def test_ollama_url_from_prefs(self):
        """rag.ollama_url читает prefs['rag']['ollama_url'], если OLLAMA_HOST не задан."""
        db = common.new_db("rag_url.db")
        prefs(db, {"rag": {"ollama_url": "http://localhost:11435"}})
        conn = sqlite3.connect(db)
        try:
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("OLLAMA_HOST", None)
                self.assertEqual(rag.ollama_url(conn), "http://localhost:11435")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
