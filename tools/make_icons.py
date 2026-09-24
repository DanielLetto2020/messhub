#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Иконка программы: доска с тремя колонками карточек. Рисуется кодом, без графических
библиотек, чтобы её можно было пересобрать где угодно.

    python3 tools/make_icons.py        # → packaging/icons/messhub.svg, messhub-<N>.png, messhub.ico

PNG — для Linux (иконки приложения и окна), ICO (PNG внутри, 16…256) — для Windows.
"""

import os
import struct
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "packaging", "icons")
SIZES = (16, 24, 32, 48, 64, 128, 256)

# фигуры в координатах 64×64: (вид, x, y, w, h, радиус, цвет RGBA)
BG = (27, 36, 51, 255)
SHAPES = [
    ("rect", 2, 2, 60, 60, 14, BG),
    ("circle", 13, 12.5, 3.2, 0, 0, (62, 201, 143, 255)),                 # точка «на связи»
    ("rect", 20, 10.5, 22, 4, 2, (91, 155, 255, 230)),                    # шапка
    ("rect", 9, 20, 13, 10, 3, (91, 155, 255, 255)),                      # колонка 1
    ("rect", 9, 33, 13, 8, 3, (201, 212, 232, 235)),
    ("rect", 9, 44, 13, 8, 3, (201, 212, 232, 170)),
    ("rect", 25.5, 20, 13, 8, 3, (201, 212, 232, 235)),                   # колонка 2
    ("rect", 25.5, 31, 13, 13, 3, (245, 159, 69, 255)),
    ("rect", 42, 20, 13, 8, 3, (201, 212, 232, 235)),                     # колонка 3
    ("rect", 42, 31, 13, 8, 3, (201, 212, 232, 170)),
]


def svg():
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="256" height="256">']
    for kind, x, y, w, h, r, (cr, cg, cb, ca) in SHAPES:
        fill = f'fill="#{cr:02x}{cg:02x}{cb:02x}"' + (f' fill-opacity="{ca / 255:.2f}"' if ca < 255 else "")
        if kind == "rect":
            parts.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" {fill}/>')
        else:
            parts.append(f'  <circle cx="{x}" cy="{y}" r="{w}" {fill}/>')
    parts.append("</svg>\n")
    return "\n".join(parts)


def inside(kind, x, y, w, h, r, px, py):
    if kind == "circle":
        return (px - x) ** 2 + (py - y) ** 2 <= w * w
    if not (x <= px <= x + w and y <= py <= y + h):
        return False
    cx = min(max(px, x + r), x + w - r)
    cy = min(max(py, y + r), y + h - r)
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def raster(size, ss=4):
    """Сглаживание — суперсэмплингом ss×ss на пиксель, наложение слоёв по альфе."""
    import avatars
    rows = []
    k = 64 / size
    for j in range(size):
        row = bytearray()
        for i in range(size):
            acc = [0.0, 0.0, 0.0, 0.0]
            for sj in range(ss):
                for si in range(ss):
                    px, py = (i + (si + .5) / ss) * k, (j + (sj + .5) / ss) * k
                    r = g = b = a = 0.0
                    for kind, x, y, w, h, rad, (cr, cg, cb, ca) in SHAPES:
                        if inside(kind, x, y, w, h, rad, px, py):
                            al = ca / 255
                            r, g, b = r * (1 - al) + cr * al, g * (1 - al) + cg * al, b * (1 - al) + cb * al
                            a = a + al * (1 - a)
                    acc[0] += r
                    acc[1] += g
                    acc[2] += b
                    acc[3] += a
            n = ss * ss
            a = acc[3] / n
            # цвет храним «не умноженным» на альфу, как принято в PNG
            row += bytes((min(255, int(acc[0] / n / a)) if a else 0, min(255, int(acc[1] / n / a)) if a else 0,
                          min(255, int(acc[2] / n / a)) if a else 0, int(round(a * 255))))
        rows.append(bytes(row))
    return avatars.png_bytes(size, size, rows, True)


def ico(pngs):
    """ICO с PNG внутри (поддерживается с Windows Vista)."""
    head = struct.pack("<HHH", 0, 1, len(pngs))
    offset, dirs, data = 6 + 16 * len(pngs), b"", b""
    for size, png in pngs:
        s = 0 if size >= 256 else size
        dirs += struct.pack("<BBBBHHII", s, s, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return head + dirs + data


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "messhub.svg"), "w", encoding="utf-8") as f:
        f.write(svg())
    pngs = []
    for size in SIZES:
        png = raster(size)
        pngs.append((size, png))
        with open(os.path.join(OUT, f"messhub-{size}.png"), "wb") as f:
            f.write(png)
    with open(os.path.join(OUT, "messhub.ico"), "wb") as f:
        f.write(ico([p for p in pngs if p[0] in (16, 24, 32, 48, 64, 128, 256)]))
    print("готово:", OUT)


if __name__ == "__main__":
    main()
