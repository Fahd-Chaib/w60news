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
        for r in self.conn.execute("SELECT meta FROM stories WHERE created>=?", (since,)):
            try:
                ids.update(json.loads(r["meta"] or "{}").get("item_ids", []))
            except json.JSONDecodeError:
                pass
        return ids

    def story_exists(self, story_id: str, hours: float) -> bool:
        since = time.time() - hours * 3600
        r = self.conn.execute("SELECT 1 FROM stories WHERE id=? AND created>=?", (story_id, since)).fetchone()
        return r is not None

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

    def already_posted(self, story_id, platform) -> bool:
        r = self.conn.execute(
            "SELECT 1 FROM posts WHERE story_id=? AND platform=? AND status='ok'",
            (story_id, platform)).fetchone()
        return r is not None

    def prune(self, days=3):
        cutoff = (datetime.now() - timedelta(days=days)).timestamp()
        self.conn.execute("DELETE FROM items WHERE fetched < ?", (cutoff,))
        self.conn.commit()
