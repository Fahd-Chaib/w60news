"""Royalty-free illustration photos (Pixabay, or Pexels if you have a key).
Never the news outlets' own photos. Without any key, videos use generated backgrounds."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from .config import env

log = logging.getLogger("newsbot.visuals")


def _pixabay(q: str, orientation: str, key: str) -> str | None:
    r = requests.get("https://pixabay.com/api/", timeout=20, params={
        "key": key, "q": q[:100], "image_type": "photo", "safesearch": "true", "per_page": 5,
        "orientation": "vertical" if orientation == "portrait" else "horizontal"})
    r.raise_for_status()
    hits = r.json().get("hits", [])
    if not hits and orientation == "portrait":  # fewer vertical photos: accept any orientation
        r = requests.get("https://pixabay.com/api/", timeout=20, params={
            "key": key, "q": q[:100], "image_type": "photo", "safesearch": "true", "per_page": 5})
        hits = r.json().get("hits", [])
    return hits[0].get("largeImageURL") if hits else None


def _pexels(q: str, orientation: str, key: str) -> str | None:
    r = requests.get("https://api.pexels.com/v1/search", timeout=20, headers={"Authorization": key},
                     params={"query": q, "orientation": orientation, "per_page": 3})
    r.raise_for_status()
    photos = r.json().get("photos", [])
    return (photos[0]["src"].get("large2x") or photos[0]["src"]["original"]) if photos else None


def fetch_images(queries: list[str], folder: Path, orientation: str = "portrait") -> list[str | None]:
    prefix = "img" if orientation == "portrait" else "land"
    providers = [(f, env(k)) for f, k in ((_pixabay, "PIXABAY_API_KEY"), (_pexels, "PEXELS_API_KEY")) if env(k)]
    out: list[str | None] = []
    for i, q in enumerate(queries):
        path = folder / f"{prefix}_{i}.jpg"
        if path.exists():
            out.append(str(path))
            continue
        url = None
        for find, key in providers:
            try:
                url = find(q, orientation, key)
                if url:
                    break
            except Exception as exc:
                log.warning("Image search '%s' failed: %s", q, exc)
        if not url:
            out.append(None)
            continue
        try:
            img = requests.get(url, timeout=30)
            img.raise_for_status()
            path.write_bytes(img.content)
            out.append(str(path))
        except Exception as exc:
            log.warning("Image download failed for '%s': %s", q, exc)
            out.append(None)
    return out
