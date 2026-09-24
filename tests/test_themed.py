"""Тематические колонки (контейнеры, службы, команды), «проблема → починилось», журнал,
защита сервера от чужих страниц. Без docker/podman/systemd: их вывод подставлен."""
import json
import os
import sqlite3
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

import common
import applog
import collect
import containers
import events
import ingest
import rules
import run
import serve
import services


def prefs_on(db, **cols):
    """Включить колонки. Язык — русский явно: при «авто» фоновые карточки пишутся на языке
    системы, а у машин CI он английский."""
    conn = sqlite3.connect(db)
    rules.set_prefs(conn, {"language": "ru",
                           "themed": {c: dict(v, enabled=True) if isinstance(v, dict) else {"enabled": v}
                                      for c, v in cols.items()}})
    conn.commit()
    conn.close()


def rows(db, where="1"):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM messages WHERE {where} ORDER BY id")]
    finally:
        conn.close()


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = common.new_db(cls.__name__ + ".db")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), serve.make_handler(cls.db))
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        h = dict(headers or {})
        if data is not None:
            h.setdefault("Content-Type", "application/json")
        r = urllib.request.Request(self.base + path, data=data, headers=h)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
        except urllib.error.HTTPError as e:
            return e.code, e.read()


class GuardTest(ServerCase):
    def test_host_rules(self):
        for h in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765", "192.168.1.5:8765", "localhost"):
            self.assertTrue(serve.host_allowed(h), h)
        for h in ("evil.example:8765", "evil.example", "127.0.0.1.nip.io:8765", ""):
            self.assertFalse(serve.host_allowed(h), h)

    def test_rebinding_blocked(self):
        """Чужое имя в Host (DNS rebinding) — 403 и на страницы, и на API."""
        for path in ("/api/messages", "/widget", "/api/version"):
            code, _ = self.req(path, headers={"Host": f"evil.example:{self.port}"})
            self.assertEqual(code, 403, path)
        code, _ = self.req("/api/version")
        self.assertEqual(code, 200)

    def test_foreign_origin_and_cross_site(self):
        code, _ = self.req("/api/read", {"ids": []}, headers={"Origin": "http://evil.example"})
        self.assertEqual(code, 403)
        code, _ = self.req("/api/read", {"ids": []}, headers={"Origin": f"http://127.0.0.1:{self.port + 1}"})
        self.assertEqual(code, 403)
        code, _ = self.req("/api/messages", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(code, 403)
        code, _ = self.req("/api/read", {"ids": []}, headers={"Origin": f"http://127.0.0.1:{self.port}"})
        self.assertEqual(code, 200)


class LifecycleTest(ServerCase):
    def test_emit_supersede_resolve(self):
        conn = sqlite3.connect(self.db)
        a = events.emit(conn, "containers", "web", "упал с кодом 1", sender="shop", key="container:podman:web",
                        details="line1\nline2", urgency=2)
        b = events.emit(conn, "containers", "web", "упал с кодом 1 · 2-й раз", key="container:podman:web", urgency=2)
        self.assertEqual(events.recent_count(conn, "container:podman:web", 10), 2)
        conn.close()
        first, second = rows(self.db, f"id IN ({a}, {b})")
        self.assertEqual((first["is_read"], second["is_read"]), (1, 0))      # на доске — только свежая
        self.assertEqual(first["details"], "line1\nline2")
        code, vis = self.req("/api/visible")
        self.assertIn(b, vis["ids"])
        self.assertNotIn(str(b), vis["resolved"])
        conn = sqlite3.connect(self.db)
        self.assertEqual(events.resolve(conn, "container:podman:web"), 2)
        self.assertIsNone(events.open_problem(conn, "container:podman:web"))
        conn.close()
        code, vis = self.req("/api/visible")
        self.assertIn(str(b), vis["resolved"])
        code, msgs = self.req(f"/api/messages?rules=1&ids={b}")
        self.assertEqual(msgs[0]["src"], "containers")
        self.assertTrue(msgs[0]["resolved_at"])

    def test_ingest_key_and_resolved(self):
        with mock.patch.object(ingest, "load_token", return_value="k"):
            hdr = {"Authorization": "Bearer k"}
            code, r1 = self.req("/api/ingest", {"source": "Бэкапы", "text": "не прошёл", "key": "nas",
                                                "details": "rsync: error 23"}, headers=hdr)
            code, r2 = self.req("/api/ingest", {"source": "Бэкапы", "text": "снова не прошёл", "key": "nas"}, headers=hdr)
            self.assertEqual(code, 200)
            code, r3 = self.req("/api/ingest", {"source": "Бэкапы", "key": "nas", "status": "resolved"}, headers=hdr)
            self.assertEqual(r3, {"resolved": 2})
            code, bad = self.req("/api/ingest", {"source": "Бэкапы", "status": "resolved"}, headers=hdr)
            self.assertEqual(code, 400)
        one, two = rows(self.db, f"id IN ({r1['id']}, {r2['id']})")
        self.assertEqual((one["is_read"], two["is_read"]), (1, 0))
        self.assertEqual(one["details"], "rsync: error 23")
        self.assertTrue(two["resolved_at"])

    def test_themed_prefs_merge(self):
        conn = sqlite3.connect(self.db)
        rules.set_prefs(conn, {"themed": {"containers": {"enabled": True, "ignore": "test-*, tmp"}}})
        rules.set_prefs(conn, {"themed": {"services": {"enabled": True}}})
        t = rules.themed(rules.get_prefs(conn))
        self.assertTrue(t["containers"]["enabled"] and t["services"]["enabled"])
        self.assertEqual(t["containers"]["ignore"], ["test-*", "tmp"])      # не сбросилось второй правкой
        self.assertFalse(t["commands"]["enabled"])
        with self.assertRaises(ValueError):
            rules.set_prefs(conn, {"themed": {"containers": {"log_lines": 7}}})
        rules.set_prefs(conn, {"themed": {"containers": {"enabled": False}, "services": {"enabled": False}}})
        conn.commit()
        conn.close()
        code, info = self.req("/api/themed")
        self.assertEqual(set(info["prefs"]), {"containers", "services", "commands"})
        self.assertIn("run", info["commands"])


class CommandsTest(ServerCase):
    def test_disabled_then_failure_then_success(self):
        cmd = {"kind": "command", "cmd": "make build", "code": 2, "seconds": 75, "cwd": "/tmp/shop",
               "tail": "\n".join(f"line {i}" for i in range(60))}
        code, r = self.req("/api/event", cmd)
        self.assertTrue(r.get("skipped"))
        prefs_on(self.db, commands={"log_lines": 10})
        code, r = self.req("/api/event", cmd)
        row = rows(self.db, f"id = {r['id']}")[0]
        self.assertEqual((row["app"], row["chat"], row["sender"], row["urgency"]),
                         ("messhub-commands", "make build", "shop", 2))
        self.assertIn("ошибка (код 2) через 1 мин 15 с", row["message"])
        self.assertEqual(row["details"].splitlines(), [f"line {i}" for i in range(50, 60)])
        code, ok = self.req("/api/event", dict(cmd, code=0, seconds=3))
        self.assertEqual(ok["resolved"], 1)
        self.assertTrue(rows(self.db, f"id = {r['id']}")[0]["resolved_at"])
        self.assertIsNone(rows(self.db, f"id = {ok['id']}")[0]["details"])

    def test_run_wrapper_keeps_exit_code(self):
        prefs_on(self.db, commands={"log_lines": 20})
        with mock.patch.dict(os.environ, {"MESSHUB_PORT": str(self.port)}):
            code = run.main(["--", sys.executable, "-c", "print('hello from run'); raise SystemExit(3)"])
        self.assertEqual(code, 3)
        last = rows(self.db, "app = 'messhub-commands'")[-1]
        self.assertIn("(код 3)", last["message"])
        self.assertIn("hello from run", last["details"])
        with mock.patch.dict(os.environ, {"MESSHUB_PORT": str(self.port)}):
            self.assertEqual(run.main(["--", "no-such-command-xyz"]), 127)

    def test_hook_skipped_when_off(self):
        conn = sqlite3.connect(self.db)
        rules.set_prefs(conn, {"themed": {"commands": {"enabled": False}}})
        conn.commit()
        conn.close()
        skip = collect.make_skip(self.db)
        collect._mode["t"] = 0
        self.assertTrue(skip({"app": "messhub-commands"}))
        self.assertFalse(skip({"app": "eXpress"}))
        prefs_on(self.db, commands=True)
        collect._mode["t"] = 0
        self.assertFalse(skip({"app": "messhub-commands"}))


PODMAN_DIED = json.dumps({"ID": "x", "Image": "localhost/shop:dev", "Name": "shop-api", "Status": "died",
                          "Type": "container", "ContainerExitCode": 1,
                          "Attributes": {"com.docker.compose.project": "shop"}})
DOCKER_DIE = json.dumps({"Type": "container", "Action": "die", "Actor": {"ID": "y", "Attributes": {
    "name": "worker", "exitCode": "137", "image": "worker:1", "com.docker.compose.project": "jobs"}}, "time": 1})


class ContainersTest(unittest.TestCase):
    def setUp(self):
        self.db = common.new_db(f"containers-{self._testMethodName}.db")
        prefs_on(self.db, containers={"log_lines": 10, "ignore": ["tmp-*"]})
        self.p1 = mock.patch.object(containers, "logs_tail", return_value="boom\nstack")
        self.p2 = mock.patch.object(containers, "oom_killed", return_value=False)
        self.p1.start()
        self.p2.start()

    def tearDown(self):
        self.p1.stop()
        self.p2.stop()

    def now_later(self):
        return lambda d, fn: fn()

    def test_parse(self):
        p = containers.parse("podman", PODMAN_DIED)
        self.assertEqual((p["name"], p["action"], p["code"], p["project"]), ("shop-api", "die", 1, "shop"))
        self.assertEqual(containers.parse("podman", json.dumps({"Name": "a", "Status": "died", "Type": "container"}))["code"], 0)
        d = containers.parse("docker", DOCKER_DIE)
        self.assertEqual((d["name"], d["action"], d["code"], d["project"]), ("worker", "die", 137, "jobs"))
        h = containers.parse("docker", json.dumps({"Type": "container", "Action": "health_status: unhealthy",
                                                   "Actor": {"Attributes": {"name": "db"}}}))
        self.assertEqual((h["action"], h["health"]), ("health", "unhealthy"))
        self.assertIsNone(containers.parse("docker", json.dumps({"Type": "image", "Action": "pull"})))
        self.assertIsNone(containers.parse("podman", "not json"))

    def test_crash_card_then_healthy(self):
        w = containers.Watcher(self.db, "podman")
        w.handle(containers.parse("podman", PODMAN_DIED), now=1000, later=self.now_later())
        r = rows(self.db)
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["app"], r[0]["chat"], r[0]["sender"], r[0]["urgency"]),
                         ("messhub-containers", "shop-api", "shop", 2))
        self.assertIn("упал с кодом 1", r[0]["message"])
        self.assertEqual(r[0]["details"], "boom\nstack")
        w.handle({"name": "shop-api", "action": "start", "code": 0, "health": "", "project": "shop", "image": ""},
                 now=1010, later=self.now_later())
        self.assertTrue(rows(self.db)[0]["resolved_at"])

    def test_manual_stop_is_quiet(self):
        w = containers.Watcher(self.db, "docker")
        w.handle({"name": "worker", "action": "kill", "code": 0, "health": "", "project": "", "image": ""}, now=100)
        w.handle(containers.parse("docker", DOCKER_DIE), now=105, later=self.now_later())
        self.assertEqual(rows(self.db), [])

    def test_oom_and_repeat_and_ignore(self):
        w = containers.Watcher(self.db, "docker")
        w.handle({"name": "worker", "action": "oom", "code": 0, "health": "", "project": "", "image": ""}, now=200)
        w.handle(containers.parse("docker", DOCKER_DIE), now=201, later=self.now_later())
        w.handle(containers.parse("docker", DOCKER_DIE), now=260, later=self.now_later())
        r = rows(self.db)
        self.assertIn("не хватило памяти", r[0]["message"])
        self.assertIn("2-й раз за 10 минут", r[1]["message"])
        self.assertEqual((r[0]["is_read"], r[1]["is_read"]), (1, 0))
        w.handle({"name": "tmp-build", "action": "die", "code": 1, "health": "", "project": "", "image": ""},
                 now=300, later=self.now_later())
        self.assertEqual(len(rows(self.db)), 2)

    def test_unhealthy_then_healthy(self):
        w = containers.Watcher(self.db, "podman")
        mk = lambda h: {"name": "db", "action": "health", "code": 0, "health": h, "project": "", "image": ""}  # noqa: E731
        w.handle(mk("healthy"), now=1)
        w.handle(mk("unhealthy"), now=2)
        w.handle(mk("unhealthy"), now=3)                 # повтор — без новой карточки
        w.handle(mk("healthy"), now=4)
        r = rows(self.db)
        self.assertEqual(len(r), 1)
        self.assertIn("unhealthy", r[0]["message"])
        self.assertTrue(r[0]["resolved_at"])


