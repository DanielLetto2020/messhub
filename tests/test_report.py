"""Недельный отчёт в Telegram: когда отправляется и когда повторяется.

Раньше отметка «отчёт отправлен» записывалась только при успехе, а фон вызывает maybe_send
раз в минуту. Если Telegram недоступен, отчёт повторялся каждой минутой весь день."""
import sqlite3
import unittest
from datetime import datetime, timedelta
from unittest import mock

import common  # первым: пути программы вычисляются при импорте paths
import report
import rules


def prefs_on(conn, **report_kw):
    r = {"enabled": True, "weekday": 0, "time": "09:00"}
    r.update(report_kw)
    rules.set_prefs(conn, {"report": r})


class DueTest(unittest.TestCase):
    """Когда отчёт считается нужным (чистая функция, без базы)."""

    def setUp(self):
        self.now = datetime(2026, 9, 21, 9, 30)      # понедельник

    def base(self, **kw):
        p = dict(enabled=True, weekday=0, time="09:00")
        p.update(kw)
        return {"report": p, "report_last": "", "report_try": ""}

    def test_due_on_the_day_after_time(self):
        self.assertTrue(report.due(self.base(), self.now))
        self.assertFalse(report.due(self.base(), self.now.replace(hour=8, minute=59)))

    def test_not_due_other_day_or_when_off(self):
        self.assertFalse(report.due(self.base(weekday=4), self.now))
        self.assertFalse(report.due(self.base(enabled=False), self.now))

    def test_sent_today_not_again(self):
        p = self.base()
        p["report_last"] = "2026-09-21"
        self.assertFalse(report.due(p, self.now))

    def test_retry_waits_half_an_hour(self):
        """Неудачная попытка не должна повторяться каждую минуту."""
        p = self.base()
        p["report_try"] = (self.now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        self.assertFalse(report.due(p, self.now))
        p["report_try"] = (self.now - timedelta(minutes=report.RETRY_MIN + 1)).strftime("%Y-%m-%d %H:%M:%S")
        self.assertTrue(report.due(p, self.now))

    def test_bad_timestamp_does_not_block_forever(self):
        """Мусор в сохранённой попытке - пробуем сразу, а не молча жмёмся."""
        for bad in ("", "не дата", None, "2026-13-45"):
            p = self.base()
            p["report_try"] = bad
            self.assertTrue(report.due(p, self.now), bad)


class MaybeSendTest(unittest.TestCase):
    def setUp(self):
        self.db = common.new_db("report.db")
        self.conn = sqlite3.connect(self.db)
        prefs_on(self.conn)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def prefs(self):
        """Настройки читаем отдельным подключением: отчёт пишет их своим (тот же файл),
        иначе этот экземпляр виде бы свой снимок."""
        conn = sqlite3.connect(self.db)
        try:
            return rules.get_prefs(conn)
        finally:
            conn.close()

    def _when(self, offset_minutes=0):
        """Понедельник 09:30 этой недели - отчёт включён именно на понедельник и на 09:00."""
        base = datetime.now().replace(tzinfo=None)
        midnight = base.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = midnight - timedelta(days=base.weekday()) + timedelta(hours=9, minutes=30)
        return monday + timedelta(minutes=offset_minutes)

    def _send(self, when, result):
        """Вызвать maybe_send в заданный момент. result — что вернёт actions.send
        (или исключение, если он его бросит)."""
        side = result if isinstance(result, BaseException) else None
        ret = None if side else result
        fake_dt = mock.Mock(wraps=datetime)
        fake_dt.now.return_value = when
        fake_dt.strptime = datetime.strptime
        with mock.patch.object(report, "build", return_value="отчёт"), \
             mock.patch("actions.send", side_effect=side, return_value=ret), \
             mock.patch.object(report, "datetime", fake_dt):
            return report.maybe_send(self.db)

    def test_ok_marks_sent(self):
        self.assertIsNone(self._send(self._when(), (True, "")))
        prefs = self.prefs()
        self.assertNotEqual(prefs["report_last"], "")       # отправлен - запомнили
        self.assertNotEqual(prefs["report_try"], "")        # и попытку тоже

    def test_failure_marks_attempt_but_not_sent(self):
        """Главное: при ошибке запоминается попытка, а не успех. Иначе - раз в минуту весь день."""
        when = self._when()
        err = self._send(when, (False, "Telegram недоступен"))
        self.assertIn("недоступен", err)
        prefs = self.prefs()
        self.assertEqual(prefs["report_last"], "")                       # не отправлен
        self.assertNotEqual(prefs["report_try"], "")                    # но попытку запомнили
        # и через минуту повторять не пойдёт
        self.assertIsNone(self._send(when + timedelta(minutes=1), (False, "again")))
        # а через полчаса - повторим
        self.assertIsNone(self._send(when + timedelta(minutes=report.RETRY_MIN + 1), (True, "")))
        self.assertNotEqual(self.prefs()["report_last"], "")

    def test_send_raising_is_not_a_crash(self):
        """Telegram не ответил - фон не должен на этом падать."""
        err = self._send(self._when(), OSError("соединение разорвано"))
        self.assertIn("разорвано", err)
        self.assertNotEqual(self.prefs()["report_try"], "")
