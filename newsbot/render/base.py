"""Squelette commun aux 3 formats : habillage, barre de progression, écran de fin."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from .intro import WIPE, BrandIntro

from .common import (END_CARD, FPS, Captions, audio_envelope, clamp, ease_out, encode,
                     font, generated_backdrop, load_cover, music_track, rgb, text_size, wrap,
                     draw_lines)


class BaseRenderer:
    style = "base"
    embedded = False  # True when used inside the mixed renderer (no own transitions)

    def __init__(self, cfg, script, timeline, folder: Path, images, W=1080, H=1920, end_card=True):
        self.cfg, self.script, self.tl, self.folder = cfg, script, timeline, Path(folder)
        self.images = images or []
        self.W, self.H = W, H
        self.u = min(W, H) / 1080
        self.vertical = H > W
        th = cfg["theme"]
        self.c_primary, self.c_dark = rgb(th["primary"]), rgb(th["dark"])
        self.c_light, self.c_accent = rgb(th["light"]), rgb(th["accent"])
        self.duration = timeline["duration"]
        self.total = self.duration + (END_CARD if end_card else 0)
        self.env = audio_envelope(self.folder / "audio.wav", timeline, self.total)
        self.segments = timeline["segments"]
        # branded opening ("Welcome to World in 60!") = first segment of the voice timeline
        self.has_intro = bool(self.segments) and self.segments[0].get("scene") == "intro"
        self.first_seg = 1 if self.has_intro else 0
        self.intro_end = (self.segments[0]["end"] + 0.16) if self.has_intro else 0.0
        self._covers = {}
        self._backdrops = {}
        self._static = None
        self.captions = self.make_captions()

    # ── à surcharger ──
    def make_captions(self):
        return Captions(self.tl, int((78 if self.vertical else 58) * self.u), int(self.W * 0.86))

    def scene(self, t: float) -> Image.Image:
        raise NotImplementedError

    # ── utilitaires ──
    def seg_index(self, t):
        for i, s in enumerate(self.segments):
            if t < s["end"] + 0.08:
                return i
        return len(self.segments) - 1

    def cover(self, seg_i, W=None, H=None):
        W, H = W or self.W, H or self.H
        idx = self.segments[seg_i].get("image", seg_i)
        path = self.images[idx] if isinstance(idx, int) and 0 <= idx < len(self.images) else None
        key = (path, W, H, seg_i if not path else None)
        if key not in self._covers:
            if path:
                self._covers[key] = load_cover(path, W, H)
            else:
                pal = [(self.c_dark, (20, 40, 70)), ((40, 12, 30), self.c_dark),
                       ((10, 30, 45), (5, 10, 20))][seg_i % 3]
                bd = generated_backdrop(int(W * 1.12), int(H * 1.12), seg_i * 7 + 3, pal[0], pal[1],
                                        self.c_primary if seg_i % 2 else self.c_accent)
                self._covers[key] = bd
        return self._covers[key]

    def env_at(self, t):
        i = int(t * FPS)
        return float(self.env[i]) if 0 <= i < len(self.env) else 0.0

    # ── habillage commun ──
    def chrome(self, img: Image.Image, t: float):
        u, W, H = self.u, self.W, self.H
        d = ImageDraw.Draw(img, "RGBA")
        # barre de progression
        d.rectangle((0, 0, W, int(10 * u)), fill=(0, 0, 0, 90))
        d.rectangle((0, 0, int(W * clamp(t / self.duration)), int(10 * u)), fill=self.c_primary)
        top = int((70 if self.vertical else 36) * u)
        # marque
        name = self.cfg["channel"]["name"].upper()
        f = font("Bold", int(34 * u))
        tw, _ = text_size(f, name)
        x0 = int(44 * u)
        d.rounded_rectangle((x0, top, x0 + tw + int(78 * u), top + int(64 * u)), int(14 * u),
                            fill=(11, 19, 32, 220))
        pulse = 0.6 + 0.4 * math.sin(t * 5)
        r = int(11 * u)
        cx, cy = x0 + int(30 * u), top + int(32 * u)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=self.c_primary + (int(255 * pulse),))
        d.text((x0 + int(54 * u), top + int(10 * u)), name, font=f, fill=(255, 255, 255))
        # catégorie
        cat = (self.script.get("category") or "news").upper()
        fc = font("Bold", int(28 * u))
        cw, _ = text_size(fc, cat)
        d.rounded_rectangle((W - x0 - cw - int(40 * u), top + int(6 * u), W - x0, top + int(58 * u)),
                            int(12 * u), fill=self.c_primary)
        d.text((W - x0 - cw - int(20 * u), top + int(12 * u)), cat, font=fc, fill=(255, 255, 255))
        # sources + mention IA en pied
        src = "Sources: " + " · ".join(self.script.get("sources", [])[:4])
        fs = font("Medium", int(26 * u))
        lines = wrap(src, fs, int(W * 0.9))[:2]
        fa = font("Regular", int(22 * u))
        lab = self.cfg["channel"].get("ai_label", "")
        y = H - int((120 if self.vertical else 70) * u) - len(lines) * int(32 * u)
        box_w = max([text_size(fs, ln)[0] for ln in lines] + [text_size(fa, lab)[0]]) + int(40 * u)
        box_h = len(lines) * int(32 * u) + int(48 * u)
        d.rounded_rectangle(((W - box_w) / 2, y - int(10 * u), (W + box_w) / 2, y + box_h),
                            int(16 * u), fill=(0, 0, 0, 120))
        for i, ln in enumerate(lines):
            lw, _ = text_size(fs, ln)
            d.text(((W - lw) / 2, y + i * int(32 * u)), ln, font=fs, fill=(255, 255, 255, 230))
        lw, _ = text_size(fa, lab)
        d.text(((W - lw) / 2, y + len(lines) * int(32 * u) + int(6 * u)), lab, font=fa,
               fill=(255, 255, 255, 180))

    def end_card(self, img: Image.Image, t: float):
        p = ease_out((t - self.duration) / 0.5)
        u, W, H = self.u, self.W, self.H
        overlay = Image.new("RGBA", img.size, self.c_dark + (int(250 * p),))
        img.alpha_composite(overlay)
        if p < 0.3:
            return
        d = ImageDraw.Draw(img, "RGBA")
        a = int(255 * clamp((p - 0.3) / 0.7))
        name = self.cfg["channel"]["name"].upper()
        fn = font("Bold", int(92 * u))
        lines = wrap(name, fn, int(W * 0.85))
        y = H * 0.36 - (1 - p) * 60 * u
        draw_lines(d, lines, fn, int(92 * u), W * 0.075, y, (255, 255, 255, a), "center", W * 0.85)
        y += len(lines) * 100 * u + 30 * u
        d.rectangle((W / 2 - 60 * u, y, W / 2 + 60 * u, y + 10 * u), fill=self.c_primary + (a,))
        fh = font("Medium", int(46 * u))
        h = self.cfg["channel"].get("handle", "")
        hw, _ = text_size(fh, h)
        d.text(((W - hw) / 2, y + 40 * u), h, font=fh, fill=self.c_accent + (a,))
        fs = font("Regular", int(36 * u))
        msg = self.cfg["channel"].get("tagline", "")
        mw, _ = text_size(fs, msg)
        d.text(((W - mw) / 2, y + 120 * u), msg, font=fs, fill=(255, 255, 255, int(a * .8)))

    # ── boucle de rendu ──
    def frames(self):
        n = int(math.ceil(self.total * FPS))
        intro = BrandIntro(self, self.segments[0]) if self.has_intro else None
        for i in range(n):
            t = i / FPS
            if intro and t < self.intro_end:
                img = intro.frame(t, self.env_at(t))
                wipe_start = self.intro_end - WIPE
                if t >= wipe_start:
                    first = self.scene(self.intro_end)
                    self.chrome(first, self.intro_end)
                    img = intro.wipe(img, first, (t - wipe_start) / WIPE)
                yield img
                continue
            img = self.scene(min(t, self.duration))
            if t <= self.duration:
                self.captions.draw(img, t, self.W / 2, self.caption_y_at(t))
            self.chrome(img, min(t, self.duration))
            if t > self.duration:
                self.end_card(img, t)
            yield img

    def caption_y_at(self, t):
        return self.caption_y()

    def caption_y(self):
        return self.H * 0.70

    def render(self, out: Path):
        sting = None
        if self.has_intro:
            from ..music import ensure_sting
            sting = ensure_sting()
        return encode(self.frames(), self.W, self.H, self.total, self.folder / "audio.wav", out,
                      music=music_track(self.cfg), music_vol=self.cfg.get_path("music.volume", 0.07),
                      sting=sting)
