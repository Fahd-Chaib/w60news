"""Outils de rendu partagés : polices, texte, fonds, sous-titres, encodage ffmpeg."""
from __future__ import annotations

import functools
import json
import math
import random
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import ASSETS, FONTS

FPS = 30
END_CARD = 1.8  # secondes


# ── couleurs / easing ───────────────────────────────────────
def rgb(hex_color: str, alpha: int | None = None):
    h = hex_color.lstrip("#")
    c = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return c + (alpha,) if alpha is not None else c


def mix(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_out_back(t):
    t = clamp(t)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


def ease_in_out(t):
    t = clamp(t)
    return 3 * t * t - 2 * t * t * t


# ── polices ─────────────────────────────────────────────────
@functools.lru_cache(maxsize=256)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"Poppins-{weight}.ttf"), max(8, int(size)))


def text_size(fnt, text):
    l, t, r, b = fnt.getbbox(text)
    return r - l, b - t


def wrap(text: str, fnt, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        cand = f"{cur} {word}".strip()
        if text_size(fnt, cand)[0] <= max_w or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(text, weight, max_w, max_h, start_size, min_size=24, line_gap=1.08):
    """Plus grande taille de police qui fait tenir le texte dans la boîte."""
    size = start_size
    while size >= min_size:
        f = font(weight, size)
        lines = wrap(text, f, max_w)
        h = len(lines) * size * line_gap
        if h <= max_h and all(text_size(f, ln)[0] <= max_w for ln in lines):
            return f, lines, size
        size -= 4
    f = font(weight, min_size)
    return f, wrap(text, f, max_w), min_size


def draw_lines(draw, lines, fnt, size, x, y, fill, align="left", max_w=0, line_gap=1.08,
               stroke=0, stroke_fill=None):
    for i, ln in enumerate(lines):
        w, _ = text_size(fnt, ln)
        lx = x + (max_w - w) / 2 if align == "center" else x + (max_w - w) if align == "right" else x
        draw.text((lx, y + i * size * line_gap), ln, font=fnt, fill=fill,
                  stroke_width=stroke, stroke_fill=stroke_fill)


def text_layer(lines, fnt, size, fill, align="center", line_gap=1.08, stroke=0,
               stroke_fill=(0, 0, 0), shadow=True, pad=None):
    """Bloc de texte sur calque transparent (pour animer échelle/position)."""
    pad = pad if pad is not None else int(size * 0.25) + stroke
    w = max(text_size(fnt, ln)[0] for ln in lines) + 2 * pad
    h = int(len(lines) * size * line_gap + size * 0.35) + 2 * pad
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_lines(ImageDraw.Draw(sh), lines, fnt, size, pad, pad + size * 0.06, (0, 0, 0, 150),
                   align, w - 2 * pad, line_gap)
        layer = Image.alpha_composite(layer, sh.filter(ImageFilter.GaussianBlur(size * 0.08)))
    draw_lines(ImageDraw.Draw(layer), lines, fnt, size, pad, pad, fill, align, w - 2 * pad,
               line_gap, stroke, stroke_fill)
    return layer


def paste_scaled(base: Image.Image, layer: Image.Image, cx, cy, scale=1.0, alpha=1.0):
    if scale <= 0.01 or alpha <= 0.01:
        return
    if abs(scale - 1) > 0.01:
        layer = layer.resize((max(1, int(layer.width * scale)), max(1, int(layer.height * scale))),
                             Image.BILINEAR)
    if alpha < 0.99:
        a = layer.getchannel("A").point(lambda v: int(v * alpha))
        layer = layer.copy()
        layer.putalpha(a)
    base.alpha_composite(layer, (int(cx - layer.width / 2), int(cy - layer.height / 2)))


def rounded(size, radius, fill):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=fill)
    return img


# ── fonds ───────────────────────────────────────────────────
def gradient(W, H, top, bottom):
    t = np.linspace(0, 1, H)[:, None, None]
    arr = (np.array(top)[None, None, :] * (1 - t) + np.array(bottom)[None, None, :] * t)
    arr = np.repeat(arr, W, axis=1).astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


