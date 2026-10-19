"""'BREAKING NEWS' opening sting drawn at the start of every short (≈2.4 s).

Timeline (seconds):
  0.00-0.35  red diagonal stripes sweep in, white flash, slight shake
  0.15-0.65  "BREAKING" (red bar) slides from the left, "NEWS" (dark bar) from the right
  0.35-2.40  spinning wireframe globe, LIVE dot, ticker crawl at the bottom
  0.70-1.70  the story headline types in
  2.05-2.40  red wipe up into the first shot
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .common import (clamp, draw_lines, ease_in_out, ease_out, ease_out_back, fit_text, font, mix,
                     text_size, wrap)

INTRO_SECONDS = 2.4


class BreakingIntro:
    def __init__(self, r):
        self.r = r
        self.W, self.H, self.u = r.W, r.H, r.u
        self.red, self.dark, self.acc = r.c_primary, r.c_dark, r.c_accent
        cfg = r.cfg
        self.label = (cfg.get_path("intro.label") or "BREAKING NEWS").upper().split()
        if len(self.label) == 1:
            self.label.append("")
        self.label = [self.label[0], " ".join(self.label[1:])]
        self.headline = (r.script.get("headline") or r.script.get("title") or "").strip()
        self.channel = cfg["channel"]["name"].upper()
        self._bg = self._background()
        self._bars = self._title_bars()
        self._ticker = self._ticker_strip()

    # ── static layers ─────────────────────────────────────────
    def _background(self):
        W, H = self.W, self.H
        y = np.linspace(0, 1, H)[:, None]
        x = np.linspace(0, 1, W)[None, :]
        d = np.sqrt((x - 0.5) ** 2 * 1.4 + (y - 0.42) ** 2)
        base = np.array(mix(self.dark, (0, 0, 0), 0.3))
        glow = np.array(mix(self.red, self.dark, 0.55))
        t = np.clip(1 - d * 1.6, 0, 1)[..., None]
        arr = (base * (1 - t) + glow * t).astype(np.uint8)
        img = Image.fromarray(arr, "RGB").convert("RGBA")
        g = ImageDraw.Draw(img, "RGBA")
        step = int(60 * self.u)
        for xx in range(0, W, step):
            g.line([(xx, 0), (xx, H)], fill=(255, 255, 255, 10))
        for yy in range(0, H, step):
            g.line([(0, yy), (W, yy)], fill=(255, 255, 255, 10))
        return img

    def _title_bars(self):
        u = self.u
        out = []
        for word, bg, fg in ((self.label[0], self.red, (255, 255, 255)),
                             (self.label[1], (255, 255, 255), self.red)):
            if not word:
                out.append(None)
                continue
            f, lines, size = fit_text(word, "Bold", int(self.W * 0.82), int(190 * u), int(170 * u), int(60 * u), 1.0)
            tw, th = text_size(f, lines[0])
            pad_x, pad_y = int(46 * u), int(26 * u)
            bar = Image.new("RGBA", (tw + 2 * pad_x, int(size * 1.18) + 2 * pad_y), (0, 0, 0, 0))
            d = ImageDraw.Draw(bar)
            d.polygon([(int(24 * u), 0), (bar.width, 0), (bar.width - int(24 * u), bar.height), (0, bar.height)], fill=bg)
            d.text((pad_x, pad_y - int(size * 0.08)), lines[0], font=f, fill=fg)
            out.append(bar)
        return out

    def _ticker_strip(self):
        u = self.u
        f = font("Bold", int(40 * u))
        unit = f"  {self.channel}  •  {' '.join(self.label).strip()}  •  LIVE  •"
        uw, _ = text_size(f, unit)
        h = int(78 * u)
        reps = int(self.W * 2 / max(uw, 1)) + 3
        strip = Image.new("RGBA", (uw * reps, h), self.acc + (255,))
        d = ImageDraw.Draw(strip)
        for k in range(reps):
            d.text((k * uw, int(14 * u)), unit, font=f, fill=self.dark)
        self.ticker_unit = uw
        return strip

    # ── animated pieces ───────────────────────────────────────
    def _stripes(self, img, p):
        """Diagonal red stripes sweeping across (p 0→1)."""
        W, H, u = self.W, self.H, self.u
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        band = int(120 * u)
        off = (1 - p) * W * 1.6
        for k in range(-4, 14):
            x0 = k * band * 2 - off
            d.polygon([(x0, 0), (x0 + band, 0), (x0 + band - H * 0.35, H), (x0 - H * 0.35, H)],
                      fill=self.red + (int(70 * (1 - abs(p - 0.5) * 2) + 20),))
        img.alpha_composite(layer)

    def _globe(self, img, t, cx, cy, r, alpha):
        if alpha <= 0:
            return
        S = int(r * 2 + 8)
        layer = Image.new("RGBA", (S * 2, S * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        c, R = S, r * 2
        col = (255, 255, 255, int(200 * alpha))
        d.ellipse((c - R, c - R, c + R, c + R), outline=col, width=int(6 * self.u))
        for lat in (-60, -30, 0, 30, 60):  # parallels
            yy = c + R * math.sin(math.radians(lat))
            rx = R * math.cos(math.radians(lat))
            d.ellipse((c - rx, yy - rx * 0.08, c + rx, yy + rx * 0.08), outline=col, width=int(3 * self.u))
        rot = t * 70
        for k in range(6):  # meridians, rotating
            ang = math.radians((rot + k * 30) % 180)
            rx = abs(R * math.cos(ang))
            front = math.cos(ang) > 0
            d.ellipse((c - rx, c - R, c + rx, c + R), outline=(255, 255, 255, int((170 if front else 70) * alpha)),
                      width=int(3 * self.u))
        layer = layer.resize((S, S), Image.LANCZOS)
        glow = layer.filter(ImageFilter.GaussianBlur(10 * self.u))
        img.alpha_composite(glow, (int(cx - S / 2), int(cy - S / 2)))
        img.alpha_composite(layer, (int(cx - S / 2), int(cy - S / 2)))

    def frame(self, t: float) -> Image.Image:
        W, H, u = self.W, self.H, self.u
        img = self._bg.copy()
        # stripes sweep + flash
        self._stripes(img, clamp(t / 0.45))
        if t < 0.18:
            img.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, int(200 * (1 - t / 0.18)))))
        # globe
        self._globe(img, t, W / 2, H * 0.27, 150 * u * ease_out_back((t - 0.3) / 0.5),
                    clamp((t - 0.3) / 0.3))
        # BREAKING / NEWS bars
        y1 = H * 0.42
        b1, b2 = self._bars
        if b1 is not None:
            p = ease_out(clamp((t - 0.15) / 0.4))
            xc = -b1.width / 2 + (W / 2 + b1.width / 2) * p
            img.alpha_composite(b1, (int(xc - b1.width / 2), int(y1)))
        if b2 is not None:
            p = ease_out(clamp((t - 0.28) / 0.4))
            xc = W + b2.width / 2 - (W / 2 + b2.width / 2) * p
            img.alpha_composite(b2, (int(xc - b2.width / 2), int(y1 + (b1.height * 0.92 if b1 else 0))))
        # headline typing
        if self.headline and t > 0.7:
            n = int(len(self.headline) * ease_in_out(clamp((t - 0.7) / 0.9)))
            shown = self.headline[:n] + ("|" if (t * 3) % 1 < 0.6 and n < len(self.headline) else "")
            f, lines, size = fit_text(self.headline, "Bold", int(W * 0.84), int(H * 0.16),
                                      int(72 * u), int(40 * u), 1.1)
            ls = wrap(shown, f, int(W * 0.84)) or [""]
            d = ImageDraw.Draw(img)
            yh = H * 0.42 + sum(b.height * 0.92 for b in self._bars if b is not None) + 50 * u
            draw_lines(d, ls, f, size, W * 0.08, yh, (255, 255, 255), "center", W * 0.84, 1.1)
        # LIVE badge
        d = ImageDraw.Draw(img, "RGBA")
        if t > 0.45:
            fl = font("Bold", int(36 * u))
            lw, _ = text_size(fl, "LIVE")
            x0, y0 = W * 0.08, H * 0.085
            d.rounded_rectangle((x0, y0, x0 + lw + 76 * u, y0 + 62 * u), int(12 * u), fill=(0, 0, 0, 170))
            pulse = 0.4 + 0.6 * (0.5 + 0.5 * math.sin(t * 9))
            rr = 12 * u
            d.ellipse((x0 + 20 * u, y0 + 31 * u - rr, x0 + 20 * u + 2 * rr, y0 + 31 * u + rr),
                      fill=self.red + (int(255 * pulse),))
            d.text((x0 + 54 * u, y0 + 8 * u), "LIVE", font=fl, fill=(255, 255, 255))
            fc = font("Bold", int(34 * u))
            cw, _ = text_size(fc, self.channel)
            d.text((W * 0.92 - cw, y0 + 10 * u), self.channel, font=fc, fill=(255, 255, 255, 220))
        # ticker
        ty = H * 0.86
        p = ease_out(clamp((t - 0.35) / 0.3))
        if p > 0:
            shift = int((t * 420 * u) % self.ticker_unit)
            crop = self._ticker.crop((shift, 0, shift + W, self._ticker.height))
            band = Image.new("RGBA", (W, crop.height), (0, 0, 0, 0))
            band.alpha_composite(crop, (int(-W * (1 - p)), 0))
            img.alpha_composite(band, (0, int(ty)))
            d.rectangle((0, ty - 10 * u, W, ty), fill=self.red)
        # shake on impact
        if 0.15 < t < 0.45:
            k = (t - 0.15) / 0.3
            dx = int(math.sin(t * 90) * 14 * u * (1 - k))
            img = img.transform(img.size, Image.AFFINE, (1, 0, dx, 0, 1, 0), fillcolor=self.dark + (255,))
        return img

    def wipe(self, intro_img: Image.Image, scene_img: Image.Image, p: float) -> Image.Image:
        """Red bar sweeps upward revealing the first shot."""
        W, H = self.W, self.H
        p = ease_in_out(p)
        y = int(H * (1 - p))
        out = intro_img.copy()
        out.paste(scene_img.crop((0, y, W, H)), (0, y))
        d = ImageDraw.Draw(out)
        d.rectangle((0, y - int(28 * self.u), W, y), fill=self.red)
        return out
