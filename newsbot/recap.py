"""Daily long recap (16:9) for YouTube: today's stories stitched together, with chapters."""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from . import tts, visuals
from .config import DATA
from .db import DB
from .render import render_story
from .render.common import draw_lines, fit_text, font, generated_backdrop, rgb, text_size, wrap

log = logging.getLogger("newsbot.recap")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]


def _date_fr(d=None):
    d = d or datetime.now()
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def _duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip() or 0)


def _card(cfg, W, H, title, subtitle, lines=()):
    th = cfg["theme"]
    img = generated_backdrop(W, H, 5, rgb(th["dark"]), (4, 8, 18), rgb(th["primary"]))
    d = ImageDraw.Draw(img, "RGBA")
    u = min(W, H) / 1080
    d.rectangle((0, 0, int(24 * u), H), fill=rgb(th["primary"]))
    fs = font("Bold", int(40 * u))
    d.text((int(110 * u), int(H * .2)), subtitle.upper(), font=fs, fill=rgb(th["accent"]))
    f, ls, s = fit_text(title.upper(), "Bold", int(W * .8), int(H * .3), int(150 * u), int(60 * u))
    draw_lines(d, ls, f, s, int(110 * u), int(H * .2 + 70 * u), (255, 255, 255))
    y = H * .2 + 70 * u + len(ls) * s * 1.08 + 40 * u
    fl = font("Medium", int(40 * u))
    for ln in lines[:4]:
        txt = wrap(ln, fl, int(W * .78))[0]
        d.ellipse((110 * u, y + 18 * u, 126 * u, y + 34 * u), fill=rgb(th["primary"]))
        d.text((150 * u, y), txt, font=fl, fill=(235, 235, 235))
        y += 62 * u
    return img.convert("RGB")


def _still_clip(img: Image.Image, seconds: float, out: Path):
    png = out.with_suffix(".png")
    img.save(png)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(png),
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{seconds}",
                    "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", str(out)], check=True)
    return out


def _ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60:02d}:{sec % 60:02d}"


def build(cfg, publish=True):
    rc = cfg["recap"]
    db = DB()
    status = None if cfg.get("dry_run") else "published"
    stories = [s for s in db.stories_today(status) if s["status"] != "failed" and "script" in (s["meta"] or "")]
    stories = sorted(stories, key=lambda s: -s["score"])[: rc["max_stories"]]
    if len(stories) < rc["min_stories"]:
        log.info("Recap: only %d story(ies) today, no recap.", len(stories))
        return None
    stories = sorted(stories, key=lambda s: s["created"])
    W, H = 1920, 1080
    out_dir = DATA / "recaps" / datetime.now().strftime("%Y-%m-%d")
    out_dir.mkdir(parents=True, exist_ok=True)
    date = _date_fr()
    headlines = [s["headline"] for s in stories]

    parts, chapters, t = [], [], 0.0
    intro = _still_clip(_card(cfg, W, H, "Today's world recap", date, headlines), 4, out_dir / "00_intro.mp4")
    parts.append(intro)
    chapters.append((0, "Intro"))
    t += _duration(intro)
    for i, s in enumerate(stories, 1):
        script = json.loads(s["meta"])["script"]
        # the recap has its own intro card: drop the spoken "Welcome" line and rebuild the voice track
        script["segments"] = [g for g in script["segments"] if g.get("scene") != "intro"]
        src = Path(s["folder"]) if s["folder"] else None
        folder = out_dir / s["id"]
        folder.mkdir(parents=True, exist_ok=True)
        if src and src.exists():
            for img in src.glob("land_*.jpg"):
                (folder / img.name).write_bytes(img.read_bytes())
        tts.synthesize(cfg, script["segments"], folder)
        imgs = visuals.fetch_images(script.get("image_queries", []), folder, "landscape")
        part = out_dir / f"{i:02d}_story.mp4"
        render_story(cfg, script, folder, imgs, part, "motion", W=W, H=H, end_card=False)
        parts.append(part)
        chapters.append((t, s["headline"]))
        t += _duration(part)
    outro = _still_clip(_card(cfg, W, H, cfg["channel"]["name"], "See you tomorrow",
                              [cfg["channel"].get("handle", "")]), 4, out_dir / "99_outro.mp4")
    parts.append(outro)

    lst = out_dir / "parts.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in parts))
    final = out_dir / "recap.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
                    "-movflags", "+faststart", str(final)], check=True, cwd=out_dir)

    thumb = out_dir / "thumb.jpg"
    _card(cfg, 1280, 720, "The day in news", date, headlines[:3]).save(thumb, quality=90)

    title = f"The world today — {date} | {cfg['channel']['name']} daily recap"
    sources = sorted({src for s in stories for src in json.loads(s["meta"]).get("sources", [])})
    desc = "\n".join(
        [f"The {len(stories)} stories that shaped the day, explained in a few minutes.", ""]
        + [f"{_ts(c[0])} {c[1]}" for c in chapters]
        + ["", "Sources: " + ", ".join(sources),
           "AI-assisted video, cross-checked against multiple news outlets. Photos: Pixabay.", "#news #worldnews #dailynews"])
    (out_dir / "description.txt").write_text(desc, "utf-8")
    log.info("Recap ready: %s (%.0f s)", final, _duration(final))

    if publish and not cfg.get("dry_run") and cfg["platforms"]["youtube"].get("enabled") \
            and cfg["platforms"]["youtube"].get("upload_recap"):
        from .publish import youtube
        vid, url = youtube.upload(cfg, final, title, desc, ["news", "world news", "daily recap", "international"], thumb)
        db.record_post(f"recap-{datetime.now():%Y%m%d}", "youtube", vid, url)
        log.info("Recap published: %s", url)
    return final
