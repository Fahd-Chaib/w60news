"""Publication Instagram Reels via l'API Instagram (compte Pro ou Créateur obligatoire).

Upload "resumable" : la vidéo est envoyée directement depuis le serveur,
pas besoin de l'héberger sur une URL publique.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

from .. import vault
from ..config import env

log = logging.getLogger("newsbot.instagram")


def _token(cfg) -> str:
    data = vault.load("instagram", "INSTAGRAM_ACCESS_TOKEN") or {}
    tok = data.get("access_token")
    if not tok:
        raise RuntimeError("INSTAGRAM_ACCESS_TOKEN is missing")
    # rafraîchit le token longue durée (60 j) tous les ~20 jours
    if cfg["platforms"]["instagram"]["graph_host"] == "graph.instagram.com" and \
            time.time() - data.get("refreshed", 0) > 20 * 86400:
        try:
            r = requests.get("https://graph.instagram.com/refresh_access_token",
                             params={"grant_type": "ig_refresh_token", "access_token": tok}, timeout=30)
            r.raise_for_status()
            tok = r.json()["access_token"]
            vault.save("instagram", {"access_token": tok, "refreshed": time.time()})
            log.info("Instagram token refreshed")
        except Exception as exc:
            log.warning("Could not refresh the Instagram token: %s", exc)
    return tok


def _check(r: requests.Response):
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram {r.status_code} : {r.text[:400]}")
    return r.json()


def upload(cfg, video: Path, caption: str, cover: Path | None = None) -> tuple[str, str]:
    ig = cfg["platforms"]["instagram"]
    host, ver = ig["graph_host"], ig["api_version"]
    tok = _token(cfg)
    base = f"https://{host}/{ver}"
    user_id = env("INSTAGRAM_USER_ID")
    if not user_id:  # look it up from the token (Instagram API with Instagram Login)
        me = _check(requests.get(f"{base}/me", params={"fields": "user_id,username", "access_token": tok},
                                 timeout=30))
        user_id = me.get("user_id") or me.get("id")
        log.info("Instagram account: @%s (%s)", me.get("username"), user_id)

    # 1) conteneur Reel
    c = _check(requests.post(f"{base}/{user_id}/media", data={
        "media_type": "REELS", "upload_type": "resumable", "caption": caption[:2200],
        "share_to_feed": "true", "access_token": tok}, timeout=60))
    container = c["id"]
    upload_uri = c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{ver}/{container}"

    # 2) envoi du fichier
    size = video.stat().st_size
    with open(video, "rb") as f:
        _check(requests.post(upload_uri, data=f, timeout=600, headers={
            "Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(size)}))

    # 3) attente du traitement
    for _ in range(40):
        st = _check(requests.get(f"{base}/{container}",
                                 params={"fields": "status_code,status", "access_token": tok}, timeout=30))
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram a refusé la vidéo : {st}")
        time.sleep(15)
    else:
        raise RuntimeError("Instagram : traitement trop long")

    # 4) publication
    pub = _check(requests.post(f"{base}/{user_id}/media_publish",
                               data={"creation_id": container, "access_token": tok}, timeout=60))
    media_id = pub["id"]
    link = ""
    try:
        link = _check(requests.get(f"{base}/{media_id}",
                                   params={"fields": "permalink", "access_token": tok}, timeout=30)
                      ).get("permalink", "")
    except Exception:
        pass
    log.info("Instagram OK : %s", link or media_id)
    return media_id, link
