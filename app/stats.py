#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Статистика по сообщениям — для раздела «Статистика» и недельного отчёта."""

from collections import Counter
from datetime import datetime

import catcher
import rules

TS = "%Y-%m-%d %H:%M:%S"


def stats(conn, days, src=""):
    """Кто больше пишет, самые шумные чаты, по источникам, активность день×час."""
    prefs = rules.get_prefs(conn)
    names, rs, mre = prefs["source_names"], rules.load(conn, prefs), rules.mention_re(prefs["mentions"])
    since = catcher.msk_time(days * 24) if days else ""
    total, mentions = 0, 0
    senders, chats, by_src = Counter(), Counter(), Counter()
    heat, srcs, meta_of = [[0] * 24 for _ in range(7)], {}, {}
    for app, site, chat, sender, at, text in conn.execute(
            "SELECT app, COALESCE(site, ''), chat, sender, received_at, message FROM messages "
            "WHERE received_at >= ?", (since,)):
        s = meta_of.get((app, site)) or meta_of.setdefault((app, site), rules.source_of(app, site, names))
        srcs[s["key"]] = {k: s[k] for k in ("key", "name", "ico", "rank")}
        if src and s["key"] != src:
            continue
        total += 1
        by_src[s["key"]] += 1
        senders[(s["key"], sender or "")] += 1
        chats[(s["key"], chat or "")] += 1
        if mre and mre.search(text or ""):
            mentions += 1
        try:
            t = datetime.strptime(at, TS)
            heat[t.weekday()][t.hour] += 1
        except (TypeError, ValueError):
            pass
    by_hour = [sum(heat[d][h] for d in range(7)) for h in range(24)]
    busiest = max(range(24), key=lambda h: by_hour[h]) if total else None
    busy_day = max(range(7), key=lambda d: sum(heat[d])) if total else None
    return {
        "days": days, "src": src, "total": total, "chats": len(chats), "senders": len(senders),
        "mentions": mentions,
        "busiest_hour": busiest, "busiest_n": by_hour[busiest] if busiest is not None else 0,
        "busiest_day": busy_day,
        "by_source": [dict(srcs[k], n=n) for k, n in by_src.most_common()],
        "top_senders": [dict(sender=k[1], n=n, src_name=srcs[k[0]]["name"], ico=srcs[k[0]]["ico"])
                        for k, n in senders.most_common(10)],
        "top_chats": [dict(src=k[0], chat=k[1], n=n, src_name=srcs[k[0]]["name"],
                           ico=srcs[k[0]]["ico"], hidden=not rs.visible(k[0], k[1], None, None))
                      for k, n in chats.most_common(10)],
        "heat": heat,
        "sources": sorted(srcs.values(), key=lambda s: (s["rank"], s["name"])),
    }
