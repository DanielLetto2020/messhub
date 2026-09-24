"""Проверка новой версии: сравнение номеров и ответ /api/update без настоящей сети."""
import json
import time
import unittest
from unittest import mock

import common  # noqa: F401
import updates
import version


class UpdatesTest(unittest.TestCase):
    def setUp(self):
        updates._state.update(at=0.0, latest="", url="", error="", busy=False)

    def test_compare(self):
        self.assertEqual(updates.parse("v1.0.12"), (1, 0, 12))
        self.assertEqual(updates.parse("1.0.3+unknown"), (1, 0, 3))
        self.assertTrue(updates.newer("1.0.12", "1.0.9"))            # числа, а не строки: 12 > 9
        self.assertFalse(updates.newer("1.0.3", "1.0.3"))
        self.assertFalse(updates.newer("", "1.0.3"))

    def test_fetch_in_background_and_disabled(self):
        fake = mock.MagicMock()
        fake.__enter__.return_value.read.return_value = json.dumps(
            {"tag_name": "v9.9.9", "html_url": "https://example.com/r"}).encode()
        with mock.patch.object(updates.urllib.request, "urlopen", return_value=fake) as op:
            updates.status(True)                                        # первый раз — только запуск запроса
            for _ in range(50):
                if updates._state["latest"]:
                    break
                time.sleep(0.02)
            st = updates.status(True)
            self.assertEqual((st["latest"], st["newer"], st["url"]), ("9.9.9", True, "https://example.com/r"))
            self.assertEqual(op.call_count, 1)                          # второй раз — из памяти, без сети
            off = updates.status(False)
            self.assertNotIn("latest", off)
            self.assertEqual(op.call_count, 1)                          # выключено — запросов нет
        self.assertEqual(st["current"], version.__version__)


if __name__ == "__main__":
    unittest.main()
