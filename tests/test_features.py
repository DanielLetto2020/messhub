"""Время в тексте и напоминания, тихие часы, календарь, ресурсы, журналы, свои скрипты, показ экрана,
ассистент (выборка, беседы, поток ответа — модель подменена). Без сети и рабочего стола."""
import json
import os
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
import urllib.request
from datetime import datetime, timedelta
import base64
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import common
import ai
import calendar_src
import events
import logwatch
import paths
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
        w = rules.clean_watch({"id": "w1", "name": "app", "target": path, "pattern": "ERROR"})
        logwatch.card(db, w, b)
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


class AiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = common.new_db("ai.db")
        prefs(cls.db, {})
        conn = sqlite3.connect(cls.db)
        common.put(conn, "eXpress", "Команда", "Иван: отчёт по проекту нужен к пятнице")
        common.put(conn, "telegram-desktop", "Мама", "Позвони, как освободишься")
        events.emit(conn, "containers", "shop-api", "упал с кодом 1", key="container:podman:shop-api", urgency=2)
        conn.commit()
        conn.close()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(cls.db))
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def post(self, path, body):
        r = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.read().decode()

    def test_urls_only_local(self):
        self.assertTrue(rules.ai_url_ok("http://127.0.0.1:11434"))
        self.assertTrue(rules.ai_url_ok("http://localhost:1234"))
        self.assertFalse(rules.ai_url_ok("http://192.168.1.5:11434"))
        self.assertTrue(rules.ai_url_ok("http://192.168.1.5:11434", allow_lan=True))
        for bad in ("https://api.openai.com", "http://evil.example:11434", "http://8.8.8.8:11434"):
            self.assertFalse(rules.ai_url_ok(bad, allow_lan=True), bad)
        with self.assertRaises(ValueError):
            rules.clean_ai({"ollama_url": "http://evil.example:11434"})

    def test_context_selection(self):
        conn = sqlite3.connect(self.db)
        st = dict(ai.session_defaults(conn), period="all")
        lines, ids, summary, _ = ai.build_context(conn, st, "что с отчётом по проекту?")
        self.assertEqual(len(ids), 3)
        self.assertTrue(lines[0].startswith("#"))
        self.assertIn("Всего сообщений: 3", summary)
        lines, ids, _, _ = ai.build_context(conn, dict(st, sources=["containers"]), "что упало?")
        self.assertEqual(len(ids), 1)
        self.assertIn("shop-api", lines[0])
        conn.close()

    def test_sessions_and_streaming_chat(self):
        s = json.loads(self.post("/api/ai/session", {"settings": {"provider": "ollama", "model": "demo:1b", "period": "all"}}))
        self.assertEqual(s["settings"]["model"], "demo:1b")
        s = json.loads(self.post("/api/ai/session", {"id": s["id"], "settings": {"temperature": 0.1}}))
        self.assertEqual((s["settings"]["temperature"], s["settings"]["model"]), (0.1, "demo:1b"))   # остальное не сбросилось
        seen = {}

        def fake_stream(ai_prefs, st, messages):
            seen["system"] = messages[0]["content"]
            yield {"think": "надо найти отчёт"}                     # отдельное поле размышлений (Ollama)
            for piece in ("<think>ещё подумаю</think>Отчёт нужен ", "к пятнице (#1)."):   # и теги в тексте
                yield {"t": piece}
            yield {"tokens": 7, "done_reason": "stop"}
        with mock.patch.object(ai, "_stream", fake_stream), mock.patch.object(ai, "thinks", return_value=True):
            out = self.post("/api/ai/chat", {"session": s["id"], "text": "Что с отчётом?"})
        evs = [json.loads(line) for line in out.splitlines() if line.strip()]
        self.assertEqual([e["type"] for e in evs], ["context", "think", "think", "token", "token", "done"])
        self.assertEqual(evs[-1]["tokens"], 7)
        self.assertEqual(evs[-1]["thinking"], "надо найти отчётещё подумаю")
        self.assertIn("#1 · ", seen["system"])                      # сообщения из базы — в промпте
        with urllib.request.urlopen(f"{self.base}/api/ai/session?id={s['id']}", timeout=10) as r:
            full = json.load(r)
        self.assertEqual([m["role"] for m in full["messages"]], ["user", "assistant"])
        self.assertEqual(full["messages"][1]["content"], "Отчёт нужен к пятнице (#1).")
        self.assertEqual(full["title"], "Что с отчётом?")
        with urllib.request.urlopen(f"{self.base}/api/ai/export?id={s['id']}", timeout=10) as r:
            self.assertIn("**Ассистент**", json.load(r)["text"])
        out = self.post("/api/ai/chat", {"session": s["id"], "text": ""})
        self.assertEqual(json.loads(out.splitlines()[-1])["type"], "error")
        self.post("/api/ai/session/delete", {"id": s["id"]})
        with urllib.request.urlopen(f"{self.base}/api/ai/sessions", timeout=10) as r:
            self.assertNotIn(s["id"], [x["id"] for x in json.load(r)])

    def test_empty_answer_retried_without_thinking(self):
        """Весь запас ушёл на размышления — второй заход без них; не помогло — объяснить, что поправить."""
        s = json.loads(self.post("/api/ai/session", {"settings": {"provider": "ollama", "model": "demo:1b"}}))
        calls = []

        def think_then_answer(ai_prefs, st, messages):
            calls.append((st["think"], st["_predict"]))
            if st["think"] != "off":
                yield {"think": "долго-долго думаю"}
                yield {"tokens": 4000, "done_reason": "length"}
            else:
                yield {"t": "Коротко: всё спокойно."}
                yield {"tokens": 12, "done_reason": "stop"}
        with mock.patch.object(ai, "_stream", think_then_answer), mock.patch.object(ai, "thinks", return_value=True):
            out = self.post("/api/ai/chat", {"session": s["id"], "text": "Что было?"})
        evs = [json.loads(x) for x in out.splitlines() if x.strip()]
        self.assertEqual([e["type"] for e in evs], ["context", "think", "retry", "token", "done"])
        self.assertEqual([c[0] for c in calls], ["hide", "off"])
        self.assertGreater(calls[0][1], 1024)            # размышлениям — весь остаток контекста, не «длина ответа»
        done = evs[-1]
        self.assertEqual((done["tokens"], done["thinking"]), (4012, "долго-долго думаю"))
        self.assertIn("ответ дан без них", done["note"])
        msgs = json.loads(urllib.request.urlopen(f"{self.base}/api/ai/session?id={s['id']}", timeout=10).read())["messages"]
        self.assertEqual(msgs[-1]["content"], "Коротко: всё спокойно.")

        def only_thinking(ai_prefs, st, messages):
            yield {"think": "думаю"}
            yield {"tokens": 1024, "done_reason": "length"}
        with mock.patch.object(ai, "_stream", only_thinking), mock.patch.object(ai, "thinks", return_value=True):
            out = self.post("/api/ai/chat", {"session": s["id"], "text": "А ещё?"})
        done = json.loads(out.splitlines()[-1])
        self.assertIn("весь запас ушёл на размышления", done["note"])

    def test_context_plan(self):
        """Контекст делится с запасом на размышления; у OpenRouter — контекст самой модели, не настройка."""
        st = {"provider": "ollama", "num_ctx": 8192, "max_tokens": 1024}
        p = ai.plan(st, None, thinking=True)
        self.assertEqual(p["ctx"], 8192)
        self.assertGreaterEqual(p["out"], 1024 + 2048)
        self.assertEqual(p["prompt"], 8192 - p["out"] - ai.MARGIN)
        self.assertEqual(ai.plan(st)["out"], 1024)
        orst = dict(st, provider="openrouter")
        p = ai.plan(orst, {"ctx": 1000000, "max_out": 128000}, thinking=True)
        self.assertEqual((p["ctx"], p["out"]), (1000000, 1024 + ai.OR_THINK))
        self.assertEqual(ai.plan(orst, {"ctx": 200000, "max_out": 8000}, thinking=True)["out"], 8000)
        self.assertEqual(ai.plan(orst, {})["ctx"], 32768)          # каталог не загрузился
        self.assertEqual(ai._or_reasoning(True, {}), None)
        self.assertEqual(ai._or_reasoning(False, {}), {"effort": "none"})
        self.assertEqual(ai._or_reasoning(False, {"efforts": ["high", "medium", "none"]}), {"effort": "none"})
        self.assertEqual(ai._or_reasoning(False, {"efforts": ["xhigh", "medium", "low"]}), {"enabled": False})
        self.assertEqual(ai._or_reasoning(False, {"mandatory": True, "efforts": ["high", "medium", "low"]}), {"effort": "low"})
        # русский текст: ≈2 символа на токен (замер на qwen3) — оценка не должна занижать
        self.assertGreaterEqual(ai.est_tokens("Созвон переносим на 15:00, пришлите отчёт"), 20)

    def test_selection_says_what_did_not_fit(self):
        conn = sqlite3.connect(self.db)
        st = dict(ai.session_defaults(conn), period="all")
        lines, ids, summary, _ = ai.build_context(conn, st, "что было?", budget=len(ai._line(
            {"id": 1, "src_name": "x", "chat": "", "sender": "", "text": "", "iso": "", "details": ""}, False)) + 60)
        self.assertLess(len(ids), 3)
        self.assertIn("Не влезло в контекст:", summary)
        conn.close()

    def test_think_modes_and_splitter(self):
        self.assertEqual(rules.clean_ai({"think": True})["think"], "show")
        self.assertEqual(rules.clean_ai({"think": False})["think"], "hide")
        self.assertEqual(rules.clean_ai({"think": "off"})["think"], "off")
        sp, out = ai.ThinkSplitter(), []
        for ch in ("<th", "ink>думаю</th", "ink>Отв", "ет <"):
            out += sp.feed(ch)
        out += sp.flush()
        self.assertEqual("".join(p for k, p in out if k == "think"), "думаю")
        self.assertEqual("".join(p for k, p in out if k == "answer"), "Ответ <")

    def test_pages_served(self):
        with urllib.request.urlopen(self.base + "/assistant", timeout=10) as r:
            self.assertIn(b'id="view"', r.read())


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


