"""Collects public performance numbers for every published video (YouTube + Instagram)
and stores them in the bot's memory (table `stats`) for analysis."""
from __future__ import annotations

import json
import logging
import time

import requests

from .db import DB

log = logging.getLogger("newsbot.stats")


def _youtube(cfg, ids):
    from .publish.youtube import _service
    yt = _service()
    out = {}
    for i in range(0, len(ids), 50):
        resp = yt.videos().list(part="statistics,snippet,contentDetails", id=",".join(ids[i:i + 50])).execute()
        for v in resp.get("items", []):
            st = v.get("statistics", {})
            out[v["id"]] = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                            "comments": int(st.get("commentCount", 0)),
                            "duration": v.get("contentDetails", {}).get("duration"),
                            "published": v["snippet"].get("publishedAt")}
    try:  # channel totals
        ch = yt.channels().list(part="statistics", mine=True).execute()["items"][0]["statistics"]
        out["_channel"] = ch
    except Exception as exc:
        log.warning("channel stats unavailable: %s", exc)
    return out


def _instagram(cfg, ids):
    from .publish.instagram import _token
    ig = cfg["platforms"]["instagram"]
    base = f"https://{ig['graph_host']}/{ig['api_version']}"
    tok = _token(cfg)
    out, insights_ok = {}, True
    for mid in ids:
        rec = {}
        try:
            r = requests.get(f"{base}/{mid}", timeout=30, params={
                "fields": "like_count,comments_count,timestamp,permalink", "access_token": tok}).json()
            rec.update({"likes": r.get("like_count"), "comments": r.get("comments_count"),
                        "published": r.get("timestamp")})
            if insights_ok:
                ins = requests.get(f"{base}/{mid}/insights", timeout=30, params={
                    "metric": "views,reach,saved,shares,total_interactions,ig_reels_avg_watch_time",
                    "access_token": tok}).json()
                if "error" in ins:
                    log.warning("Instagram insights unavailable: %s", ins["error"].get("message"))
                    insights_ok = False
                else:
                    for m in ins.get("data", []):
                        rec[m["name"]] = (m.get("values") or [{}])[0].get("value")
        except Exception as exc:
            rec["error"] = str(exc)[:200]
        out[mid] = rec
    try:
        me = requests.get(f"{base}/me", timeout=30, params={
            "fields": "followers_count,media_count,username", "access_token": tok}).json()
        out["_account"] = me
    except Exception:
        pass
    return out


def collect(cfg):
    db = DB()
    db.conn.execute("CREATE TABLE IF NOT EXISTS stats (collected REAL, platform TEXT, data TEXT)")
    rows = db.conn.execute("SELECT story_id, platform, remote_id FROM posts WHERE status='ok'").fetchall()
    yt_ids = [r["remote_id"] for r in rows if r["platform"] == "youtube" and r["remote_id"]]
    ig_ids = [r["remote_id"] for r in rows if r["platform"] == "instagram" and r["remote_id"]]
    now = time.time()
    for name, fn, ids in (("youtube", _youtube, yt_ids), ("instagram", _instagram, ig_ids)):
        if not ids:
            continue
        try:
            data = fn(cfg, ids)
            db.conn.execute("INSERT INTO stats VALUES (?,?,?)", (now, name, json.dumps(data)))
            db.conn.commit()
            log.info("%s: stats for %d videos", name, len(ids))
        except Exception as exc:
            log.exception("%s stats failed: %s", name, exc)
