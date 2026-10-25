"""Publication multi-plateformes. Une plateforme en panne n'empêche pas les autres."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("newsbot.publish")


def _hashtags(script, extra=()):
    tags = [t.strip("# ").replace(" ", "") for t in script.get("hashtags", [])]
    return " ".join(f"#{t}" for t in [*extra, *tags] if t)


def _question(script):
    q = next((g.get("big") for g in script.get("segments", []) if g.get("scene") == "question"), None)
    return f"💬 {q} Tell us in the comments!" if q else ""


def youtube_text(script, short=True):
    lines = [_question(script), script.get("description", ""), "",
             "Sources: " + ", ".join(script.get("sources", []))]
    lines += [f"• {u}" for u in script.get("source_urls", [])[:6]]
    lines += ["", "AI-assisted video, cross-checked against multiple news outlets. Photos: Pixabay.",
              _hashtags(script, ["Shorts"] if short else [])]
    return "\n".join(lines)


def social_caption(script):
    tags = script.get("hashtags", [])[:4]
    return "\n\n".join(p for p in [
        script.get("title", ""),                      # hook line shown before "more"
        _question(script),
        script.get("description", ""),
        "Sources: " + ", ".join(script.get("sources", [])) + " · AI-assisted · Photos: Pixabay",
        _hashtags({"hashtags": tags}, ["worldnews"]),
    ] if p)


def publish_short(cfg, db, story_id: str, video: Path, script: dict) -> dict:
    results = {}
    if cfg.get("dry_run"):
        log.info("dry_run: not publishing (%s)", video)
        return {"dry_run": True}
    plats = cfg["platforms"]
    jobs = []
    from ..pipeline import connected_platforms
    ready = connected_platforms(cfg)
    score = (db.conn.execute("SELECT score FROM stories WHERE id=?", (story_id,)).fetchone() or [0])[0]
    if "instagram" in ready and not db.already_posted(story_id, "instagram") \
            and not db.instagram_ok(cfg, score):
        log.info("Instagram: skipped (daily cap / spacing / score %s) — keeping only the strongest Reels", score)
        ready = [p for p in ready if p != "instagram"]
    if "youtube" in ready and db.youtube_room(cfg) <= 0:
        log.info("YouTube daily upload limit reached: this video goes to the other platforms only")
        ready = [p for p in ready if p != "youtube"]
    if "youtube" in ready:
        from . import youtube
        jobs.append(("youtube", lambda: youtube.upload(
            cfg, video, script["title"], youtube_text(script), script.get("hashtags", []))))
    if "instagram" in ready:
        from . import instagram
        jobs.append(("instagram", lambda: instagram.upload(cfg, video, social_caption(script))))
    if "tiktok" in ready:
        from . import tiktok
        jobs.append(("tiktok", lambda: tiktok.upload(cfg, video, social_caption(script))))
    for name, job in jobs:
        if db.already_posted(story_id, name):
            continue
        try:
            rid, url = job()
            db.record_post(story_id, name, rid, url)
            results[name] = url or rid
        except Exception as exc:
            log.error("%s: failed — %s", name, exc)
            db.record_post(story_id, name, status="failed", error=str(exc)[:500])
            results[name] = f"ERROR: {exc}"
    return results
