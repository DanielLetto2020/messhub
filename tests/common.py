"""Общее для тестов: всё приложение — во временной папке, наружу ничего не уходит.
Импортировать ПЕРВЫМ в каждом тесте (пути программы вычисляются при импорте paths)."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="express-msgs-test-")
os.environ["EXPRESS_MSGS_HOME"] = TMP
os.environ["EXPRESS_MSGS_EXPORT_DIR"] = TMP
os.environ["EXPRESS_MSGS_FORWARD_CFG"] = os.path.join(TMP, "fwd.json")
os.environ["EXPRESS_MSGS_TG_API"] = "http://127.0.0.1:9"      # никуда не достучится

import catcher  # noqa: E402


def new_db(name="t.db"):
    path = os.path.join(TMP, name)
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)
    catcher.init_db(path).close()
    return path


def put(conn, app, summary, body, site=None, **kw):
    """Записать уведомление так же, как это делает сборщик. → rec с id."""
    chat, sender, msg, s = catcher.parse_fields(app, summary, body)
    rec = dict(app=app, chat=chat, sender=sender, is_bot=catcher.guess_is_bot(sender), message=msg,
               notification_id=0, urgency=1, has_media=0, event_ts=1.7e9,
               event_iso="2026-09-24T12:00:00", raw_summary=summary, raw_body=body,
               site=s if site is None else site, avatar=None)
    rec.update(kw)
    rec["id"] = catcher.insert(conn, rec)
    return rec
