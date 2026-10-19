"""Format INFOGRAPHIE : diapos animées (chiffre clé, points, titres) + voix off."""
from __future__ import annotations

import re

from PIL import Image, ImageDraw

from .base import BaseRenderer
from .common import (Captions, clamp, draw_lines, ease_in_out, ease_out, ease_out_back, fit_text,
                     font, load_cover, mix, paste_scaled, rounded, text_layer, text_size, wrap)

NUM_RE = re.compile(r"^([^\d\-]*)(-?\d[\d\s.,]*)(.*)$")


def _parse_number(txt: str):
    m = NUM_RE.match(txt.strip())
    if not m:
        return None
    raw = m.group(2).strip()
    suffix = (" " if m.group(2) != m.group(2).rstrip() else "") + m.group(3)
    clean = raw.replace(" ", "").replace(" ", "")
    dec = "," if "," in clean and clean.count(",") == 1 and len(clean.split(",")[1]) <= 2 else None
    try:
        if dec:
            val = float(clean.replace(".", "").replace(",", "."))
            return m.group(1), val, suffix, 1
        val = float(clean.replace(",", "").replace(".", "")) if clean.count(".") > 1 or \
            ("." in clean and len(clean.split(".")[1]) == 3) else float(clean.replace(",", ""))
        decimals = len(clean.split(".")[1]) if "." in clean and len(clean.split(".")[1]) != 3 else 0
        return m.group(1), val, suffix, decimals
    except ValueError:
        return None


def _fmt(val, decimals):
    return f"{val:,.{decimals}f}"