class FakeOpenRouter(BaseHTTPRequestHandler):
    """Поддельный OpenRouter: каталог моделей и потоковый ответ (SSE) с размышлениями и ценой."""
    seen = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"data": [
            {"id": "demo/vision-pro", "name": "Vision Pro", "context_length": 128000,
             "top_provider": {"context_length": 128000, "max_completion_tokens": 64000},
             "reasoning": {"mandatory": True, "supported_efforts": ["high", "medium", "low"]},
             "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
             "supported_parameters": ["reasoning"], "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
            {"id": "demo/free:free", "name": "Free", "context_length": 32000, "architecture": {},
             "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "demo/painter", "name": "Painter", "architecture": {"output_modalities": ["image"]}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        FakeOpenRouter.seen = {"auth": self.headers.get("Authorization"),
                               "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for ev in ({"choices": [{"delta": {"reasoning": "считаю"}}]}, {"choices": [{"delta": {"content": "Готово "}}]},
                   {"choices": [{"delta": {"content": "(#1)."}, "finish_reason": "stop"}]},
                   {"choices": [], "usage": {"completion_tokens": 5, "cost": 0.00042}}):
            self.wfile.write(b": OPENROUTER PROCESSING\n\ndata: " + json.dumps(ev).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")


class OpenRouterTest(AiTest):
    """Облачные модели: только по согласию и с ключом; ключ наружу не отдаётся; картинки к вопросу."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fake = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenRouter)
        threading.Thread(target=cls.fake.serve_forever, daemon=True).start()
        cls.patch = mock.patch.object(ai, "OPENROUTER", f"http://127.0.0.1:{cls.fake.server_address[1]}")
        cls.patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.fake.shutdown()
        cls.fake.server_close()
        super().tearDownClass()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as r:
            return json.load(r)

    def post_err(self, path, body):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post(path, body)
        return json.load(cm.exception)["error"]

    def test_openrouter_consent_key_and_stream(self):
        self.post("/api/ai/setup", {"ai": {"openrouter": True, "openrouter_consent": "x"}})   # в обход согласия — нельзя
        self.assertFalse(self.get("/api/ai/status")["prefs"]["openrouter"])
        self.assertIn("ключ", self.post_err("/api/ai/openrouter", {"enabled": True, "consent": True}))
        self.assertIn("согласие", self.post_err("/api/ai/openrouter", {"enabled": True, "key": "sk-or-v1-demo-token-not-real-1234"}))
        st = json.loads(self.post("/api/ai/openrouter", {"enabled": True, "consent": True}))
        self.assertTrue(st["enabled"])
        if os.name != "nt":                         # на Windows прав «600» нет — там профиль пользователя
            self.assertEqual(stat.S_IMODE(os.stat(paths.OPENROUTER_CFG).st_mode), 0o600)
        full = json.dumps(self.get("/api/ai/status"), ensure_ascii=False)
        self.assertNotIn("demo-token-not-real", full)                      # ключ странице не отдаётся
        self.assertIn("…1234", full)
        models = self.get("/api/ai/openrouter/models")["models"]
        self.assertEqual([m["name"] for m in models], ["demo/free:free", "demo/vision-pro"])   # без моделей-«художников»
        self.assertTrue(models[0]["free"] and models[1]["vision"] and models[1]["reasoning"])
        self.assertEqual(models[1]["price_in"], 1.0)
        self.assertEqual((models[1]["mandatory"], models[1]["max_out"], models[0]["mandatory"]), (True, 64000, False))

        s = json.loads(self.post("/api/ai/session", {"settings": {"provider": "openrouter", "model": "demo/vision-pro", "period": "all"}}))
        out = self.post("/api/ai/chat", {"session": s["id"], "text": "Что было?", "images": ["data:image/png;base64," + base64.b64encode(PNG).decode()]})
        evs = [json.loads(x) for x in out.splitlines() if x.strip()]
        self.assertEqual(evs[-1]["type"], "done", evs[-1])
        self.assertTrue(evs[-1]["external"])
        self.assertEqual(evs[-1]["cost"], 0.00042)
        self.assertEqual(evs[-1]["thinking"], "считаю")
        self.assertEqual(FakeOpenRouter.seen["auth"], "Bearer sk-or-v1-demo-token-not-real-1234")
        body = FakeOpenRouter.seen["body"]
        self.assertEqual(body["max_tokens"], 1024 + ai.OR_THINK)          # размышлениям — запас сверх ответа
        self.assertNotIn("reasoning", body)
        conn = sqlite3.connect(self.db)
        self.assertEqual(ai.model_info(conn, "openrouter", "demo/vision-pro")["mandatory"], True)
        conn.close()
        last = FakeOpenRouter.seen["body"]["messages"][-1]
        self.assertEqual(last["content"][0], {"type": "text", "text": "Что было?"})
        self.assertTrue(last["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))
        msgs = self.get(f"/api/ai/session?id={s['id']}")["messages"]
        self.assertEqual(msgs[1]["content"], "Готово (#1).")
        # «не просить размышлять» у модели, которая думает всегда, — наименьшее усилие, а не exclude
        self.post("/api/ai/session", {"id": s["id"], "settings": {"think": "off"}})
        self.post("/api/ai/chat", {"session": s["id"], "text": "Коротко?"})
        self.assertEqual(FakeOpenRouter.seen["body"]["reasoning"], {"effort": "low"})
        name = msgs[0]["meta"]["images"][0]
        with urllib.request.urlopen(f"{self.base}/ai-image/{name}", timeout=10) as r:
            self.assertEqual((r.headers["Content-Type"], r.read()), ("image/png", PNG))

        self.post("/api/ai/setup", {"ai": {"provider": "openrouter", "model": "demo/vision-pro"}})
        st = json.loads(self.post("/api/ai/openrouter", {"enabled": False}))
        self.assertFalse(st["enabled"])
        self.assertEqual(self.get("/api/ai/status")["prefs"]["provider"], "")      # новые беседы — не в облако
        out = self.post("/api/ai/chat", {"session": s["id"], "text": "Ещё?"})
        self.assertIn("OpenRouter выключен", json.loads(out.splitlines()[-1])["error"])
        self.post("/api/ai/session/delete", {"id": s["id"]})
        self.assertIsNone(ai.image_file(name))                             # картинка удалена вместе с беседой
        self.post("/api/ai/openrouter", {"enabled": False, "key": ""})
        self.assertFalse(os.path.exists(paths.OPENROUTER_CFG))

    def test_images_checked_and_formatted(self):
        for bad in ("data:text/plain;base64,aGk=", "data:image/png;base64," + base64.b64encode(b"not an image").decode(), "http://x/y.png"):
            with self.assertRaises(ValueError):
                ai.save_images([bad])
        url = "data:image/png;base64," + base64.b64encode(PNG).decode()
        a, b = ai.save_images([url, url])
        self.assertEqual(a, b)                                             # одна и та же картинка — один файл
        self.assertIsNone(ai.image_file("../../etc/passwd"))
        msg = {"role": "user", "content": "что тут?"}
        self.assertEqual(ai._with_images("ollama", msg, [a])["images"], [base64.b64encode(PNG).decode()])
        self.assertEqual(ai._with_images("lmstudio", msg, [a])["content"][1]["type"], "image_url")
        self.assertIs(ai._with_images("ollama", msg, []), msg)


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
        conn.close()
        e = urllib.error.HTTPError("u", 404, "nf", {}, None)
        self.assertIn("Установить", rag.human_error(e))
        self.assertIn("не запущена", rag.human_error(urllib.error.URLError(ConnectionRefusedError("refused"))))


if __name__ == "__main__":
    unittest.main()
