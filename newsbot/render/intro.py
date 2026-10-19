"""Branded opening: Sam or Nina says "Welcome to W60 News!" (≈2 s).

The welcome line is the first segment of the voice timeline (scene "intro"), so the voice,
lip-sync and timing come from the real TTS. This module only draws the pictures:
  · W60 logo badge pops in with a spinning globe and light rays
  · the speaking anchor rises into frame, mouth synced to the voice
  · the welcome words appear one by one as they are spoken
  · tagline ticker at the bottom, then a red wipe into the first shot
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .anchors import anchor
from .common import clamp, ease_in_out, ease_out, ease_out_back, fit_text, font, mix, paste_scaled, text_size

WIPE = 0.35  # seconds of red wipe at the end of the intro


def add_intro_segment(cfg, script: dict, key: str) -> dict:
    """Prepends the spoken welcome line to a script (alternating Sam / Nina by story)."""
    if not cfg.get_path("intro.enabled", True):
        return script
    segs = [s for s in script.get("segments", []) if s.get("scene") != "intro"]
    who = "ab"[sum(map(ord, key or "x")) % 2]
    if script.get("format") in ("mixed", "characters"):
        speaker = who
    else:  # single voice-over formats: the narrator is Nina's voice
        who, speaker = "b", "narrator"
    text = cfg.get_path("intro.text") or "Welcome to W60 News!"
    script["segments"] = [{"speaker": speaker, "anchor": who, "scene": "intro", "kind": "intro",
                           "text": text}] + segs
    return script


class BrandIntro:
    def __init__(self, r, seg: dict):
        self.r, self.seg = r, seg
        self.W, self.H, self.u = r.W, r.H, r.u
        self.red, self.dark, self.acc = r.c_primary, r.c_dark, r.c_accent
        cfg = r.cfg
        self.who = seg.get("anchor") or (seg.get("speaker") if seg.get("speaker") in ("a", "b") else "b")
        self.logo_txt = cfg.get_path("intro.logo") or "W60"
        self.logo_sub = cfg.get_path("intro.logo_sub") or "NEWS"
        self.tagline = cfg["channel"].get("tagline", "")
        self._bg = self._background()
        self._logo = self._logo_layer()
        self._ticker = self._ticker_strip()
        self._words = {}

    # ── static layers ─────────────────────────────────────────
    def _background(self):
        W, H = self.W, self.H
        y = np.linspace(0, 1, H)[:, None]
        x = np.linspace(0, 1, W)[None, :]
        d = np.sqrt((x - 0.5) ** 2 * 1.3 + (y - 0.3) ** 2)
        base = np.array(mix(self.dark, (0, 0, 0), 0.35))
        glow = np.array(mix((58, 91, 160), self.dark, 0.35))
        t = np.clip(1 - d * 1.5, 0, 1)[..., None]
        img = Image.fromarray((base * (1 - t) + glow * t).astype(np.uint8), "RGB").convert("RGBA")
        g = ImageDraw.Draw(img, "RGBA")
        step = int(60 * self.u)
        for xx in range(0, W, step):
            g.line([(xx, 0), (xx, H)], fill=(255, 255, 255, 9))
        for yy in range(0, H, step):
            g.line([(0, yy), (W, yy)], fill=(255, 255, 255, 9))
        return img

    def _logo_layer(self):
        u = self.u
        R = int(190 * u)
        S = 2 * R + int(20 * u)
        img = Image.new("RGBA", (S, S + int(150 * u)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        c = S // 2
        d.ellipse((c - R, c - R, c + R, c + R), fill=self.red)
        d.ellipse((c - R, c - R, c + R, c + R), outline=(255, 255, 255), width=int(10 * u))
        f, lines, size = fit_text(self.logo_txt, "Bold", int(R * 1.55), int(R * 0.9), int(190 * u), int(60 * u), 1.0)
        tw, _ = text_size(f, lines[0])
        d.text((c - tw / 2, c - size * 0.62), lines[0], font=f, fill=(255, 255, 255))
        fs = font("Bold", int(64 * u))
        sw, _ = text_size(fs, self.logo_sub)
        pill_w, pill_h = sw + int(70 * u), int(92 * u)
        top = c + R - int(30 * u)
        d.rounded_rectangle((c - pill_w / 2, top, c + pill_w / 2, top + pill_h), int(46 * u), fill=(255, 255, 255))
        d.text((c - sw / 2, top + int(8 * u)), self.logo_sub, font=fs, fill=self.dark)
        return img

    def _ticker_strip(self):
        u = self.u
        f = font("Bold", int(38 * u))
        unit = f"  {self.logo_txt} {self.logo_sub}  •  {self.tagline.upper()}  •"
        uw, _ = text_size(f, unit)
        reps = int(self.W * 2 / max(uw, 1)) + 3
        strip = Image.new("RGBA", (uw * reps, int(76 * u)), self.acc + (255,))
        d = ImageDraw.Draw(strip)
        for k in range(reps):
            d.text((k * uw, int(13 * u)), unit, font=f, fill=self.dark)
        self.ticker_unit = uw
        return strip

    def _word(self, w):
        if w not in self._words:
            u = self.u
            f = font("Bold", int(92 * u))
            tw, _ = text_size(f, w)
            lay = Image.new("RGBA", (tw + int(40 * u), int(140 * u)), (0, 0, 0, 0))
            ImageDraw.Draw(lay).text((int(20 * u), int(10 * u)), w, font=f, fill=(255, 255, 255),
                                     stroke_width=int(5 * u), stroke_fill=(0, 0, 0))
            self._words[w] = lay
        return self._words[w]

    # ── animated pieces ───────────────────────────────────────
    def _rays(self, img, t, cx, cy, alpha):
        if alpha <= 0:
            return
        W, H = self.W, self.H
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        L = max(W, H)
        for k in range(12):
            a0 = math.radians(t * 18 + k * 30)
            a1 = a0 + math.radians(9)
            d.polygon([(cx, cy), (cx + L * math.cos(a0), cy + L * math.sin(a0)),
                       (cx + L * math.cos(a1), cy + L * math.sin(a1))], fill=(255, 255, 255, int(14 * alpha)))
        img.alpha_composite(layer)

    def _globe_ring(self, img, t, cx, cy, r, alpha):
        if alpha <= 0 or r <= 1:
            return
        S = int(r * 2.4)
        layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c = S / 2
        d.ellipse((c - r, c - r, c + r, c + r), outline=(255, 255, 255, int(150 * alpha)), width=int(4 * self.u))
        for k in range(6):
            ang = math.radians((t * 80 + k * 30) % 180)
            rx = abs(r * math.cos(ang))
            d.ellipse((c - rx, c - r, c + rx, c + r), outline=(255, 255, 255, int(60 * alpha)), width=int(2 * self.u))
        img.alpha_composite(layer, (int(cx - c), int(cy - c)))

    def frame(self, t: float, level: float) -> Image.Image:
        W, H, u = self.W, self.H, self.u
        img = self._bg.copy()
        if t < 0.15:  # opening flash
            img.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, int(170 * (1 - t / 0.15)))))
        cx, cy = W / 2, H * 0.22
        self._rays(img, t, cx, cy, clamp(t / 0.4))
        pop = ease_out_back(clamp(t / 0.45))
        self._globe_ring(img, t, cx, cy, 250 * u * pop, clamp(t / 0.3))
        bob = math.sin(t * 3) * 6 * u
        paste_scaled(img, self._logo, cx, cy + 60 * u + bob, max(0.01, 0.5 + 0.5 * pop), clamp(t / 0.15))

        # welcome words, one by one as spoken (two lines max)
        words = self.seg.get("words") or []
        shown = [w for w in words if w["start"] <= t + 0.05]
        if shown:
            space = 26 * u
            lines, cur, cur_w = [], [], 0
            for w in shown:
                lw = self._word(w["w"].upper()).width
                if cur and cur_w + lw > W * 0.9:
                    lines.append(cur)
                    cur, cur_w = [], 0
                cur.append(w)
                cur_w += lw + space
            lines.append(cur)
            y0 = H * 0.44
            for li, line in enumerate(lines[-2:]):
                layers = [self._word(w["w"].upper()) for w in line]
                total = sum(lay.width for lay in layers) + space * (len(layers) - 1)
                x = (W - total) / 2
                for w, lay in zip(line, layers):
                    k = clamp((t - w["start"]) / 0.22)
                    paste_scaled(img, lay, x + lay.width / 2, y0 + li * 120 * u + lay.height / 2,
                                 0.6 + 0.4 * ease_out_back(k), clamp(k * 2))
                    x += lay.width + space

        # speaking anchor rises from the bottom, mouth synced to the voice
        rise = ease_out(clamp((t - 0.05) / 0.45))
        bust = anchor(self.who, int(560 * u), int(round(level * 6)), (t % 2.7) < 0.12, 0, True, False)
        bx = W / 2
        by = H - bust.height / 2 - 120 * u + (1 - rise) * bust.height - math.sin(t * 8) * 4 * u * level
        img.alpha_composite(bust, (int(bx - bust.width / 2), int(by - bust.height / 2)))

        # name tag + ticker
        d = ImageDraw.Draw(img, "RGBA")
        name = self.r.cfg["characters"][self.who]["name"].upper()
        fn = font("Bold", int(40 * u))
        nw, _ = text_size(fn, name)
        ty = H - 120 * u
        if rise > 0.6:
            a = int(255 * clamp((rise - 0.6) / 0.4))
            tagc = (58, 91, 160) if self.who == "a" else (24, 131, 122)
            d.rounded_rectangle((W / 2 - nw / 2 - 30 * u, ty - 92 * u, W / 2 + nw / 2 + 30 * u, ty - 30 * u),
                                int(31 * u), fill=tagc + (a,))
            d.text((W / 2 - nw / 2, ty - 84 * u), name, font=fn, fill=(255, 255, 255, a))
        p = ease_out(clamp((t - 0.25) / 0.35))
        if p > 0:
            shift = int((t * 380 * u) % self.ticker_unit)
            crop = self._ticker.crop((shift, 0, shift + W, self._ticker.height))
            band = Image.new("RGBA", (W, crop.height), (0, 0, 0, 0))
            band.alpha_composite(crop, (int(-W * (1 - p)), 0))
            img.alpha_composite(band, (0, int(ty)))
            d.rectangle((0, ty - 8 * u, W, ty), fill=self.red)
        return img

    def wipe(self, intro_img: Image.Image, scene_img: Image.Image, p: float) -> Image.Image:
        """Red bar sweeps upward revealing the first shot."""
        W, H = self.W, self.H
        y = int(H * (1 - ease_in_out(clamp(p))))
        out = intro_img.copy()
        out.paste(scene_img.crop((0, y, W, H)), (0, y))
        ImageDraw.Draw(out).rectangle((0, y - int(28 * self.u), W, y), fill=self.red)
        return out
