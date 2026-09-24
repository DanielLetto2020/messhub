import os
import struct
import zlib
import unittest

import common  # noqa: F401  — первым: временные пути
import avatars
import catcher

HEADER = ("method call time=1790000000.5 sender=:1.46 -> destination=org.freedesktop.Notifications "
          "serial=7 path=/org/freedesktop/Notifications; interface=org.freedesktop.Notifications; member=Notify")


def block(app, summary, body, entry=None, image=False):
    lines = [f'   string "{app}"', "   uint32 0", '   string ""', f'   string "{summary}"',
             f'   string "{body}"', "   array [", "   ]", "   array ["]
    if entry:
        lines += ["      dict entry(", '         string "desktop-entry"', f'         variant             string "{entry}"', "      )"]
    lines += ["      dict entry(", '         string "urgency"', "         variant             byte 1", "      )"]
    if image:
        lines += ["      dict entry(", '         string "image-data"', "         variant             struct {",
                  "               int32 2", "               int32 2", "               int32 8",
                  "               boolean true", "               int32 8", "               int32 4",
                  "               array of bytes [", "                  ff 00 00 ff 00 ff 00 ff",
                  "                  00 00 ff ff 10 20 30 ff", "               ]", "            }", "      )"]
    lines += ["   ]", "   int32 -1"]
    return HEADER, lines


class ParseTest(unittest.TestCase):
    def test_group_chat(self):
        r = catcher.parse_message_block(*block("eXpress", "Команда", "Иван Петров: Созвон в 15:00", entry="express"))
        self.assertEqual((r["app"], r["chat"], r["sender"], r["message"]), ("express", "Команда", "Иван Петров", "Созвон в 15:00"))
        self.assertEqual(r["urgency"], 1)

    def test_personal_chat(self):
        r = catcher.parse_message_block(*block("eXpress", "Анна", "Привет"))
        self.assertEqual((r["chat"], r["sender"], r["message"]), ("Анна", "Анна", "Привет"))

    def test_colon_in_private_text_is_not_sender(self):
        for body in ("Скинешь макет? Прошлая версия: https://example.com/v3", "Готово? Да: выкладываю",
                     "Смотри https://example.com/a: там всё", "Длинная фраза из шести слов тут: и текст"):
            self.assertEqual(catcher.split_sender("Марина", body)[1], "Марина", body)
        self.assertEqual(catcher.split_sender("Команда", "Иван Петров (ИТ): готово")[1], "Иван Петров (ИТ)")

    def test_browser_site(self):
        chat, sender, msg, site = catcher.parse_fields("yandex-browser", "Чат двора", "web.max.ru\n\nСосед: Воды не будет")
        self.assertEqual((site, sender, msg), ("web.max.ru", "Сосед", "Воды не будет"))
        self.assertEqual(catcher.parse_fields("firefox", "Чат", "Привет\n\nvk.com")[3], "vk.com")

    def test_mail(self):
        chat, sender, msg, site = catcher.parse_fields("org.gnome.Evolution", "Новое письмо",
                                                      "У вас письмо.\nОт: Бухгалтерия\nТема: Зарплата")
        self.assertEqual((sender, msg), ("Бухгалтерия", "Зарплата"))

    def test_telegram_bots_skipped(self):
        self.assertTrue(catcher.telegram_should_skip({"app": "telegram-desktop", "sender": "NewsBot", "chat": "NewsBot"}))
        self.assertFalse(catcher.telegram_should_skip({"app": "telegram-desktop", "sender": "Мама", "chat": "Семья"}))
        self.assertFalse(catcher.telegram_should_skip({"app": "eXpress", "sender": "CI Bot", "chat": "x"}))

    def test_avatar_from_image_data(self):
        r = catcher.parse_message_block(*block("eXpress", "Анна", "Привет", image=True))
        self.assertTrue(r["avatar"] and r["avatar"].endswith(".png"))
        with open(os.path.join(avatars.paths.AVATAR_DIR, r["avatar"]), "rb") as f:
            png = f.read()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        w, h = struct.unpack(">II", png[16:24])
        self.assertEqual((w, h), (2, 2))
        idat = png[png.index(b"IDAT") + 4:png.index(b"IEND") - 8]
        self.assertEqual(len(zlib.decompress(idat)), h * (1 + w * 4))
        self.assertIsNotNone(avatars.file_for(r["avatar"]))
        self.assertIsNone(avatars.file_for("../../etc/passwd"))

    def test_avatar_downscale(self):
        w = h = 200
        name = avatars.from_image_data(w, h, w * 3, False, 8, 3, bytes(w * h * 3))
        with open(os.path.join(avatars.paths.AVATAR_DIR, name), "rb") as f:
            png = f.read()
        self.assertEqual(struct.unpack(">II", png[16:24]), (avatars.MAX_SIDE, avatars.MAX_SIDE))


if __name__ == "__main__":
    unittest.main()
