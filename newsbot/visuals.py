"""Photos d'illustration libres de droits (Pexels). Jamais les photos des médias sources."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from .config import env

log = logging.getLogger("newsbot.visuals")


def fetch_images(queries: list[str], folder: Path, orientation: str = "portrait") -> list[str | None]:
    prefix = "img" if orientation == "portrait" else "land"
    key = env("PEXELS_API_KEY")
    out: list[str | None] = []
    for i, q in enumerate(queries):
        path = folder / f"{prefix}_{i}.jpg"
        if path.exists():
            out.append(str(path))
            continue
        if not key:
            out.append(None)
            continue
        try:
            r = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": q, "orientation": orientation, "per_page": 3},
                headers={"Authorization": key}, timeout=20,
            )
            r.raise_for_status()
            photos = r.json().get("photos", [])
            if not photos:
                out.append(None)
                continue
            src = photos[0]["src"].get("large2x") or photos[0]["src"]["original"]
            img = requests.get(src, timeout=30)
            img.raise_for_status()
            path.write_bytes(img.content)
            out.append(str(path))
        except Exception as exc:
            log.warning("Image '%s' indisponible : %s", q, exc)
            out.append(None)
    return out
