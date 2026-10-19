"""Offline demo: renders the 3 formats with a made-up story (no API key needed).

    python -m newsbot demo
"""
from __future__ import annotations

import json
import logging

from .config import DATA
from .render import render_story
from .render.intro import add_intro_segment
from .tts import synthesize

log = logging.getLogger("newsbot.demo")

DEMO = {
    "title": "Oceans just hit a record temperature — here's why it matters",
    "category": "climate",
    "sources": ["Outlet A", "Outlet B", "Outlet C"],
    "description": "Rendering demo.",
    "hashtags": ["news", "climate"],
    "image_queries": [],
    "grave": False,
}

SEGMENTS = {
    "mixed": [
        {"speaker": "a", "scene": "desk", "big": "Record broken",
         "text": "Nina, the world's oceans just broke a heat record. Again?"},
        {"speaker": "b", "scene": "photo", "big": "Hottest ever", "image": 0,
         "text": "Yes Sam. They have never been this warm since records began."},
        {"speaker": "b", "scene": "stat", "big": "21.1 °C", "label": "average sea surface temperature",
         "text": "The average surface temperature hit twenty-one point one degrees."},
        {"speaker": "a", "scene": "claim", "source": "Outlet A",
         "big": "Scientists say the heat is building faster than expected.",
         "text": "And according to Outlet A, scientists say it is building faster than expected."},
        {"speaker": "b", "scene": "versus", "big": "Then vs now",
         "left": {"label": "average in 2000", "value": "20.4 °C"},
         "right": {"label": "average this year", "value": "21.1 °C"},
         "text": "Compare: about twenty point four degrees in 2000, twenty-one point one today."},
        {"speaker": "a", "scene": "points", "big": "Why it matters",
         "points": ["Coral reefs bleaching", "Stronger storms", "Fish moving north"],
         "text": "So why does it matter? Coral bleaching, stronger storms, and fish moving north."},
        {"speaker": "b", "scene": "timeline", "big": "What comes next",
         "steps": [{"when": "Next month", "what": "New satellite readings"},
                   {"when": "November", "what": "Climate summit talks"},
                   {"when": "2027", "what": "Updated global report"}],
         "text": "Next: new readings next month, summit talks in November, a new report in 2027."},
        {"speaker": "a", "scene": "question", "big": "Should this be the top priority at the summit?",
         "options": ["Yes, absolutely", "No, other issues first", "Not sure yet"],
         "text": "Should this be the top priority at the summit? Tell us in the comments."},
    ],
    "motion": [
        {"speaker": "narrator", "kind": "headline", "big": "Record broken",
         "text": "The world's oceans have never been this warm since records began."},
        {"speaker": "narrator", "kind": "stat", "big": "21.1 °C", "label": "average sea surface temperature",
         "text": "The average sea surface temperature reached twenty-one point one degrees."},
        {"speaker": "narrator", "kind": "headline", "big": "Coral at risk",
         "text": "Why it matters: coral reefs are bleaching in several regions."},
        {"speaker": "narrator", "kind": "headline", "big": "What's next",
         "text": "Scientists are waiting for next month's data. We'll keep you posted."},
    ],
    "characters": [
        {"speaker": "a", "kind": "headline", "big": "Record broken",
         "text": "Nina, the oceans just broke a heat record. Again?"},
        {"speaker": "b", "kind": "stat", "big": "21.1 °C",
         "text": "Yes, Sam. Twenty-one point one degrees on average at the surface. Never seen before."},
        {"speaker": "a", "kind": "headline", "big": "So what?",
         "text": "Okay, but what does that actually change for us?"},
        {"speaker": "b", "kind": "headline", "big": "Coral at risk",
         "text": "Coral reefs bleach, and storms pick up more energy from warm water."},
        {"speaker": "a", "kind": "headline", "big": "What's next",
         "text": "So we watch the next readings closely. What do you think?"},
    ],
    "slides": [
        {"speaker": "narrator", "kind": "title", "big": "Oceans are overheating",
         "text": "The oceans are overheating. Here's what you need to know in one minute."},
        {"speaker": "narrator", "kind": "stat", "big": "21.1 °C", "label": "average ocean surface temperature",
         "text": "The ocean surface hit twenty-one point one degrees on average."},
        {"speaker": "narrator", "kind": "points", "big": "The effects",
         "points": ["Coral reefs bleaching", "Stronger storms", "Fish moving north"],
         "text": "Three effects to remember: coral bleaching, stronger storms, and fish moving north."},
        {"speaker": "narrator", "kind": "headline", "big": "What happens next?",
         "text": "Next step: next month's readings. We'll keep you posted."},
    ],
}


def run(cfg, formats=("mixed",), landscape=False):
    out_dir = DATA / "demo"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for fmt in formats:
        folder = out_dir / fmt
        folder.mkdir(exist_ok=True)
        script = {**DEMO, "format": fmt, "segments": [dict(s) for s in SEGMENTS[fmt]]}
        add_intro_segment(cfg, script, "demo")
        (folder / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=1), "utf-8")
        synthesize(cfg, script["segments"], folder)
        out = out_dir / f"demo_{fmt}.mp4"
        render_story(cfg, script, folder, [], out)
        log.info("Demo %s → %s", fmt, out)
        results.append(out)
    if landscape:
        folder = out_dir / "mixed"
        if not (folder / "timeline.json").exists():
            folder.mkdir(exist_ok=True)
            synthesize(cfg, SEGMENTS["mixed"], folder)
        out = out_dir / "demo_recap_16x9.mp4"
        script = {**DEMO, "format": "motion", "segments": SEGMENTS["mixed"]}
        render_story(cfg, script, folder, [], out, "motion", W=1920, H=1080)
        results.append(out)
    return results
