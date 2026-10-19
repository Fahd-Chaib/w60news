"""Publication YouTube (Shorts + récap long) via YouTube Data API v3.

Quota par défaut : 100 uploads/jour (videos.insert a son propre compteur depuis déc. 2025).
Première connexion :  python -m newsbot auth youtube
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..config import SECRETS, env

log = logging.getLogger("newsbot.youtube")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]
TOKEN = SECRETS / "youtube_token.json"


def authorize():
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets = env("YOUTUBE_CLIENT_SECRETS", str(SECRETS / "youtube_client_secret.json"))
    flow = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
    # Sur un serveur sans écran : ouvre le lien affiché depuis ton PC,
    # ou lance cette commande en local puis copie secrets/youtube_token.json sur le serveur.
    creds = flow.run_local_server(port=8765, open_browser=False)
    TOKEN.write_text(creds.to_json())
    print(f"\nOK — token saved to {TOKEN}")
    print("For GitHub Actions: create the repository secret YOUTUBE_TOKEN_JSON with this content:\n")
    print(creds.to_json())


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    import json
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    elif env("YOUTUBE_TOKEN_JSON"):
        creds = Credentials.from_authorized_user_info(json.loads(env("YOUTUBE_TOKEN_JSON")), SCOPES)
    else:
        raise RuntimeError("YouTube not connected: run `python -m newsbot auth youtube`")
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())  # refreshed in memory; the refresh token itself does not change
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(cfg, video: Path, title: str, description: str, tags: list[str],
           thumbnail: Path | None = None) -> tuple[str, str]:
    from googleapiclient.http import MediaFileUpload

    yt_cfg = cfg["platforms"]["youtube"]
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags[:15],
            "categoryId": yt_cfg.get("category_id", "25"),
            "defaultLanguage": cfg["channel"]["language"],
            "defaultAudioLanguage": cfg["channel"]["language"],
        },
        "status": {
            "privacyStatus": yt_cfg.get("privacy", "public"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,   # déclaration "contenu modifié/synthétique"
        },
    }
    yt = _service()
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video), chunksize=8 * 1024 * 1024,
                                                        resumable=True, mimetype="video/mp4"))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    if thumbnail and thumbnail.exists():
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumbnail))).execute()
        except Exception as exc:  # nécessite une chaîne vérifiée
            log.warning("Miniature non appliquée : %s", exc)
    url = f"https://youtu.be/{vid}"
    log.info("YouTube OK : %s", url)
    return vid, url
