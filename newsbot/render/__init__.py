"""Point d'entrée du rendu vidéo."""
from __future__ import annotations

from pathlib import Path

from .characters import CharactersRenderer
from .common import load_timeline
from .mixed import MixedRenderer
from .motion import MotionRenderer
from .slides import SlidesRenderer

RENDERERS = {"mixed": MixedRenderer, "characters": CharactersRenderer, "motion": MotionRenderer,
             "slides": SlidesRenderer}


def render_story(cfg, script, folder: Path, images, out: Path, fmt=None, W=1080, H=1920, end_card=True):
    fmt = fmt or script["format"]
    renderer = RENDERERS[fmt](cfg, script, load_timeline(folder), folder, images, W=W, H=H,
                               end_card=end_card)
    return renderer.render(out)