WIN_XML = """<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='Service Control Manager'/>
<EventID Qualifiers='49152'>7031</EventID><TimeCreated SystemTime='2026-09-24T10:00:00.000Z'/><EventRecordID>501</EventRecordID></System>
<EventData><Data Name='param1'>Print Spooler</Data><Data Name='param2'>1</Data><Binary>530070006F006F006C00650072000000</Binary></EventData></Event>
<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System><Provider Name='Service Control Manager'/>
<EventID>7000</EventID><TimeCreated SystemTime='2026-09-24T10:05:00.000Z'/><EventRecordID>502</EventRecordID></System>
<EventData><Data Name='param1'>Demo Agent</Data><Data Name='param2'>The system cannot find the file specified.</Data></EventData></Event>"""


class ServicesTest(unittest.TestCase):
    def setUp(self):
        self.db = common.new_db(f"services-{self._testMethodName}.db")
        prefs_on(self.db, services={"log_lines": 10, "user": False})

    def conn(self):
        c = sqlite3.connect(self.db)
        self.addCleanup(c.close)            # и после упавшей проверки (на Windows открытый файл не удалить)
        return c

    def test_parse_failed(self):
        out = "backup-nightly.service loaded failed failed Nightly backup\n● demo.timer loaded failed failed Demo\n"
        self.assertEqual(services.parse_failed(out), ["backup-nightly.service", "demo.timer"])
        self.assertEqual(services.parse_failed(""), [])

    def test_linux_fail_once_then_resolve(self):
        conn = self.conn()
        cfg = rules.themed(rules.get_prefs(conn))["services"]
        with mock.patch.object(services, "failed_units", return_value=["backup-nightly.service"]), \
                mock.patch.object(services, "unit_info", return_value=("Nightly backup", "exit-code", "23")), \
                mock.patch.object(services, "journal_tail", return_value="rsync error 23"):
            self.assertEqual(services.linux_step(conn, cfg), 1)
            services.linux_step(conn, cfg)                  # ещё упавшая — второй карточки нет
        r = rows(self.db)
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["app"], r[0]["chat"], r[0]["event_key"]),
                         ("messhub-services", "backup-nightly.service", "unit:system:backup-nightly.service"))
        self.assertIn("кодом 23", r[0]["message"])
        self.assertEqual(r[0]["details"], "rsync error 23")
        with mock.patch.object(services, "failed_units", return_value=[]):
            services.linux_step(conn, cfg)
        self.assertTrue(rows(self.db)[0]["resolved_at"])

    def test_windows_events(self):
        evs = services.parse_win_events(WIN_XML)
        self.assertEqual([(e["id"], e["event"], e["name"], e["service"]) for e in evs],
                         [(501, 7031, "Print Spooler", "Spooler"), (502, 7000, "Demo Agent", "")])
        self.assertEqual(services.parse_win_events("<!DOCTYPE x [<!ENTITY a 'b'>]>"), [])
        conn = self.conn()
        cfg = rules.themed(rules.get_prefs(conn))["services"]
        with mock.patch.object(services, "win_events", return_value=evs[:1]), \
                mock.patch.object(services, "win_running", return_value=False):
            services.windows_step(conn, cfg)                 # первый раз — только запомнить
        self.assertEqual(rows(self.db), [])
        with mock.patch.object(services, "win_events", return_value=evs), \
                mock.patch.object(services, "win_running", return_value=False):
            services.windows_step(conn, cfg)
        r = rows(self.db)
        self.assertEqual([x["chat"] for x in r], ["Demo Agent"])
        self.assertIn("не запустилась", r[0]["message"])


