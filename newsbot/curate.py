"""Picks the "juicy" stories among cross-checked clusters (free open-source LLM)."""
from __future__ import annotations

import hashlib
import logging

from .cluster import group
from .llm import ask_json

log = logging.getLogger("newsbot.curate")

SYSTEM = """You are the editor-in-chief of "{channel}", a global English-language short-video news \
channel (YouTube Shorts, Reels, TikTok). From clusters of wire headlines, pick the stories that will \
hook a worldwide audience AND are journalistically solid.

Rules:
- Each cluster lists headlines from different outlets. Only keep a cluster if its headlines really \
describe the SAME specific event (set same_event=false otherwise).
- "Juicy" = surprising, high-stakes, widely shared, unusual, a twist, a record, or a concrete impact \
on people's lives. Skip dull institutional or purely procedural news.
- Skip stories already covered (list given) unless there is a genuinely major new development.
- Mark "grave": true for anything involving deaths, injuries, disasters, attacks, war or abuse.
- Our own audience data (views per video) is given below: score higher the kinds of stories that \
actually get watched, lower the ones that don't (unless the story is truly huge).
Answer ONLY with JSON."""

PROMPT = """What our audience watches (average views per video, by category, last days):
{perf}

Already covered recently:
{covered}

Clusters (id | outlets | headlines):
{clusters}

Return:
{{"stories": [{{"cid": "cluster id", "same_event": true,
  "headline": "catchy factual headline, max 70 chars",
  "topic_key": "3-5 stable keywords identifying the event",
  "score": 0-100, "category": "politics|conflict|economy|tech|science|climate|society|weird|sport|culture",
  "grave": false, "best_format": "characters|motion|slides"}}]}}
Max 6 stories, best first. best_format: characters = two anchors discuss it (great for explaining \
and for debates), motion = very visual or breaking story, slides = numbers-driven story."""


DEFAULT_PERF = ("conflict / Middle East and human tragedies perform best, then big US politics and "
                "weird/viral stories; science, health, tech and climate get few views")


def audience_summary(db) -> str:
    """Average views per category from the latest stats snapshot (fed back into story selection)."""
    import json
    import statistics
    try:
        snap = {}
        for r in db.conn.execute("SELECT platform, data FROM stats ORDER BY collected"):
            snap[r["platform"]] = json.loads(r["data"])
        by_cat = {}
        for p in db.conn.execute("SELECT p.platform, p.remote_id, s.meta FROM posts p JOIN stories s "
                                 "ON s.id = p.story_id WHERE p.status='ok'"):
            v = (snap.get(p["platform"], {}).get(p["remote_id"]) or {}).get("views")
            cat = json.loads(p["meta"] or "{}").get("category")
            if v is not None and cat:
                by_cat.setdefault(cat, []).append(v)
        if sum(len(v) for v in by_cat.values()) < 10:
            return DEFAULT_PERF
        ranked = sorted(by_cat.items(), key=lambda kv: -statistics.mean(kv[1]))
        return ", ".join(f"{c}: {statistics.mean(v):.0f} ({len(v)} videos)" for c, v in ranked)
    except Exception:
        return DEFAULT_PERF


def select_stories(cfg, db) -> list[dict]:
    sel = cfg["selection"]
    items = db.recent_items(sel["lookback_hours"])
    clusters = group(items, sel["min_sources"])
    covered_ids = db.covered_item_ids(sel["dedup_hours"])
    fresh = []
    for c in clusters:
        ids = {it["id"] for it in c["items"]}
        if len(ids & covered_ids) >= max(1, len(ids) // 2):
            continue  # same event already turned into a video
        fresh.append(c)
    fresh = fresh[:25]
    if not fresh:
        log.info("No new cross-checked cluster (%d clusters total).", len(clusters))
        return []
    lines = []
    for c in fresh:
        heads = " || ".join(it["title"][:140] for it in c["items"][:3])
        lines.append(f"{c['cid']} | {', '.join(c['sources'][:5])} | {heads}")
    covered = db.recent_story_headlines(sel["dedup_hours"]) or ["(none)"]
    data = ask_json(
        cfg, SYSTEM.format(channel=cfg["channel"]["name"]),
        PROMPT.format(perf=audience_summary(db), covered="\n".join(f"- {c}" for c in covered[-30:]), clusters="\n".join(lines)),
        max_tokens=2500,
    )
    by_cid = {c["cid"]: c for c in fresh}
    kept = []
    for st in data.get("stories", []):
        c = by_cid.get(st.get("cid"))
        if not c or not st.get("same_event", True):
            continue
        if st.get("score", 0) < sel["min_score"]:
            continue
        st["items"] = c["items"][:6]
        st["sources"] = c["sources"]
        st["id"] = hashlib.sha1(st.get("topic_key", st["headline"]).lower().encode()).hexdigest()[:12]
        kept.append(st)
    log.info("%d story(ies) kept out of %d clusters sent", len(kept), len(fresh))
    return kept
