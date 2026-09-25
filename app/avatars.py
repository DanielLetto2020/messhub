#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Аватары отправителей из самих уведомлений — без обращения к приложениям.

Уведомление часто несёт картинку (обычно аватар собеседника):
  hint "image-data" (или старые "image_data" / "icon_data") — структура
      (ширина, высота, шаг строки, есть альфа, бит на канал, каналов, байты),
      dbus-monitor печатает её так:
          string "image-data"
          variant             struct {
                int32 48
                int32 48
                int32 192
                boolean true
                int32 8
                int32 4
                array of bytes [
                   ff 00 00 ff ...
                ]
             }
  hint "image-path" — путь или file:// к картинке.

Картинка уменьшается до 48 px, кодируется в PNG (своим кодировщиком на zlib — без
внешних библиотек) и кладётся в ~/.cache/<APP_ID>/avatars/<sha1>.png; одинаковые
картинки не дублируются. В БД у сообщения хранится только имя файла.
"""

import hashlib
import os
import re
import struct
import zlib
from urllib.parse import unquote, urlparse

import paths

MAX_SIDE = 48
_RE_INT = re.compile(r"^\s*int32 (-?\d+)\s*$")
_RE_BOOL = re.compile(r"^\s*boolean (true|false)\s*$")
_RE_HEX = re.compile(r"^\s*((?:[0-9a-f]{2}\s*)+)$")
_RE_PATH = re.compile(r'variant\s+string "([^"]+)"')
IMAGE_KEYS = ('"image-data"', '"image_data"', '"icon_data"')


# ── PNG без внешних библиотек ───────────────────────────────────────────────

def png_bytes(width, height, rows, alpha):
    """rows — список bytes по строкам (RGB или RGBA, 8 бит на канал)."""
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6 if alpha else 2, 0, 0, 0)
    raw = b"".join(b"\x00" + r for r in rows)          # фильтр 0 у каждой строки
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _scaled_rows(data, w, h, stride, channels):
    """Строки картинки, уменьшенной до MAX_SIDE (ближайший сосед)."""
    scale = max(w, h) / MAX_SIDE if max(w, h) > MAX_SIDE else 1.0
    nw, nh = max(1, round(w / scale)), max(1, round(h / scale))
    rows = []
    for y in range(nh):
        sy = min(h - 1, int(y * scale))
        base = sy * stride
        row = bytearray()
        for x in range(nw):
            sx = min(w - 1, int(x * scale))
            row += data[base + sx * channels: base + sx * channels + channels]
        rows.append(bytes(row))
    return nw, nh, rows


# ── разбор вывода dbus-monitor ──────────────────────────────────────────────

def parse_image_data(lines):
    """Найти в строках блока структуру image-data → (w, h, stride, alpha, bits, ch, bytes)."""
    for i, line in enumerate(lines):
        if not any(k in line for k in IMAGE_KEYS):
            continue
        ints, alpha, data, j = [], None, bytearray(), i + 1
        while j < len(lines) and "array of bytes" not in lines[j]:
            m = _RE_INT.match(lines[j])
            if m:
                ints.append(int(m.group(1)))
            b = _RE_BOOL.match(lines[j])
            if b:
                alpha = b.group(1) == "true"
            j += 1
            if j - i > 12:          # структура короткая — дальше искать нечего
                break
        if j >= len(lines) or "array of bytes" not in lines[j] or len(ints) < 5 or alpha is None:
            continue
        j += 1
        while j < len(lines) and lines[j].strip() != "]":
            m = _RE_HEX.match(lines[j])
            if m:
                data += bytes.fromhex(m.group(1).replace(" ", ""))
            j += 1
        w, h, stride, bits, ch = ints[0], ints[1], ints[2], ints[3], ints[4]
        return w, h, stride, alpha, bits, ch, bytes(data)
    return None


def parse_image_path(lines):
    for i, line in enumerate(lines):
        if '"image-path"' in line or '"image_path"' in line:
            for nxt in lines[i + 1:i + 3]:
                m = _RE_PATH.search(nxt)
                if m:
                    return m.group(1)
    return None


# ── сохранение ──────────────────────────────────────────────────────────────

def _save(data, ext="png"):
    os.makedirs(paths.AVATAR_DIR, exist_ok=True)
    name = hashlib.sha1(data).hexdigest()[:20] + "." + ext
    path = os.path.join(paths.AVATAR_DIR, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)
    return name


def from_image_data(w, h, stride, alpha, bits, ch, data):
    if bits != 8 or ch not in (3, 4) or w <= 0 or h <= 0 or w > 4096 or h > 4096:
        return None
    if len(data) < stride * (h - 1) + w * ch:
        return None
    nw, nh, rows = _scaled_rows(data, w, h, stride, ch)
    return _save(png_bytes(nw, nh, rows, ch == 4))


def from_path(p):
    """image-path: локальный файл PNG/JPEG (не больше 2 МБ) копируем как есть —
    уменьшать без внешних библиотек не из чего, а браузер покажет и так."""
    if p.startswith("file://"):
        p = unquote(urlparse(p).path)
    if not p.startswith("/") or not os.path.isfile(p) or os.path.getsize(p) > 2 * 1024 * 1024:
        return None
    ext = os.path.splitext(p)[1].lower().lstrip(".")
    if ext not in ("png", "jpg", "jpeg"):
        return None
    with open(p, "rb") as f:
        return _save(f.read(), "jpg" if ext == "jpeg" else ext)


def extract(lines):
    """Аватар из блока dbus-monitor → имя файла в кэше или None. Ошибки глотаем:
    картинка — украшение, из-за неё запись уведомления падать не должна."""
    try:
        img = parse_image_data(lines)
        if img:
            return from_image_data(*img)
        p = parse_image_path(lines)
        return from_path(p) if p else None
    except (OSError, ValueError, IndexError):
        return None


_RE_NAME = re.compile(r"^[0-9a-f]{20}\.(png|jpg)$")


def file_for(name):
    """Путь к файлу аватара по имени (для сервера) или None, если имя подозрительное."""
    if not _RE_NAME.match(name or ""):
        return None
    p = os.path.join(paths.AVATAR_DIR, name)
    return p if os.path.isfile(p) else None
