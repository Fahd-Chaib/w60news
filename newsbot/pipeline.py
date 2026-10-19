"""Orchestration : collecte → sélection → script → voix → rendu → publication."""
from __future__ import annotations

import fcntl
import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path

from . import curate, fetch, tts, visuals, writer
from .config import DATA
from .db import DB
from .publish import publish_short
from .render import render_story

log = logging.getLogger("newsbot")


def connected_platforms(cfg) -> list[str]:
    from .config import env
    plats, out = cfg["platforms"], []
    if plats.get("youtube", {}).get("enabled") and env("YOUTUBE_TOKEN_JSON"):
        out.append("youtube")
    if plats.get("instagram", {}).get("enabled") and env("INSTAGRAM_ACCESS_TOKEN") and env("INSTAGRAM_USER_ID"):
        out.append("instagram")
    if plats.get("tiktok", {}).get("enabled") and env("TIKTOK_TOKEN_JSON"):
        out.append("tiktok")
    return out


class RunLock:
    """Empêche deux passages simultanés si un rendu dure plus longtemps que l'intervalle cron."""

    def __enter__(self):
        self.f = open(DATA / ".lock", "w")
        try:
            fcntl.flock(self.f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Un passage est déjà en cours — on saute celui-ci.")
        return self

    def __exit__(self, *exc):
        fcntl.flock(self.f, fcntl.LOCK_UN)
        self.f.close()


def _pick_format(cfg, story, n_today):
    if cfg["formats"]["mode"] == "mixed":
        return "mixed"
    if cfg["formats"]["mode"] == "auto":
        fmt = story.get("best_format", "motion")
    else:
        rot = cfg["formats"]["rotation"]
        fmt = rot[n_today % len(rot)]
    return fmt if fmt in ("mixed", "characters", "motion", "slides") else "mixed"


def produce(cfg, story: dict, fmt: str) -> tuple[Path, dict, Path]:
    folder = DATA / "stories" / datetime.now().strftime("%Y-%m-%d") / story["id"]
    folder.mkdir(parents=True, exist_ok=True)
    script = writer.write_script(cfg, story, fmt)
    script["headline"] = story["headline"]
    (folder / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=1), "utf-8")
    tts.synthesize(cfg, script["segments"], folder)
    images = visuals.fetch_images(script.get("image_queries", []), folder, "portrait")
    out = folder / "short.mp4"
    t0 = time.time()
    render_story(cfg, script, folder, images, out, fmt)
    log.info("Rendered %s in %.0f s → %s", fmt, time.time() - t0, out)
    return folder, script, out


def run(cfg):
    sel = cfg["selection"]
    hour = datetime.now().hour
    q0, q1 = sel.get("quiet_hours") or [None, None]
    if q0 is not None and q0 <= hour < q1:
        log.info("Heures calmes (%sh-%sh) : rien à faire.", q0, q1)
        return
    from .config import env
    if not any(env(p["key_env"]) for p in cfg.get_path("llm.providers", [])):
        log.warning("Setup not finished: add GROQ_API_KEY (or CEREBRAS_API_KEY) to the repository "
                    "secrets. Skipping this run.")
        return
    if not cfg.get("dry_run") and not connected_platforms(cfg):
        log.warning("No platform connected yet (YouTube / Instagram / TikTok secrets missing). "
                    "Skipping the scheduled run — use the 'preview' mode to test without publishing.")
        return
    with RunLock():
        db = DB()
        db.prune()
        n_new = fetch.fetch_all(cfg, db)
        log.info("%d nouvelles dépêches", n_new)
        if n_new == 0:
            log.info("No new wire items since last run: skipping the LLM call.")
            return
        done_today = db.count_published_today()
        room = min(sel["max_videos_per_run"], sel["max_videos_per_day"] - done_today)
        if room <= 0:
            log.info("Quota du jour atteint (%d vidéos).", done_today)
            return
        stories = curate.select_stories(cfg, db)
        if not stories:
            log.info("Rien d'assez croustillant pour l'instant.")
            return
        made = 0
        for story in stories:
            if made >= room:
                break
            if db.story_exists(story["id"], sel["dedup_hours"]):
                continue
            fmt = _pick_format(cfg, story, done_today + made)
            meta = {k: story.get(k) for k in ("category", "grave", "sources", "score")}
            meta["item_ids"] = [it["id"] for it in story["items"]]
            try:
                folder, script, video = produce(cfg, story, fmt)
                meta["script"] = {k: v for k, v in script.items() if k != "source_urls"}
                db.add_story(story["id"], story["headline"], story["topic_key"], story["score"],
                             fmt, folder, meta)
                db.set_story_status(story["id"], "produced")
                res = publish_short(cfg, db, story["id"], video, script)
                ok = res.get("dry_run") or any(not str(v).startswith("ERROR") for v in res.values())
                db.set_story_status(story["id"], "published" if ok else "failed")
                log.info("✔ %s → %s", story["headline"], res)
                made += 1
            except Exception as exc:
                log.exception("Sujet abandonné (%s) : %s", story.get("headline"), exc)
                db.add_story(story["id"], story["headline"], story["topic_key"], story.get("score", 0),
                             fmt, "", {**meta, "error": str(exc)[:300]})
                db.set_story_status(story["id"], "failed")
        _cleanup()


def _cleanup(keep_days=3):
    root = DATA / "stories"
    if not root.exists():
        return
    for d in root.iterdir():
        try:
            age = (datetime.now() - datetime.strptime(d.name, "%Y-%m-%d")).days
        except ValueError:
            continue
        if age > keep_days:
            shutil.rmtree(d, ignore_errors=True)
