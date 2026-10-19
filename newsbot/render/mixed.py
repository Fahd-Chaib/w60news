"""MIXED format: every line of dialogue gets its own shot.

Scenes: desk (Sam & Nina at the news desk), photo (full-screen picture + punchy words),
stat / points (infographic), claim ("according to <outlet>"), versus (A vs B),
timeline (key dates), question (audience interaction with answer options).
Off the desk, the anchor who is talking stays on screen in a picture-in-picture bubble.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from .anchors import anchor
from .base import BaseRenderer
from .characters import TAG_COLORS, CharactersRenderer
from .common import (clamp, draw_lines, ease_in_out, ease_out, ease_out_back, fit_text, font,
                     generated_backdrop, ken_burns, mix, paste_scaled, rounded, text_layer, text_size,
                     wrap)
from .motion import MotionRenderer
from .slides import SlidesRenderer

SCENES = ("desk", "photo", "stat", "points", "claim", "versus", "timeline", "question")


class MixedRenderer(BaseRenderer):
    style = "mixed"

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        sub_kw = dict(W=self.W, H=self.H, end_card=False)
        args = (self.cfg, self.script, self.tl, self.folder, self.images)
        self.desk = CharactersRenderer(*args, **sub_kw)
        self.motion = MotionRenderer(*args, **sub_kw)
        self.slides = SlidesRenderer(*args, **sub_kw)
        for r in (self.desk, self.motion, self.slides):
            r.embedded = True
        for seg in self.segments:
            seg["scene"] = seg.get("scene") if seg.get("scene") in SCENES else "desk"
            if seg["scene"] in ("stat", "points"):
                seg["kind"] = seg["scene"]
        self.sober = bool(self.script.get("grave"))
        self._blur = {}
        self._layers = {}

    # ── shot dispatch ─────────────────────────────────────────
    def shot(self, i, t):
        sc = self.segments[i]["scene"]
        if sc == "desk":
            return self.desk.scene(t)
        if sc == "photo":
            img = self.motion.scene(t)
        elif sc in ("stat", "points"):
            img = self.slides.scene(t)
        else:
            img = getattr(self, f"card_{sc}")(i, t)
        self.pip(img, i, t)
        return img

    def scene(self, t):
        i = self.seg_index(t)
        seg = self.segments[i]
        k = t - seg["start"]
        img = self.shot(i, t)
        dur = 0.34
        if i > 0 and k < dur:
            prev = self.shot(i - 1, self.segments[i - 1]["end"] - 0.02)
            img = self.transition(prev, img, ease_in_out(k / dur), i)
        return img

    def transition(self, a, b, p, i):
        W, H = self.W, self.H
        kind = i % 4
        if kind == 0:  # push left
            out = Image.new("RGBA", a.size)
            out.alpha_composite(a, (int(-W * p), 0))
            out.alpha_composite(b, (int(W * (1 - p)), 0))
            return out
        if kind == 1:  # zoom-through crossfade
            z = 1 + 0.12 * p
            az = a.resize((int(W * z), int(H * z)), Image.BILINEAR).crop(
                (int(W * (z - 1) / 2), int(H * (z - 1) / 2), int(W * (z - 1) / 2) + W, int(H * (z - 1) / 2) + H))
            return Image.blend(az, b, p)
        if kind == 2:  # brand-colour wipe from bottom
            out = a.copy()
            y = int(H * (1 - p))
            out.paste(b.crop((0, y, W, H)), (0, y))
            d = ImageDraw.Draw(out)
            d.rectangle((0, y - int(18 * self.u), W, y), fill=self.c_primary)
            return out
        # push up
        out = Image.new("RGBA", a.size)
        out.alpha_composite(a, (0, int(-H * p)))
        out.alpha_composite(b, (0, int(H * (1 - p))))
        return out

    def caption_y_at(self, t):
        sc = self.segments[self.seg_index(t)]["scene"]
        if sc == "desk":
            return self.desk.caption_y()
        return self.H * 0.665

    # ── picture-in-picture anchor bubble ──────────────────────
    def pip(self, img, i, t):
        seg = self.segments[i]
        who_list = ["a", "b"] if seg["scene"] == "question" else [seg.get("speaker", "a")]
        u, W, H = self.u, self.W, self.H
        k = t - seg["start"]
        level = self.env_at(t)
        for who in who_list:
            if who not in ("a", "b"):
                continue
            active = who == seg.get("speaker")
            r = int(120 * u)
            cx = W * (0.14 if who == "a" else 0.86)
            cy = H * 0.805
            pop = ease_out_back(k / 0.35)
            bub = self._bubble(who, r, int(round(level * 6)) if active else 0,
                               (t % (3.1 if who == "a" else 3.7)) < 0.12, active)
            bounce = math.sin(t * 8) * 3 * u * level if active and not self.sober else 0
            paste_scaled(img, bub, cx, cy - bounce, 0.6 + 0.4 * pop, 1.0 if active else 0.75)

    def _bubble(self, who, r, mouth_q, blink, active):
        key = ("bub", who, r, mouth_q, blink, active, self.sober)
        if key in self._layers:
            return self._layers[key]
        size = int(r * 2.3)
        bust = anchor(who, size, mouth_q, blink, 0, active, self.sober)
        S = 2 * r + int(16 * self.u)
        img = Image.new("RGBA", (S, S + int(54 * self.u)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        ring = TAG_COLORS[who]
        d.ellipse((0, 0, S - 1, S - 1), fill=(255, 255, 255))
        inner = Image.new("RGBA", (2 * r, 2 * r), mix(ring, (11, 19, 32), 0.45) + (255,))
        inner.alpha_composite(bust, ((2 * r - bust.width) // 2, int(r * 0.02)))
        mask = Image.new("L", (2 * r, 2 * r), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 2 * r - 1, 2 * r - 1), fill=255)
        o = (S - 2 * r) // 2
        img.paste(inner, (o, o), mask)
        # name tag
        f = font("Bold", int(28 * self.u))
        name = self.cfg["characters"][who]["name"].upper()
        tw, _ = text_size(f, name)
        tag = rounded((tw + int(36 * self.u), int(48 * self.u)), int(24 * self.u), ring)
        ImageDraw.Draw(tag).text((int(18 * self.u), int(6 * self.u)), name, font=f, fill=(255, 255, 255))
        img.alpha_composite(tag, ((S - tag.width) // 2, S - int(24 * self.u)))
        if len(self._layers) > 400:
            self._layers.clear()
        self._layers[key] = img
        return img

    # ── backgrounds for cards ────────────────────────────────
    def card_bg(self, i, t, tint):
        """Blurred, darkened photo of the story (or generated backdrop) behind a card."""
        if i not in self._blur:
            base = self.cover(i).copy().resize((self.W // 4, self.H // 4)).filter(ImageFilter.GaussianBlur(6))
            base = base.resize((int(self.W * 1.12), int(self.H * 1.12)), Image.BILINEAR)
            dark = Image.new("RGBA", base.size, tint + (190,))
            base.alpha_composite(dark)
            self._blur[i] = base
        seg = self.segments[i]
        p = clamp((t - seg["start"]) / max(0.1, seg["end"] - seg["start"]))
        return ken_burns(self._blur[i], self.W, self.H, p, i)

    def header(self, img, text, color, y, t0):
        u = self.u
        d = ImageDraw.Draw(img)
        f = font("Bold", int(40 * u))
        tw, _ = text_size(f, text)
        a = ease_out(t0 / 0.3)
        x = self.W * 0.08
        d.rectangle((x, y, x + (tw + 44 * u) * a, y + 66 * u), fill=color)
        if a > 0.6:
            d.text((x + 22 * u, y + 8 * u), text, font=f, fill=(255, 255, 255))

    # ── claim: "according to <outlet>" ───────────────────────
    def card_claim(self, i, t):
        seg, u, W, H = self.segments[i], self.u, self.W, self.H
        k = t - seg["start"]
        img = self.card_bg(i, t, (11, 19, 32))
        src = (seg.get("source") or (self.script.get("sources") or ["reports"])[0]).upper()
        self.header(img, f"ACCORDING TO {src}", self.c_primary, H * 0.17, k)
        key = ("claim", i)
        if key not in self._layers:
            txt = seg.get("big") or seg["text"]
            fnt, lines, size = fit_text(txt, "Bold", int(W * 0.80), int(H * 0.30), int(84 * u), int(40 * u), 1.12)
            lay = Image.new("RGBA", (int(W * 0.86), int(len(lines) * size * 1.12 + 40 * u)), (0, 0, 0, 0))
            draw_lines(ImageDraw.Draw(lay), lines, fnt, size, int(W * 0.04), 0, (255, 255, 255), line_gap=1.12)
            self._layers[key] = lay
        lay = self._layers[key]
        a = ease_out(k / 0.4)
        d = ImageDraw.Draw(img)
        x0 = W * 0.08
        y0 = H * 0.27
        d.rectangle((x0, y0, x0 + 12 * u, y0 + lay.height * a), fill=self.c_accent)
        img.alpha_composite(lay.crop((0, 0, lay.width, max(1, int(lay.height * a)))), (int(x0 + 10 * u), int(y0)))
        return img

    # ── versus: two values side by side ──────────────────────
    def card_versus(self, i, t):
        seg, u, W, H = self.segments[i], self.u, self.W, self.H
        k = t - seg["start"]
        img = self.card_bg(i, t, (11, 19, 32))
        if seg.get("big"):
            self.header(img, seg["big"].upper()[:28], self.c_primary, H * 0.14, k)
        d = ImageDraw.Draw(img)
        sides = [seg.get("left") or {}, seg.get("right") or {}]
        colors = [(58, 91, 160), self.c_primary]
        pw, ph = W * 0.40, H * 0.36
        for j, side in enumerate(sides):
            a = ease_out_back((k - j * 0.25) / 0.4)
            if a <= 0:
                continue
            x = W * 0.07 + j * (W * 0.46)
            y = H * 0.23 + (1 - a) * 80 * u
            d.rounded_rectangle((x, y, x + pw, y + ph), int(34 * u), fill=colors[j])
            fv, lv, sv = fit_text(str(side.get("value", "")), "Bold", int(pw * 0.86), int(ph * 0.45),
                                  int(120 * u), int(44 * u), 1.0)
            draw_lines(d, lv, fv, sv, x + pw * 0.07, y + ph * 0.18, (255, 255, 255), "center", pw * 0.86, 1.0)
            fl, ll, sl = fit_text(str(side.get("label", "")), "Medium", int(pw * 0.84), int(ph * 0.3),
                                  int(46 * u), int(26 * u))
            draw_lines(d, ll, fl, sl, x + pw * 0.08, y + ph * 0.66, (255, 255, 255), "center", pw * 0.84)
        if k > 0.45:
            r = 62 * u * ease_out_back((k - 0.45) / 0.3)
            cx, cy = W / 2, H * 0.23 + ph / 2
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=self.c_accent, outline=(255, 255, 255), width=int(6 * u))
            fv = font("Bold", int(48 * u * max(r, 1) / (62 * u)))
            tw, th = text_size(fv, "VS")
            d.text((cx - tw / 2, cy - th / 2 - 10 * u), "VS", font=fv, fill=(11, 19, 32))
        return img

    # ── timeline: key dates ──────────────────────────────────
    def card_timeline(self, i, t):
        seg, u, W, H = self.segments[i], self.u, self.W, self.H
        k = t - seg["start"]
        dur = seg["end"] - seg["start"]
        img = self.card_bg(i, t, (8, 30, 40))
        self.header(img, (seg.get("big") or "HOW WE GOT HERE").upper()[:30], (24, 131, 122), H * 0.14, k)
        d = ImageDraw.Draw(img)
        steps = (seg.get("steps") or [])[:4]
        x = W * 0.14
        top, bottom = H * 0.24, H * 0.60
        n = max(1, len(steps))
        line_p = ease_out(k / 0.6)
        d.line((x, top, x, top + (bottom - top) * line_p), fill=(255, 255, 255, 200), width=int(8 * u))
        slot = max(0.35, (dur - 0.5) / n)
        for j, st in enumerate(steps):
            a = ease_out((k - 0.2 - j * slot * 0.5) / 0.35)
            if a <= 0:
                break
            y = top + (bottom - top) * (j / max(1, n - 1) if n > 1 else 0.5)
            r = 20 * u * a
            d.ellipse((x - r, y - r, x + r, y + r), fill=self.c_accent)
            fw = font("Bold", int(44 * u))
            d.text((x + 50 * u - (1 - a) * 40 * u, y - 34 * u), str(st.get("when", ""))[:22], font=fw,
                   fill=self.c_accent + (int(255 * a),))
            fe, le, se = fit_text(str(st.get("what", "")), "Medium", int(W * 0.70), int(90 * u), int(40 * u), int(26 * u))
            draw_lines(d, le[:2], fe, se, x + 50 * u - (1 - a) * 40 * u, y + 18 * u, (255, 255, 255, int(255 * a)))
        return img

    # ── question: audience interaction ───────────────────────
    def card_question(self, i, t):
        seg, u, W, H = self.segments[i], self.u, self.W, self.H
        k = t - seg["start"]
        img = self.card_bg(i, t, mix(self.c_primary, (11, 19, 32), 0.55))
        self.header(img, "YOUR TURN", (11, 19, 32), H * 0.13, k)
        d = ImageDraw.Draw(img)
        q = seg.get("big") or seg["text"]
        fq, lq, sq = fit_text(q, "Bold", int(W * 0.84), int(H * 0.18), int(80 * u), int(40 * u), 1.08)
        a = ease_out(k / 0.35)
        draw_lines(d, lq, fq, sq, W * 0.08, H * 0.215 + (1 - a) * 30 * u, (255, 255, 255, int(255 * a)),
                   line_gap=1.08)
        y = H * 0.215 + len(lq) * sq * 1.08 + 40 * u
        opts = (seg.get("options") or [])[:3]
        letters = "ABC"
        for j, opt in enumerate(opts):
            b = ease_out_back((k - 0.35 - j * 0.22) / 0.35)
            if b <= 0:
                break
            bw, bh = W * 0.84, 104 * u
            x = W * 0.08 + (1 - b) * 120 * u
            d.rounded_rectangle((x, y, x + bw, y + bh), int(52 * u), fill=(255, 255, 255))
            d.ellipse((x + 16 * u, y + 14 * u, x + 92 * u, y + 90 * u), fill=self.c_primary)
            fl = font("Bold", int(44 * u))
            lw, _ = text_size(fl, letters[j])
            d.text((x + 54 * u - lw / 2, y + 18 * u), letters[j], font=fl, fill=(255, 255, 255))
            fo, lo, so = fit_text(str(opt), "Bold", int(bw - 140 * u), int(bh * 0.8), int(46 * u), int(26 * u))
            draw_lines(d, lo[:2], fo, so, x + 116 * u, y + (bh - len(lo[:2]) * so * 1.08) / 2 - 6 * u, (11, 19, 32))
            y += bh + 26 * u
        # "comment below" with a bouncing arrow
        c = clamp((k - 0.9) / 0.3)
        if c > 0:
            fc = font("Bold", int(42 * u))
            msg = "COMMENT YOUR ANSWER"
            tw, _ = text_size(fc, msg)
            yy = max(y + 10 * u, H * 0.56)
            d.text(((W - tw) / 2, yy), msg, font=fc, fill=self.c_accent + (int(255 * c),))
            bob = math.sin(t * 7) * 10 * u
            ax, ay = W / 2, yy + 74 * u + bob
            d.polygon([(ax - 26 * u, ay), (ax + 26 * u, ay), (ax, ay + 30 * u)], fill=self.c_accent + (int(255 * c),))
        return img
