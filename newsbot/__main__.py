"""Command line.

  python -m newsbot run            one run: news → videos → publishing (what GitHub Actions calls)
  python -m newsbot recap          today's long 16:9 recap on YouTube
  python -m newsbot demo           renders demo videos offline (no key needed)
  python -m newsbot preview        a full run WITHOUT publishing (quality check)
  python -m newsbot auth youtube   connect the YouTube channel (once, on your computer)
  python -m newsbot auth tiktok    connect the TikTok account (once, on your computer)
  python -m newsbot keygen         generate the STATE_KEY secret
  python -m newsbot status         what was published today
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import config
from .config import DATA


def main(argv=None):
    p = argparse.ArgumentParser(prog="newsbot")
    p.add_argument("command", choices=["run", "recap", "demo", "preview", "auth", "status", "keygen"])
    p.add_argument("target", nargs="?")
    p.add_argument("--config")
    args = p.parse_args(argv)

    cfg = config.load(args.config)
    (DATA / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(DATA / "logs" / "newsbot.log", encoding="utf-8")])

    if args.command == "run":
        from .pipeline import run
        run(cfg)
    elif args.command == "preview":
        from .pipeline import run
        cfg["dry_run"] = True
        cfg["selection"]["quiet_hours"] = [None, None]
        run(cfg)
    elif args.command == "recap":
        from .recap import build
        build(cfg)
    elif args.command == "demo":
        import os
        os.environ.setdefault("TTS_BACKEND", "silent")
        from .demo import run as demo
        for path in demo(cfg, landscape=True):
            print(path)
    elif args.command == "auth":
        if args.target == "youtube":
            from .publish.youtube import authorize
        elif args.target == "tiktok":
            from .publish.tiktok import authorize
        else:
            sys.exit("Usage: python -m newsbot auth youtube|tiktok "
                     "(Instagram: put the token in INSTAGRAM_ACCESS_TOKEN, see README)")
        authorize()
    elif args.command == "keygen":
        from .vault import keygen
        print("Add this as the GitHub secret STATE_KEY:\n" + keygen())
    elif args.command == "status":
        from .db import DB
        db = DB()
        rows = db.stories_today()
        print(f"{len(rows)} story(ies) today")
        for s in rows:
            posts = db.conn.execute("SELECT platform, status, url FROM posts WHERE story_id=?",
                                    (s["id"],)).fetchall()
            print(f"- [{s['status']}] {s['format']:<10} {s['score']:>3}  {s['headline']}")
            for pl in posts:
                print(f"     {pl['platform']:<10} {pl['status']:<6} {pl['url'] or ''}")


if __name__ == "__main__":
    main()
