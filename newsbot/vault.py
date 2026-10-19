"""Token storage that survives between GitHub Actions runs.

On GitHub (public repo), refreshed tokens are saved ENCRYPTED in data/secure/*.enc
(committed to the `state` branch) with the STATE_KEY secret. Without STATE_KEY
(running on your own machine), they are stored as plain JSON in secrets/.

First run: tokens are seeded from environment variables / GitHub Secrets.
"""
from __future__ import annotations

import json

from .config import DATA, SECRETS, env


def _fernet():
    key = env("STATE_KEY")
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def _path(name):
    return (DATA / "secure" / f"{name}.enc") if _fernet() else (SECRETS / f"{name}_token.json")


def load(name: str, seed_env: str | None = None) -> dict | None:
    path, f = _path(name), _fernet()
    if path.exists():
        raw = path.read_bytes()
        return json.loads(f.decrypt(raw) if f else raw)
    if seed_env and env(seed_env):
        val = env(seed_env).strip()
        return json.loads(val) if val.startswith("{") else {"access_token": val}
    return None


def save(name: str, data: dict):
    path, f = _path(name), _fernet()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data).encode()
    path.write_bytes(f.encrypt(raw) if f else raw)


def keygen() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()
