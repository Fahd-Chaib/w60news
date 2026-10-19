"""Video scripts written by the open-source LLM, strictly from the cross-checked wire items."""
from __future__ import annotations

from .llm import ask_json

SYSTEM = """You write scripts for "{channel}", a global English-language short news channel \
(9:16 vertical videos). House style: fun but reliable, and educational — always explain WHY it \
matters and the context a global viewer needs.
Hard rules:
- FACTUAL: use ONLY facts present in the wire items provided. Never invent numbers, names, places, \
dates or quotes. If outlets disagree, say so ("according to the BBC…").
- Attribute sensitive claims to the outlet.
- Rewrite everything in your own words: never copy a sentence from the wire items.
- Hook in the first 2 seconds (question, striking number, contrast).
- Short spoken sentences, simple international English (many viewers are non-native).
- If the story is grave (deaths, war, disaster, abuse): sober, respectful tone, no jokes, no puns.
- End with an open line (what to watch next, or a question to viewers). Never say "subscribe".
Answer ONLY with JSON."""

import re

FORMAT_GUIDE = {
    "mixed": """FORMAT: a fast-paced edit. {a} (anchor) and {b} (anchor) co-host and banter; EVERY line \
gets its own on-screen shot, so the video keeps changing. 8 to 11 lines, 1-2 short sentences each, \
speaker = "a" for {a} or "b" for {b} (alternate often; they react to each other: "Wait, really?", \
"Exactly.", "Here's the thing…"). They never mock victims or real people.

For each line pick a "scene" (the shot shown while it is spoken):
- "desk": both anchors at the news desk. Use for the opening hook, reactions and banter. big = 1-4 words.
- "photo": full-screen picture + 1-4 punchy words in "big". Set "image" (index into image_queries).
- "stat": ONE number from the wire items. big = the number exactly as written (e.g. "1,200", "$4.5bn", \
"38%"), label = what it measures.
- "points": 2-3 very short key points in "points", big = short heading (e.g. "WHY IT MATTERS").
- "claim": what an outlet reports. source = outlet name from the wire items, big = the claim in your own \
words (max 18 words). Never a fake direct quote.
- "versus": a comparison. big = heading, left = {{"label","value"}}, right = {{"label","value"}} \
(before/after, country A vs B, expected vs actual) — only with facts from the wire items.
- "timeline": 2-4 steps, steps = [{{"when","what"}}] (dates or "Monday", "Next week"…).
- "question": audience interaction near the end. big = the question, options = 2-3 short answers. \
NOT allowed if the story is grave.

Editing rules: use at least 5 different scenes; never the same scene twice in a row; at most 3 desk \
shots; open with desk or photo; include a stat or versus whenever the wire items contain a number; \
end with a question (or, if grave, a sober desk line about what happens next).""",
    "characters": """FORMAT: two cartoon TV news anchors. {a} and {b} co-host the news desk.
{a} sets up the story and asks the questions viewers have; {b} brings context and explains the "why" \
(swap roles freely). 6 to 10 lines, 1-2 sentences each, natural back-and-forth banter.
speaker = "a" for {a}, "b" for {b}. They never mock victims or real people.""",
    "motion": """FORMAT: single voice-over (speaker = "narrator"), 5 to 8 segments. Each segment has \
"big": 1 to 4 punchy words shown huge on screen (e.g. "48 HOURS", "RECORD BROKEN").""",
    "slides": """FORMAT: infographic with single voice-over (speaker = "narrator"), 5 to 7 slides. \
Use kind="stat" when there is a number (big = the number exactly as in the wire, label = what it \
measures), kind="points" for 2-3 short key points, kind="title" for the opening slide.""",
}

SEGMENT_SCHEMA = {
    "mixed": """{{"speaker": "a|b", "text": "what is said", "scene": "desk|photo|stat|points|claim|versus|timeline|question",
      "big": "...", "label": "...", "points": ["..."], "source": "...",
      "left": {{"label": "...", "value": "..."}}, "right": {{"label": "...", "value": "..."}},
      "steps": [{{"when": "...", "what": "..."}}], "options": ["..."], "image": 0}}
    (only fill the fields the chosen scene needs)""",
    "default": """{{"speaker": "...", "text": "what is said",
      "kind": "title|stat|points|headline",
      "big": "punchy words / number",
      "label": "short caption (optional)",
      "points": ["only for kind=points"],
      "image": 0}}""",
}