class LogTest(ServerCase):
    def test_log_write_query_clear(self):
        applog.write("Сбор: всё хорошо")
        applog.write("Почта: не удалось подключиться")
        applog.write("Службы: нет доступа к журналу")
        applog.client_error({"page": "widget", "msg": "TypeError: x is undefined", "where": "widget:12"})
        code, r = self.req("/api/logs")
        lv = {x["msg"]: x["lvl"] for x in r["rows"]}
        self.assertEqual(lv["Сбор: всё хорошо"], "info")
        self.assertEqual(lv["Почта: не удалось подключиться"], "error")
        self.assertEqual(lv["Службы: нет доступа к журналу"], "warn")
        self.assertIn("page", r["sources"])
        code, e = self.req("/api/logs?level=error")
        self.assertTrue(all(x["lvl"] == "error" for x in e["rows"]))
        self.assertGreaterEqual(e["errors_day"], 2)
        code, x = self.req("/api/logs/export", {"level": "all"})
        with open(x["path"], encoding="utf-8") as f:
            self.assertIn("не удалось подключиться", f.read())
        code, _ = self.req("/api/logs/clear", {})
        code, r = self.req("/api/logs")
        self.assertEqual(r["total"], 0)

    def test_mask_and_tee(self):
        home = os.path.expanduser("~")
        self.assertEqual(applog.mask(f"{home}/x.db"), "~/x.db")
        applog.clear()
        tee = applog._Tee(None, "stderr")
        tee.write("GTK: что-то странное\nвторая ")
        tee.write("строка\n")
        r = applog.query()["rows"]
        self.assertEqual([x["msg"] for x in reversed(r)], ["GTK: что-то странное", "вторая строка"])
        self.assertTrue(all(x["lvl"] == "warn" for x in r))


if __name__ == "__main__":
    unittest.main()
