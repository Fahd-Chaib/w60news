"""Chargement de la configuration (config.yaml + .env)."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv est optionnel
    load_dotenv = None

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"
FONTS = ASSETS / "fonts"
SECRETS = ROOT / "secrets"


class Config(dict):
    """dict avec accès par points : cfg.get_path("selection.min_score")."""

    def get_path(self, dotted: str, default=None):
        node = self
        for key in dotted.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


def load(path: str | Path | None = None) -> Config:
    if load_dotenv:
        load_dotenv(ROOT / ".env")
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = Config(yaml.safe_load(f))
    DATA.mkdir(exist_ok=True)
    SECRETS.mkdir(exist_ok=True)
    return cfg


def env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name, default)
    return val if val not in ("", None) else default
