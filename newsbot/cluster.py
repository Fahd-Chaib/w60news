"""Local grouping of headlines that describe the same event (no LLM, no tokens spent).

Only groups covered by ≥ N different outlets are sent to the LLM. This both enforces
cross-checking and keeps each run well inside the free-tier token budget.
"""
from __future__ import annotations

import re
from collections import defaultdict

STOP = set("""
a an the and or but if of to in on at by for with from into over under after before about as is are was
were be been being has have had do does did will would can could should may might must not no nor so than
too very just also more most much many some any all each every other such own same new says said say
amid after against between during without within across up down out off again further then once here
there when where why how what which who whom this that these those its it's it their them they his her
he she we you our your my me us i live update updates latest news report reports reported video watch
year years day days week weeks month months today yesterday tomorrow first last two three one man woman
people world us uk get gets got make makes made take takes took could calls call set sets back still
""".split())

WORD = re.compile(r"[A-Za-z][A-Za-z'\-]+|\d[\d,.]*%?")


def keywords(text: str) -> set[str]:
    out = set()
    for w in WORD.findall(text):
        lw = w.lower().strip("'-").removesuffix("'s")
        if lw in STOP or len(lw) < 3:
            continue
        if lw.endswith("s") and len(lw) > 4 and not lw.endswith("ss"):
            lw = lw[:-1]  # crude singular
        out.add(lw)
    return out


def _similar(a: dict, b: dict) -> bool:
    ka, kb = a["_title_kw"], b["_title_kw"]
    shared = ka & kb
    if len(shared) >= 3:
        return True
    full = a["_kw"] & b["_kw"]
    if len(shared) >= 2 and len(full) >= 4:
        return True
    smallest = min(len(a["_kw"]), len(b["_kw"])) or 1
    return len(full) >= 5 and len(full) / smallest >= 0.35


def group(items: list[dict], min_sources: int = 2) -> list[dict]:
    for it in items:
        it["_title_kw"] = keywords(it["title"])
        it["_kw"] = it["_title_kw"] | keywords(it.get("summary", "")[:300])
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i]["source"] != items[j]["source"] and _similar(items[i], items[j]):
                parent[find(i)] = find(j)

    buckets = defaultdict(list)
    for i, it in enumerate(items):
        buckets[find(i)].append(it)
    clusters = []
    for members in buckets.values():
        sources = sorted({m["source"] for m in members})
        if len(sources) < min_sources:
            continue
        members.sort(key=lambda m: -m["published"])
        clusters.append({"items": members, "sources": sources,
                         "latest": members[0]["published"]})
    clusters.sort(key=lambda c: (-len(c["sources"]), -c["latest"]))
    for n, c in enumerate(clusters):
        c["cid"] = f"c{n}"
    for it in items:
        it.pop("_title_kw", None)
        it.pop("_kw", None)
    return clusters
