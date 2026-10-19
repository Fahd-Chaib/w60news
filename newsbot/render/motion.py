"""Format MOTION : photos en Ken Burns, mots-chocs cinétiques, sous-titres karaoké."""
from __future__ import annotations

from PIL import Image, ImageDraw

from .base import BaseRenderer
from .common import (clamp, ease_out, ease_out_back, fit_text, font, gradient, ken_burns,
                     paste_scaled, text_layer, text_size)


class MotionRenderer(BaseRenderer):
    style = "motion"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        W, H = self.W, self.H
        shade = gradient(W, H, (0, 0, 0), (0, 0, 0))
        mask = gradient(W, H, (70, 70, 70), (235, 235, 235)).convert("L")
        shade.putalpha(mask)
        self.shade = shade
        self._big = {}

    def big_layer(self, i):
        if i not in self._big:
            seg = self.segments[i]
            txt = (seg.get("big") or " ".join(seg["text"].split()[:4])).upper()
            fnt, lines, size = fit_text(txt, "Bold", int(self.W * 0.84), int(self.H * 0.24),
                                        int(150 * self.u), int(60 * self.u), 1.02)
            layer = text_layer(lines, fnt, size, (255, 255, 255), "center", 1.02,
                               stroke=max(4, size // 14), stroke_fill=(0, 0, 0))
            label = seg.get("label")
            if label and seg.get("kind") == "stat":
                f2, l2, s2 = fit_text(label, "Medium", int(self.W * 0.8), int(self.H * 0.08),
                                      int(54 * self.u), int(30 * self.u))
                sub = text_layer(l2, f2, s2, self.c_accent, "center", stroke=3)
                combo = Image.new("RGBA", (max(layer.width, sub.width), layer.height + sub.height),
                                  (0, 0, 0, 0))
                combo.alpha_composite(layer, ((combo.width - layer.width) // 2, 0))
                combo.alpha_composite(sub, ((combo.width - sub.width) // 2, layer.height))
                layer = combo
            self._big[i] = layer
        return self._big[i]

    def scene(self, t):
        W, H, u = self.W, self.H, self.u
        i = self.seg_index(t)
        seg = self.segments[i]
        start, end = seg["start"], seg["end"]
        p = clamp((t - start) / max(0.1, end - start))
        img = ken_burns(self.cover(i), W, H, p, i)
        if i > 0 and t - start < 0.3 and not self.embedded:  # crossfade
            prev = ken_burns(self.cover(i - 1), W, H, 1.0, i - 1)
            img = Image.blend(prev, img, ease_out((t - start) / 0.3))
        img.alpha_composite(self.shade)

        # bande "INFO" au premier segment
        d = ImageDraw.Draw(img, "RGBA")
        cy = H * (0.40 if self.vertical else 0.44)
        k = t - start
        if i == 0:
            f = font("Bold", int(44 * u))
            lab = "TOP STORY"
            lw, lh = text_size(f, lab)
            a = ease_out(k / 0.3)
            x = W / 2 - lw / 2 - 24 * u
            y = cy - H * 0.17
            d.rectangle((x, y, x + (lw + 48 * u) * a, y + 70 * u), fill=self.c_primary)
            if a > 0.6:
                d.text((x + 24 * u, y + 8 * u), lab, font=f, fill=(255, 255, 255))

        layer = self.big_layer(i)
        pop = ease_out_back(k / 0.38)
        alpha = clamp(k / 0.2) * (1 - clamp((t - end + 0.1) / 0.15))
        drift = (1 - ease_out(k / 0.5)) * 50 * u
        paste_scaled(img, layer, W / 2, cy + drift, 0.7 + 0.3 * pop, alpha)
        # trait d'accent sous le mot-choc
        bar = ease_out((k - 0.15) / 0.35) * W * 0.25
        by = cy + layer.height / 2 + 6 * u
        d.rectangle((W / 2 - bar / 2, by, W / 2 + bar / 2, by + 12 * u), fill=self.c_primary)

        if k < 0.12 and i > 0 and not self.embedded:  # micro-flash
            img.alpha_composite(Image.new("RGBA", img.size, (255, 255, 255, int(110 * (1 - k / 0.12)))))
        return img

    def caption_y(self):
        return self.H * (0.68 if self.vertical else 0.74)