def generated_backdrop(W, H, seed: int, c1, c2, accent):
    """Fond abstrait 'salle de rédaction' quand aucune photo n'est disponible."""
    rnd = random.Random(seed)
    img = gradient(W, H, c1, c2)
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    step = int(min(W, H) / 12)
    for x in range(0, W, step):
        d.line([(x, 0), (x, H)], fill=(255, 255, 255, 14), width=1)
    for y in range(0, H, step):
        d.line([(0, y), (W, y)], fill=(255, 255, 255, 14), width=1)
    blobs = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    db = ImageDraw.Draw(blobs)
    for _ in range(7):
        r = rnd.randint(int(W * .15), int(W * .5))
        x, y = rnd.randint(-r, W), rnd.randint(-r, H)
        db.ellipse((x, y, x + r, y + r), fill=accent + (rnd.randint(22, 45),))
    img.alpha_composite(blobs.filter(ImageFilter.GaussianBlur(min(W, H) / 30)))
    img.alpha_composite(over)
    return img


def load_cover(path, W, H, overscan=1.12):
    """Charge une photo recadrée pour couvrir W×H avec marge pour le Ken Burns."""
    im = Image.open(path).convert("RGB")
    tw, th = int(W * overscan), int(H * overscan)
    s = max(tw / im.width, th / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    l, t = (im.width - tw) // 2, (im.height - th) // 2
    return im.crop((l, t, l + tw, t + th)).convert("RGBA")


def ken_burns(cover: Image.Image, W, H, p: float, direction: int = 0):
    """p ∈ [0,1] : progression du zoom lent dans la photo."""
    p = clamp(p)
    zoom = 1.0 + 0.10 * p if direction % 2 == 0 else 1.10 - 0.10 * p
    cw = int(cover.width / zoom)
    ch = int(cover.height / zoom)
    dx = (cover.width - cw) * (0.5 + (0.25 if direction in (1, 2) else -0.25) * (p - 0.5))
    dy = (cover.height - ch) * 0.5
    crop = cover.crop((int(dx), int(dy), int(dx) + cw, int(dy) + ch))
    return crop.resize((W, H), Image.BILINEAR)


# ── audio : enveloppe pour l'animation des bouches ─────────
def audio_envelope(wav_path: Path, timeline: dict, duration: float):
    n = int(math.ceil(duration * FPS))
    env = np.zeros(n)
    if not timeline.get("silent"):
        with wave.open(str(wav_path)) as wf:
            sr = wf.getframerate()
            a = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32)
        hop = sr // FPS
        for i in range(n):
            chunk = a[i * hop:(i + 1) * hop]
            if len(chunk):
                env[i] = np.sqrt(np.mean(chunk ** 2))
        if env.max() > 0:
            env = np.clip(env / (np.percentile(env[env > 0], 90) + 1e-6), 0, 1)
            return env
    # mode silencieux : bouche qui s'anime sur chaque mot estimé
    for seg in timeline["segments"]:
        for w in seg["words"]:
            a, b = int(w["start"] * FPS), int(w["end"] * FPS)
            for i in range(a, min(b, n)):
                env[i] = 0.35 + 0.65 * abs(math.sin((i - a) / max(1, b - a) * math.pi * 2))
    return env


# ── sous-titres karaoké ─────────────────────────────────────
def caption_chunks(timeline, max_words=3, max_chars=18):
    chunks = []
    for seg in timeline["segments"]:
        cur = []
        for w in seg["words"]:
            cur.append(w)
            txt = " ".join(x["w"] for x in cur)
            if len(cur) >= max_words or len(txt) >= max_chars or w["w"][-1:] in ".,!?;:":
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        end = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else c[-1]["end"] + 0.3
        out.append({"words": c, "start": c[0]["start"], "end": min(end, c[-1]["end"] + 0.6)})
    return out


