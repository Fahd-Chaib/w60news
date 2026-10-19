"""Publication TikTok via Content Posting API (Direct Post).

⚠ Tant que ton app n'a pas passé l'audit TikTok, les vidéos sont forcées en privé
(SELF_ONLY) et le compte doit être privé. Plafond ≈ 15 posts/jour/compte.
Première connexion :  python -m newsbot auth tiktok
"""
from __future__ import annotations

import json
import logging
import secrets
import time
import urllib.parse
from pathlib import Path

import requests

from .. import vault
from ..config import env

log = logging.getLogger("newsbot.tiktok")
API = "https://open.tiktokapis.com/v2"


def authorize():
    key, secret, redirect = env("TIKTOK_CLIENT_KEY"), env("TIKTOK_CLIENT_SECRET"), env("TIKTOK_REDIRECT_URI")
    state = secrets.token_urlsafe(12)
    url = "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode({
        "client_key": key, "scope": "user.info.basic,video.publish", "response_type": "code",
        "redirect_uri": redirect, "state": state})
    print("1) Ouvre ce lien, connecte le compte TikTok de la chaîne et autorise l'app :\n", url)
    back = input("2) Colle ici l'URL complète sur laquelle tu as été redirigé·e : ").strip()
    q = urllib.parse.parse_qs(urllib.parse.urlparse(back).query)
    if q.get("state", [""])[0] != state:
        raise SystemExit("State invalide — recommence.")
    r = requests.post(f"{API}/oauth/token/", data={
        "client_key": key, "client_secret": secret, "code": q["code"][0],
        "grant_type": "authorization_code", "redirect_uri": redirect}, timeout=30)
    data = r.json()
    if "access_token" not in data:
        raise SystemExit(f"Échec : {data}")
    data["obtained"] = time.time()
    vault.save("tiktok", data)
    print("\nOK. For GitHub Actions: create the repository secret TIKTOK_TOKEN_JSON with this content:\n")
    print(json.dumps(data))


def _token() -> str:
    data = vault.load("tiktok", "TIKTOK_TOKEN_JSON")
    if not data:
        raise RuntimeError("TikTok not connected: run `python -m newsbot auth tiktok`")
    if time.time() > data["obtained"] + data.get("expires_in", 86400) - 600:
        r = requests.post(f"{API}/oauth/token/", data={
            "client_key": env("TIKTOK_CLIENT_KEY"), "client_secret": env("TIKTOK_CLIENT_SECRET"),
            "grant_type": "refresh_token", "refresh_token": data["refresh_token"]}, timeout=30)
        new = r.json()
        if "access_token" not in new:
            raise RuntimeError(f"Refresh TikTok impossible : {new}")
        new["obtained"] = time.time()
        vault.save("tiktok", new)
        data = new
    return data["access_token"]


def _post(path, tok, payload):
    r = requests.post(f"{API}{path}", json=payload, timeout=60, headers={
        "Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"})
    body = r.json()
    err = body.get("error", {})
    if r.status_code >= 400 or (err.get("code") not in (None, "ok")):
        raise RuntimeError(f"TikTok {path} : {err or body}")
    return body.get("data", {})


def upload(cfg, video: Path, caption: str) -> tuple[str, str]:
    tok = _token()
    info = _post("/post/publish/creator_info/query/", tok, {})
    wanted = cfg["platforms"]["tiktok"].get("privacy", "PUBLIC_TO_EVERYONE")
    options = info.get("privacy_level_options", [])
    privacy = wanted if wanted in options else ("SELF_ONLY" if "SELF_ONLY" in options else options[0])
    if privacy != wanted:
        log.warning("TikTok : confidentialité %s indisponible, utilisation de %s", wanted, privacy)
    size = video.stat().st_size
    init = _post("/post/publish/video/init/", tok, {
        "post_info": {
            "title": caption[:2200], "privacy_level": privacy,
            "disable_duet": False, "disable_stitch": False, "disable_comment": False,
            "video_cover_timestamp_ms": 1500,
            "is_aigc": True,  # étiquette "contenu généré par IA"
        },
        "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                        "chunk_size": size, "total_chunk_count": 1},
    })
    with open(video, "rb") as f:
        r = requests.put(init["upload_url"], data=f, timeout=600, headers={
            "Content-Type": "video/mp4", "Content-Length": str(size),
            "Content-Range": f"bytes 0-{size - 1}/{size}"})
        r.raise_for_status()
    pid = init["publish_id"]
    for _ in range(40):
        st = _post("/post/publish/status/fetch/", tok, {"publish_id": pid})
        if st.get("status") == "PUBLISH_COMPLETE":
            ids = st.get("publicaly_available_post_id") or []
            url = f"https://www.tiktok.com/video/{ids[0]}" if ids else ""
            log.info("TikTok OK (%s) %s", privacy, url)
            return pid, url
        if st.get("status") == "FAILED":
            raise RuntimeError(f"TikTok a refusé la vidéo : {st.get('fail_reason')}")
        time.sleep(10)
    return pid, ""
