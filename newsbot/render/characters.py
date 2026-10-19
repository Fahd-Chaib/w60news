"""Anchors format: Sam & Nina, cartoon TV anchors, present the story at the news desk."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .base import BaseRenderer
from .common import (Captions, clamp, ease_out, ease_out_back, fit_text, font, generated_backdrop,
                     gradient, ken_burns, paste_scaled, rgb, rounded, text_layer, text_size)
from .anchors import anchor

TAG_COLORS = {"a": (58, 91, 160), "b": (24, 131, 122)}


class CharactersRenderer(BaseRenderer):
    style = "characters"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        W, H, u = self.W, self.H, self.u
        self.studio = generated_backdrop(W, H, 11, (14, 22, 48), (6, 9, 20), (60, 90, 200))
        # screen
        self.sx0, self.sy0 = int(56 * u), int(170 * u)
        self.sw, self.sh = W - 2 * self.sx0, int(H * 0.365)
        self.mask = rounded((self.sw, self.sh), int(36 * u), (255, 255, 255, 255)).getchannel("A")
        sh = gradient(self.sw, self.sh, (0, 0, 0), (0, 0, 0))
        sh.putalpha(gradient(self.sw, self.sh, (0, 0, 0), (215, 215, 215)).convert("L"))
        self.screen_shade = sh
        # desk
        self.desk_y = int(H * 0.80)
        desk = Image.new("RGBA", (W, H - self.desk_y), (0, 0, 0, 0))
        dd = ImageDraw.Draw(desk)
        dd.rounded_rectangle((-20, 0, W + 20, H), int(30 * u), fill=(20, 28, 52))
        dd.rectangle((0, 0, W, int(14 * u)), fill=self.c_primary)
        fl = font("Bold", int(30 * u))
        logo = self.cfg["channel"]["name"].upper()
        lw, _ = text_size(fl, logo)
        dd.text(((W - lw) / 2, int(118 * u)), logo, font=fl, fill=(255, 255, 255, 90))
        self.desk = desk
        self.msize = int(500 * u)
        self.sober = bool(self.script.get("grave"))
        ch = self.cfg["characters"]
        self.chars = {
            "a": {"x": W * 0.265, **ch["a"]},
            "b": {"x": W * 0.735, **ch["b"]},
        }
        self._big = {}
        self._tags = {}

    def make_captions(self):
        return Captions(self.tl, int(66 * self.u), int(self.W * 0.88))

    def caption_y(self):
        top_of_heads = self.desk_y - 0.74 * 1.3 * self.msize
        return (self.sy0 + self.sh + top_of_heads) / 2

    def big_layer(self, i):
        if i not in self._big:
            seg = self.segments[i]
            txt = (seg.get("big") or "").upper()
            if not txt:
                self._big[i] = None
            else:
                fnt, lines, size = fit_text(txt, "Bold", int(self.sw * 0.86), int(self.sh * 0.32),
                                            int(104 * self.u), int(44 * self.u), 1.02)
                self._big[i] = text_layer(lines, fnt, size, (255, 255, 255), "center", 1.02,
                                          stroke=max(3, size // 15))
        return self._big[i]

    def tag(self, who):
        if who not in self._tags:
            c = self.chars[who]
            f = font("Bold", int(34 * self.u))
            w, _ = text_size(f, c["name"].upper())
            img = rounded((w + int(44 * self.u), int(58 * self.u)), int(29 * self.u), TAG_COLORS[who])
            ImageDraw.Draw(img).text((int(22 * self.u), int(7 * self.u)), c["name"].upper(), font=f,
                                     fill=(255, 255, 255))
            self._tags[who] = img
        return self._tags[who]

    def scene(self, t):
        W, H, u = self.W, self.H, self.u
        img = self.studio.copy()
        i = self.seg_index(t)
        seg = self.segments[i]
        k = t - seg["start"]
        p = clamp(k / max(0.1, seg["end"] - seg["start"]))
        speaker = seg.get("speaker", "a")

        # screen with photo
        scr = ken_burns(self.cover(i, self.sw, self.sh), self.sw, self.sh, p, i)
        if i > 0 and k < 0.3 and not self.embedded:
            prev = ken_burns(self.cover(i - 1, self.sw, self.sh), self.sw, self.sh, 1, i - 1)
            scr = Image.blend(prev, scr, ease_out(k / 0.3))
        scr.alpha_composite(self.screen_shade)
        big = self.big_layer(i)
        if big is not None:
            paste_scaled(scr, big, self.sw / 2, self.sh * 0.78, 0.75 + 0.25 * ease_out_back(k / 0.35),
                         clamp(k / 0.2))
        glow_c = TAG_COLORS.get(speaker, self.c_primary)
        d = ImageDraw.Draw(img, "RGBA")
        g = int(10 * u)
        d.rounded_rectangle((self.sx0 - g, self.sy0 - g, self.sx0 + self.sw + g, self.sy0 + self.sh + g),
                            int(44 * u), fill=glow_c + (200,))
        img.paste(scr, (self.sx0, self.sy0), self.mask)

        # anchors (behind the desk)
        level = self.env_at(t)
        for who, c in self.chars.items():
            active = speaker == who
            mouth_q = int(round(level * 6)) if active else 0
            period = 3.1 if who == "a" else 3.7
            blink = (t % period) < 0.12
            look = 0 if active else (1 if who == "a" else -1)
            if speaker not in self.chars:
                look = 0
            m = anchor(who, self.msize, mouth_q, blink, look, active, self.sober)
            # gentle head-bob while talking, slow breathing otherwise (calmer on grave stories)
            amp = 2 if self.sober else 5
            bounce = (math.sin(t * 8) * amp * u * level) if active else math.sin(t * 1.6 + (who == "b")) * 2 * u
            lean = (6 * u if who == "a" else -6 * u) if not active else 0
            scale = 1.0 if active else 0.96
            cy = self.desk_y - m.height * scale / 2 + m.height * 0.26 - bounce
            paste_scaled(img, m, c["x"] + lean, cy, scale)
        img.alpha_composite(self.desk, (0, self.desk_y))
        for who, c in self.chars.items():
            tg = self.tag(who)
            a = 1.0 if speaker == who else 0.55
            paste_scaled(img, tg, c["x"], self.desk_y + 62 * u, 1.0, a)
        return img
