"""Команды страницы, которые окно получает от доски (app/pagecmd.py).

Раньше разбор команд жил в widget.py и winwidget.py - в обоих нужен графический стек,
поэтому на другой системе их не импортируешь и проверить их было нечем. Здесь проверяется
разбор на любой машине: главное, чтобы окна на Linux, Windows и Mac понимали команды
одинаково (они и разбираются одним и тем же модулем)."""
import unittest

import common  # noqa: F401 — первым: пути программы вычисляются при импорте paths
import pagecmd


class ParseTest(unittest.TestCase):
    def test_verbs_without_argument(self):
        for cmd, verb in (("move", "move"), ("geom-end", "geom-end"), ("search-close", "search-close"),
                          ("assistant", "assistant"), ("close", "close")):
            self.assertEqual(pagecmd.parse(cmd)[0], verb, cmd)

    def test_numbers(self):
        self.assertEqual(pagecmd.parse("geom:12.5,-3"), ("geom", (12.5, -3.0)))
        self.assertEqual(pagecmd.parse("geom:-4,0"), ("geom", (-4.0, 0.0)))
        self.assertEqual(pagecmd.parse("opacity:0.72")[1], 0.72)
        self.assertEqual(pagecmd.parse("message:42"), ("message", 42))

    def test_bad_numbers_are_not_commands(self):
        """Мусор в команде - это не команда, а не ошибка: окно просто ничего не делает."""
        for cmd in ("geom:abc", "geom:1", "geom:1,2,3", "opacity:не-число", "opacity:",
                    "message:abc", "message:", ""):
            self.assertEqual(pagecmd.parse(cmd), (None, None), cmd)

    def test_json_arguments(self):
        cmd = 'open:{"app":"telegram-desktop_telegram-desktop","site":""}'
        self.assertEqual(pagecmd.parse(cmd)[0], "open")
        self.assertEqual(pagecmd.parse(cmd)[1]["app"], "telegram-desktop_telegram-desktop")
        self.assertEqual(pagecmd.parse('search:{"q":"привет"}')[1], {"q": "привет"})
        self.assertEqual(pagecmd.parse('strip:{"on":true}')[1], {"on": True})
        self.assertEqual(pagecmd.parse('share:{"on":false}')[1], {"on": False})
        # не-JSON и не-объект - тоже не команда (окно не должно падать на мусоре)
        for cmd in ("open:не-json", "search:[1,2]", "strip:5"):
            self.assertEqual(pagecmd.parse(cmd), (None, None), cmd)

    def test_edges(self):
        for edge in pagecmd.EDGES:
            self.assertEqual(pagecmd.parse(f"resize:{edge}"), ("resize", edge))
        self.assertEqual(pagecmd.parse("resize:q"), (None, None))       # не край

    def test_lock_and_settings(self):
        self.assertEqual(pagecmd.locked_on("lock:1"), True)
        self.assertEqual(pagecmd.locked_on("lock:0"), False)
        self.assertIsNone(pagecmd.locked_on("lock:2"))
        self.assertIsNone(pagecmd.locked_on("close"))
        self.assertEqual(pagecmd.parse("settings"), ("settings", ""))
        self.assertEqual(pagecmd.parse("settings:profiles"), ("settings", "profiles"))

    def test_unknown_command(self):
        for cmd in ("что-то", "http://example.com", "  ", "0"):
            self.assertEqual(pagecmd.parse(cmd), (None, None), cmd)


class ResizeTest(unittest.TestCase):
    """Арифметика перетаскивания за край: размер не меньше минимума, тянуть за север и
    запад двигает и сам угол окна (иначе окно «уезжает» из-под курсора)."""

    def geo(self, x=100, y=200, w=800, h=300):
        return (x, y, w, h)

    def test_south_east(self):
        self.assertEqual(pagecmd.resize_geom("se", self.geo(), 50, 30, 400, 200),
                         (100, 200, 850, 330))

    def test_north_moves_top_left(self):
        # тянем северный край вверх: верх уезжает, нижний остаётся на месте
        self.assertEqual(pagecmd.resize_geom("n", self.geo(), 0, -30, 400, 200),
                         (100, 170, 800, 330))
        # западный край влево: левый уезжает, правый остаётся
        self.assertEqual(pagecmd.resize_geom("w", self.geo(), -40, 0, 400, 200),
                         (60, 200, 840, 300))
        self.assertEqual(pagecmd.resize_geom("nw", self.geo(), -40, -30, 400, 200),
                         (60, 170, 840, 330))

    def test_minimum_size(self):
        # тянем угол внутрь окна (вправо-вниз) - размер упирается в минимум,
        # а противоположный угол остаётся на месте, иначе окно уехало бы из-под курсора
        x, y, w, h = pagecmd.resize_geom("nw", self.geo(), 5000, 5000, 400, 200)
        self.assertEqual((w, h), (400, 200))
        self.assertEqual((x + w, y + h), (900, 500))          # правый нижний угол на месте
        x, y, w, h = pagecmd.resize_geom("se", self.geo(), -5000, -5000, 400, 200)
        self.assertEqual((x, y, w, h), (100, 200, 400, 200))   # левый верхний на месте
        x, y, w, h = pagecmd.resize_geom("se", self.geo(), 5000, 5000, 400, 200)
        self.assertEqual((w, h), (5800, 5300))                 # тянем наружу - растёт

    def test_not_an_edge(self):
        self.assertIsNone(pagecmd.resize_geom("q", self.geo(), 1, 1, 400, 200))
        self.assertIsNone(pagecmd.resize_geom("se", None, 1, 1, 400, 200))

    def test_fix_points(self):
        self.assertEqual(pagecmd.fix_points("se"), (False, False))
        self.assertEqual(pagecmd.fix_points("nw"), (True, True))
        self.assertEqual(pagecmd.fix_points("n"), (False, True))
        self.assertIsNone(pagecmd.fix_points("q"))


class DragTest(unittest.TestCase):
    def test_is_drag(self):
        self.assertTrue(pagecmd.is_drag("move"))
        self.assertTrue(pagecmd.is_drag("resize:e"))
        for cmd in ("search:{}", "close", "assistant", "lock:1", "geom-end"):
            self.assertFalse(pagecmd.is_drag(cmd), cmd)