class SlidesRenderer(BaseRenderer):
    style = "slides"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.palettes = [
            (self.c_dark, (255, 255, 255), self.c_accent),
            (self.c_light, self.c_dark, self.c_primary),
            (self.c_primary, (255, 255, 255), self.c_accent),
        ]
        self._bg = {}

    def make_captions(self):
        return Captions(self.tl, int(60 * self.u), int(self.W * 0.88))

    def caption_y(self):
        return self.H * 0.735

    def pal(self, i):
        return self.palettes[i % 3]

    def background(self, i):
        if i in self._bg:
            return self._bg[i]
        W, H, u = self.W, self.H, self.u
        bg_c, fg_c, acc = self.pal(i)
        img = Image.new("RGBA", (W, H), bg_c + (255,))
        d = ImageDraw.Draw(img, "RGBA")
        # décor géométrique
        d.ellipse((W * .62, -H * .06, W * 1.25, H * .3), fill=mix(bg_c, acc, .25) + (255,))
        d.rectangle((0, H * .62, W * .06, H * .92), fill=acc + (255,))
        for k in range(6):
            d.ellipse((W * .08 + k * 34 * u, H * .955, W * .08 + k * 34 * u + 12 * u, H * .955 + 12 * u),
                      fill=mix(bg_c, fg_c, .3) + (255,))
        # bloc photo
        seg = self.segments[i]
        idx = seg.get("image", i)
        path = self.images[idx] if isinstance(idx, int) and 0 <= idx < len(self.images) else None
        if path and seg.get("kind") != "stat":
            pw, ph = int(W * 0.86), int(H * 0.22)
            photo = load_cover(path, pw, ph, 1.0)
            mask = rounded((pw, ph), int(30 * u), (255, 255, 255, 255)).getchannel("A")
            img.paste(photo, (int(W * .07), int(H * .14)), mask)
        # numéro de diapo
        f = font("Bold", int(30 * u))
        n = f"{i + 1:02d}/{len(self.segments):02d}"
        tw, _ = text_size(f, n)
        if not self.embedded:
            d.text((W - tw - 50 * u, H * .655), n, font=f, fill=mix(bg_c, fg_c, .55))
        self._bg[i] = (img, bool(path and seg.get("kind") != "stat"))
        return self._bg[i]

    def content(self, img, i, k, dur):
        W, H, u = self.W, self.H, self.u
        seg = self.segments[i]
        bg_c, fg_c, acc = self.pal(i)
        _, has_photo = self.background(i)
        top = H * (0.39 if has_photo else 0.20)
        area_h = H * 0.62 - top
        d = ImageDraw.Draw(img, "RGBA")
        kind = seg.get("kind") or ("title" if i == 0 else "headline")
        x0, mw = W * 0.10, int(W * 0.80)

        if kind == "stat" and seg.get("big"):
            parsed = _parse_number(seg["big"])
            if parsed:
                pre, val, suf, dec = parsed
                shown = pre + _fmt(val * ease_out(k / 1.1), dec) + suf
            else:
                shown = seg["big"]
            fnt, lines, size = fit_text(seg["big"].upper(), "Bold", mw, int(area_h * .5),
                                        int(230 * u), int(80 * u), 1.0)
            fnt2 = font("Bold", size)
            lay = text_layer(wrap(shown.upper(), fnt2, mw) or [" "], fnt2, size, acc, "center", 1.0,
                             shadow=False)
            yc = top + area_h * 0.32
            pop = ease_out_back(k / 0.45)
            # pastille derrière le chiffre
            r = area_h * 0.30 * pop
            d.ellipse((W / 2 - r, yc - r, W / 2 + r, yc + r), fill=mix(bg_c, acc, .14) + (255,))
            paste_scaled(img, lay, W / 2, yc, 0.6 + 0.4 * pop)
            if seg.get("label"):
                f, ls, s = fit_text(seg["label"], "Medium", mw, int(area_h * .3), int(58 * u), int(32 * u))
                a = clamp((k - .3) / .3)
                lay2 = text_layer(ls, f, s, fg_c + (int(255 * a),), "center", shadow=False)
                paste_scaled(img, lay2, W / 2, yc + area_h * 0.38 + (1 - a) * 20 * u)
        elif kind == "points" and seg.get("points"):
            pts = seg["points"][:3]
            f = font("Bold", int(58 * u))
            if seg.get("big"):
                fh, lh, sh = fit_text(seg["big"].upper(), "Bold", mw, int(area_h * .22), int(84 * u), int(40 * u))
                draw_lines(d, lh, fh, sh, x0, top, acc)
                top += len(lh) * sh * 1.1 + 30 * u
            slot = (dur - 0.3) / max(1, len(pts))
            y = top
            for j, ptxt in enumerate(pts):
                a = ease_out((k - j * slot * 0.6) / 0.35)
                if a <= 0:
                    break
                fp, lp, sp = fit_text(ptxt, "Medium", mw - int(90 * u), int(area_h * .22), int(64 * u), int(32 * u))
                xo = (1 - a) * 80 * u
                rr = 26 * u
                d.ellipse((x0 + xo, y + 8 * u, x0 + xo + 2 * rr, y + 8 * u + 2 * rr), fill=acc + (int(255 * a),))
                fn = font("Bold", int(32 * u))
                nw, _ = text_size(fn, str(j + 1))
                d.text((x0 + xo + rr - nw / 2, y + 12 * u), str(j + 1), font=fn, fill=bg_c + (int(255 * a),))
                draw_lines(d, lp, fp, sp, x0 + xo + 80 * u, y, fg_c + (int(255 * a),))
                y += len(lp) * sp * 1.1 + 34 * u
        else:  # title / headline
            txt = seg.get("big") or (self.script.get("title") if kind == "title" else seg["text"])
            size0 = int((112 if kind == "title" else 96) * u)
            fnt, lines, size = fit_text(txt.upper() if kind == "title" else txt, "Bold", mw,
                                        int(area_h * 0.75), size0, int(44 * u), 1.05)
            yy = top + (area_h - len(lines) * size * 1.05) / 2
            for j, ln in enumerate(lines):
                a = ease_out((k - j * 0.08) / 0.35)
                d.text((x0 - (1 - a) * 60 * u, yy + j * size * 1.05), ln, font=fnt,
                       fill=fg_c + (int(255 * a),))
            bar = ease_out((k - .2) / .4) * W * .3
            d.rectangle((x0, yy - 40 * u, x0 + bar, yy - 26 * u), fill=acc)

    def scene(self, t):
        W = self.W
        i = self.seg_index(t)
        seg = self.segments[i]
        k = t - seg["start"]
        dur = seg["end"] - seg["start"]
        cur = self.background(i)[0].copy()
        self.content(cur, i, k, dur)
        if i > 0 and k < 0.4 and not self.embedded:
            prev_seg = self.segments[i - 1]
            prev = self.background(i - 1)[0].copy()
            self.content(prev, i - 1, prev_seg["end"] - prev_seg["start"], prev_seg["end"] - prev_seg["start"])
            p = ease_in_out(k / 0.4)
            frame = Image.new("RGBA", cur.size)
            frame.alpha_composite(prev, (int(-W * p), 0))
            frame.alpha_composite(cur, (int(W * (1 - p)), 0))
            return frame
        return cur

