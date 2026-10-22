"""Temporary public hosting of a video file, needed by Instagram (it pulls the video from a URL).

Uses a GitHub release named `media` on this public repository: the video is uploaded as a
release asset, its public download URL is handed to Instagram, and the asset is deleted
right after Instagram has fetched it. Runs inside GitHub Actions (GITHUB_TOKEN).
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from ..config import env

log = logging.getLogger("newsbot.hosting")
API = "https://api.github.com"
TAG = "media"


def _h():
    tok = env("GITHUB_TOKEN") or env("GH_TOKEN")
    if not tok:
        raise RuntimeError("GITHUB_TOKEN missing: temporary video hosting only works inside GitHub Actions")
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}


def _repo():
    repo = env("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY missing")
    return repo


def _release():
    repo = _repo()
    r = requests.get(f"{API}/repos/{repo}/releases/tags/{TAG}", headers=_h(), timeout=30)
    if r.status_code == 200:
        return r.json()
    r = requests.post(f"{API}/repos/{repo}/releases", headers=_h(), timeout=30, json={
        "tag_name": TAG, "name": "Temporary media (auto-deleted)", "prerelease": True,
        "body": "Videos are parked here for a few minutes so Instagram can fetch them, then deleted."})
    r.raise_for_status()
    return r.json()


def public_url(video: Path) -> tuple[str, int]:
    rel = _release()
    # tidy up: remove assets older than 2 hours (left over from an interrupted run)
    for a in rel.get("assets", []):
        try:
            age = time.time() - time.mktime(time.strptime(a["created_at"], "%Y-%m-%dT%H:%M:%SZ"))
            if age > 7200:
                cleanup(a["id"])
        except Exception:
            pass
    name = f"{int(time.time())}_{video.parent.name}.mp4"
    up = rel["upload_url"].split("{")[0]
    with open(video, "rb") as f:
        r = requests.post(up, params={"name": name}, data=f, timeout=600,
                          headers={**_h(), "Content-Type": "video/mp4"})
    r.raise_for_status()
    asset = r.json()
    url = asset["browser_download_url"]
    log.info("Video hosted temporarily: %s", url)
    return url, asset["id"]


def cleanup(asset_id):
    if not asset_id:
        return
    try:
        requests.delete(f"{API}/repos/{_repo()}/releases/assets/{asset_id}", headers=_h(), timeout=30)
    except Exception as exc:
        log.warning("Could not delete temporary asset %s: %s", asset_id, exc)