class Captions:
    def __init__(self, timeline, size, max_w, color=(255, 255, 255), hi_bg=(255, 209, 102),
                 hi_fg=(11, 19, 32), upper=True):
        self.chunks = caption_chunks(timeline)
        self.size, self.max_w = size, max_w
        self.color, self.hi_bg, self.hi_fg, self.upper = color, hi_bg, hi_fg, upper
        self.cache = {}

    def _render(self, ci, wi):
        key = (ci, wi)
        if key in self.cache:
            return self.cache[key]
        words = [w["w"].upper() if self.upper else w["w"] for w in self.chunks[ci]["words"]]
        f = font("Bold", self.size)
        space = text_size(f, " ")[0] * 1.1 + self.size * 0.32
        widths = [text_size(f, w)[0] for w in words]
        total = sum(widths) + space * (len(words) - 1)
        scale = min(1.0, self.max_w / max(total, 1))
        if scale < 1:
            f = font("Bold", int(self.size * scale))
            space *= scale
            widths = [text_size(f, w)[0] for w in words]
            total = sum(widths) + space * (len(words) - 1)
        pad = int(self.size * 0.35)
        h = int(self.size * 1.5) + 2 * pad
        layer = Image.new("RGBA", (int(total) + 2 * pad, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        x = pad
        for i, (w, ww) in enumerate(zip(words, widths)):
            if i == wi:
                d.rounded_rectangle((x - pad * .45, pad * .55, x + ww + pad * .45, h - pad * .35),
                                    int(self.size * .22), fill=self.hi_bg)
                d.text((x, pad), w, font=f, fill=self.hi_fg)
            else:
                d.text((x, pad), w, font=f, fill=self.color, stroke_width=max(3, self.size // 11),
                       stroke_fill=(0, 0, 0))
            x += ww + space
        self.cache[key] = layer
        return layer

    def draw(self, base, t, cx, cy):
        for ci, c in enumerate(self.chunks):
            if c["start"] <= t < c["end"]:
                wi = max((i for i, w in enumerate(c["words"]) if w["start"] <= t), default=0)
                pop = ease_out_back((t - c["start"]) / 0.18)
                paste_scaled(base, self._render(ci, wi), cx, cy, 0.85 + 0.15 * pop)
                return


# ── encodage ────────────────────────────────────────────────
def music_track(cfg=None):
    if cfg is not None and not cfg.get_path("music.enabled", True):
        return None
    folder = ASSETS / "music"
    tracks = sorted(folder.glob("*.mp3")) + sorted(p for p in folder.glob("*.wav") if p.name != "news_bed.wav")
    if tracks:  # your own royalty-free tracks take priority
        return random.choice(tracks)
    from ..music import ensure
    return ensure()


def encode(frames, W, H, total, audio: Path, out: Path, music=None, music_vol=0.07, delay=0.0,
           sting=None):
    """Video from frames + voice track (shifted by `delay` s), optional looped music bed and intro sting."""
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(audio)]
    ms = int(delay * 1000)
    chains = [f"[1:a]aformat=channel_layouts=stereo,adelay={ms}|{ms},apad[v]"]
    mixes = ["[v]"]
    idx = 2
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        chains.append(f"[{idx}:a]aformat=channel_layouts=stereo,volume={music_vol},adelay={ms}|{ms},"
                      f"afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5[m]")
        mixes.append("[m]")
        idx += 1
    if sting:
        cmd += ["-i", str(sting)]
        chains.append(f"[{idx}:a]aformat=channel_layouts=stereo,volume=0.9[s]")
        mixes.append("[s]")
        idx += 1
    graph = ";".join(chains) + ";" + "".join(mixes) + \
        f"amix=inputs={len(mixes)}:duration=first:normalize=0[a]"
    cmd += ["-filter_complex", graph, "-map", "0:v", "-map", "[a]"]
    cmd += ["-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for frame in frames:
            proc.stdin.write(frame.convert("RGB").tobytes())
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg failed")
    return out


def load_timeline(folder: Path):
    return json.loads((folder / "timeline.json").read_text("utf-8"))
