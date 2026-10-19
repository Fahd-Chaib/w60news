"""Collecte des news depuis les flux RSS configurés."""
from __future__ import annotations

import calendar
import hashlib
import html
import logging
import re
import time

import feedparser
import requests

log = logging.getLogger("newsbot.fetch")
UA = "Mozilla/5.0 (NewsBot RSS reader)"
TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str, limit: int = 600) -> str:
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _ts(entry) -> float:
    for key in ("published_parsed", "updated_parsed"):
        st = entry.get(key)
        if st:
            return float(calendar.timegm(st))
    return time.time()


def fetch_all(cfg, db) -> int:
    """Lit tous les flux, stocke les nouveaux articles. Retourne le nombre de nouveaux."""
    new = 0
    for src in cfg["sources"]:
        try:
            resp = requests.get(src["url"], headers={"User-Agent": UA}, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except Exception as exc:  # un flux mort ne doit pas tout bloquer
            log.warning("Flux ignoré %s : %s", src["name"], exc)
            continue
        for e in feed.entries[:60]:
            url = e.get("link") or ""
            title = _clean(e.get("title", ""), 300)
            if not url or not title:
                continue
            item = {
                "id": hashlib.sha1(url.encode()).hexdigest()[:16],
                "source": src["name"],
                "title": title,
                "summary": _clean(e.get("summary", "") or e.get("description", "")),
                "url": url,
                "published": min(_ts(e), time.time()),
            }
            if db.add_item(item):
                new += 1
        log.info("%s : %d articles lus", src["name"], len(feed.entries))
    return new