PROMPT = """Story: {headline}
Category: {category} — grave: {grave}
Target length: {seconds} seconds of speech (~{words} words in total).

{guide}

Wire items (the ONLY source of truth):
{items}

Return JSON:
{{
  "title": "video title, max 80 chars, catchy but not misleading",
  "description": "2-3 factual sentences for the video description",
  "hashtags": ["5 to 8 relevant hashtags, no #"],
  "image_queries": ["3 to 5 generic stock-photo searches (places, objects, moods — never a named real person)"],
  "segments": [
    {schema}
  ]
}}
"image" = index into image_queries illustrating that segment."""

HAS_DIGIT = re.compile(r"\d")


def plan_scenes(segs: list[dict], grave: bool, sources: list[str], wire_text: str) -> list[dict]:
    """Checks the LLM's editing choices and fixes them so every video stays varied and safe."""
    for s in segs:
        sc = s.get("scene")
        ok = {
            "desk": True,
            "photo": True,
            "stat": bool(s.get("big")) and bool(HAS_DIGIT.search(str(s.get("big")))),
            "points": len(s.get("points") or []) >= 2,
            "claim": bool(s.get("big")),
            "versus": isinstance(s.get("left"), dict) and isinstance(s.get("right"), dict)
                      and s["left"].get("value") and s["right"].get("value"),
            "timeline": len(s.get("steps") or []) >= 2,
            "question": bool(s.get("big")) and not grave,
        }.get(sc, False)
        if not ok:
            s["scene"] = "photo"
        if s["scene"] == "stat":
            # the number on screen must appear in the wire items (no invented figures)
            digits = re.sub(r"[^\d]", "", str(s["big"]))
            if digits and digits not in re.sub(r"[^\d]", " ", wire_text).replace(" ", "") \
                    and digits not in re.sub(r"[^\d ]", "", wire_text):
                s["scene"] = "photo"
        if s["scene"] == "claim":
            src = s.get("source") or ""
            s["source"] = next((x for x in sources if x.lower() in src.lower() or src.lower() in x.lower()),
                               sources[0] if sources else "reports")
    # never the same shot twice in a row, desk ≤ 3
    alt = {"desk": "photo", "photo": "desk"}
    desk_count = 0
    for n, s in enumerate(segs):
        if n and s["scene"] == segs[n - 1]["scene"]:
            s["scene"] = alt.get(s["scene"], "photo" if segs[n - 1]["scene"] != "photo" else "desk")
        if s["scene"] == "desk":
            desk_count += 1
            if desk_count > 3:
                s["scene"] = "photo" if (n == 0 or segs[n - 1]["scene"] != "photo") else "points" \
                    if len(s.get("points") or []) >= 2 else "photo"
    if segs and segs[0]["scene"] not in ("desk", "photo", "stat"):
        segs[0]["scene"] = "desk"
    if not any(s["scene"] == "desk" for s in segs):
        segs[0]["scene"] = "desk"  # viewers always meet the anchors
    last = segs[-1]
    if not grave and not any(s["scene"] == "question" for s in segs) and last["text"].strip().endswith("?"):
        last["scene"], last["big"] = "question", last.get("big") or last["text"]
        if len(segs) > 1 and segs[-2]["scene"] == "question":
            segs[-2]["scene"] = "photo"
    return segs


def write_script(cfg, story: dict, fmt: str) -> dict:
    ch = cfg["characters"]
    seconds = cfg["formats"]["target_seconds"]
    guide = FORMAT_GUIDE[fmt].format(a=ch["a"]["name"], b=ch["b"]["name"])
    items = "\n\n".join(f"[{it['source']}] {it['title']}\n{it['summary'][:400]}" for it in story["items"])
    prompt = PROMPT.format(headline=story["headline"], category=story.get("category", ""),
                           grave="yes" if story.get("grave") else "no", seconds=seconds,
                           words=int(seconds * 2.6), guide=guide, items=items,
                           schema=SEGMENT_SCHEMA.get(fmt, SEGMENT_SCHEMA["default"]))
    for attempt in range(3):  # free models sometimes return a truncated script: just ask again
        script = ask_json(cfg, SYSTEM.format(channel=cfg["channel"]["name"]), prompt, max_tokens=5000)
        segs = [s for s in script.get("segments", []) if str(s.get("text", "")).strip()]
        if len(segs) >= 4:
            break
    else:
        raise ValueError("script too short")
    for s in segs:
        if fmt in ("characters", "mixed") and s.get("speaker") not in ("a", "b"):
            s["speaker"] = "a"
        if fmt not in ("characters", "mixed"):
            s["speaker"] = "narrator"
    if fmt == "mixed":
        segs = plan_scenes(segs, bool(story.get("grave")), story["sources"], items)
    script["segments"] = segs
    script["format"] = fmt
    script["sources"] = story["sources"]
    script["source_urls"] = [it["url"] for it in story["items"]]
    script["category"] = story.get("category", "")
    script["grave"] = bool(story.get("grave"))
    return script
