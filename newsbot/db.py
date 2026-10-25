"""Mémoire du bot (SQLite) : articles vus, sujets traités, publications."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta

from .config import DATA

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,           -- hash de l'URL
    source TEXT, title TEXT, summary TEXT, url TEXT,
    published REAL, fetched REAL
);
CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    created REAL,
    headline TEXT,
    topic_key TEXT,
    score INTEGER,
    format TEXT,
    status TEXT,                  -- selected | produced | published | failed
    folder TEXT,
    meta TEXT                     -- JSON
);
CREATE TABLE IF NOT EXISTS posts (
    story_id TEXT, platform TEXT, remote_id TEXT, url TEXT,
    posted REAL, status TEXT, error TEXT,
    PRIMARY KEY (story_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_items_fetched ON items(fetched);
CREATE INDEX IF NOT EXISTS idx_stories_created ON stories(created);
"""


MAX_ATTEMPTS = 3  # a story that fails is retried on the next runs, up to this many times


class DB:
    def __init__(self, path=None):
        self.conn = sqlite3.connect(path or DATA / "newsbot.sqlite")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ── articles ──
    def add_item(self, item: dict) -> bool:
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO items VALUES (?,?,?,?,?,?,?)",
            (item["id"], item["source"], item["title"], item["summary"],
             item["url"], item["published"], time.time()),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def recent_items(self, hours: float) -> list[dict]:
        since = time.time() - hours * 3600
        rows = self.conn.execute(
            "SELECT * FROM items WHERE published >= ? ORDER BY published DESC", (since,)
        ).fetchall()
        return [dict(r) for r in rows]

    def items_by_ids(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        q = ",".join("?" * len(ids))
        return [dict(r) for r in self.conn.execute(f"SELECT * FROM items WHERE id IN ({q})", ids)]

    # ── sujets ──
    def add_story(self, story_id, headline, topic_key, score, fmt, folder, meta):
        self.conn.execute(
            "INSERT OR REPLACE INTO stories VALUES (?,?,?,?,?,?,?,?,?)",
            (story_id, time.time(), headline, topic_key, score, fmt, "selected",
             str(folder), json.dumps(meta, ensure_ascii=False)),
        )
        self.conn.commit()

    def update_meta(self, story_id, meta: dict):
        self.conn.execute("UPDATE stories SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), story_id))
        self.conn.commit()

    def set_story_status(self, story_id, status):
        self.conn.execute("UPDATE stories SET status=? WHERE id=?", (status, story_id))
        self.conn.commit()

    def recent_story_headlines(self, hours: float) -> list[str]:
        since = time.time() - hours * 3600
        rows = self.conn.execute(
            "SELECT headline, topic_key FROM stories WHERE created>=? AND status!='failed'", (since,)
        ).fetchall()
        return [f"{r['headline']} [{r['topic_key']}]" for r in rows]

    def covered_item_ids(self, hours: float) -> set[str]:
        since = time.time() - hours * 3600
        ids = set()
        for r in self.conn.execute("SELECT status, meta FROM stories WHERE created>=?", (since,)):
            try:
                meta = json.loads(r["meta"] or "{}")
                if r["status"] == "failed" and meta.get("attempts", 1) < MAX_ATTEMPTS:
                    continue  # failed story that may still be retried
                ids.update(meta.get("item_ids", []))
            except json.JSONDecodeError:
                pass
        return ids

    def story_exists(self, story_id: str, hours: float) -> bool:
        """True if the story was already done (or failed too many times) — i.e. don't try it again."""
        since = time.time() - hours * 3600
        r = self.conn.execute("SELECT status, meta FROM stories WHERE id=? AND created>=?",
                              (story_id, since)).fetchone()
        if r is None:
            return False
        if r["status"] != "failed":
            return True
        return self.attempts(story_id) >= MAX_ATTEMPTS

    def attempts(self, story_id: str) -> int:
        r = self.conn.execute("SELECT meta FROM stories WHERE id=?", (story_id,)).fetchone()
        if r is None:
            return 0
        try:
            return int(json.loads(r["meta"] or "{}").get("attempts", 1))
        except (ValueError, json.JSONDecodeError):
            return 1

    def stories_today(self, status: str | None = None) -> list[dict]:
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        sql = "SELECT * FROM stories WHERE created>=?"
        args = [start]
        if status:
            sql += " AND status=?"
            args.append(status)
        rows = self.conn.execute(sql + " ORDER BY created", args).fetchall()
        return [dict(r) for r in rows]

    def count_published_today(self) -> int:
        return len(self.stories_today("published"))

    # ── publications ──
    def record_post(self, story_id, platform, remote_id=None, url=None, status="ok", error=None):
        self.conn.execute(
            "INSERT OR REPLACE INTO posts VALUES (?,?,?,?,?,?,?)",
            (story_id, platform, remote_id, url, time.time(), status, error),
        )
        self.conn.commit()

    def count_posts(self, platform, hours=24, status="ok") -> int:
        since = time.time() - hours * 3600
        return self.conn.execute("SELECT COUNT(*) FROM posts WHERE platform=? AND status=? AND posted>=?",
                                 (platform, status, since)).fetchone()[0]

    def recent_error(self, platform, needle, hours=6) -> bool:
        since = time.time() - hours * 3600
        return self.conn.execute("SELECT 1 FROM posts WHERE platform=? AND status='failed' AND posted>=? "
                                 "AND error LIKE ?", (platform, since, f"%{needle}%")).fetchone() is not None

    def last_post_time(self, platform) -> float:
        r = self.conn.execute("SELECT MAX(posted) FROM posts WHERE platform=? AND status='ok'",
                              (platform,)).fetchone()
        return r[0] or 0.0

    def instagram_ok(self, cfg, score) -> bool:
        ig = cfg["platforms"]["instagram"]
        if (score or 0) < ig.get("min_score", 0):
            return False
        if self.count_posts("instagram", 24) >= ig.get("max_per_day", 99):
            return False
        return time.time() - self.last_post_time("instagram") >= ig.get("min_gap_minutes", 0) * 60

    def youtube_room(self, cfg, for_recap=False) -> int:
        """Uploads still allowed on YouTube in the last 24 h. New channels have a daily cap;
        one slot is always kept for the evening recap."""
        yt = cfg["platforms"]["youtube"]
        cap = int(yt.get("max_uploads_per_day", 10))
        if not for_recap and cfg["recap"].get("enabled") and yt.get("upload_recap"):
            cap -= 1
        if not for_recap and self.recent_error("youtube", "uploadLimitExceeded", hours=4):
            return 0  # YouTube already said "limit reached": wait before trying again
        return max(0, cap - self.count_posts("youtube", 24))

    def already_posted(self, story_id, platform) -> bool:
        r = self.conn.execute(
            "SELECT 1 FROM posts WHERE story_id=? AND platform=? AND status='ok'",
            (story_id, platform)).fetchone()
        return r is not None

    def prune(self, days=3):
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        self.conn.execute("DELETE FROM items WHERE fetched < ?", (cutoff,))
        self.conn.commit()
