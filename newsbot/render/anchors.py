"""Sam & Nina — original cartoon TV news anchors, drawn in vector (no external images).

Sam  : man, deep brown skin, short black hair and trimmed beard, navy suit, red tie.
Nina : woman, warm light-tan skin, long dark hair with side part, teal blazer, gold earrings.
"""
from __future__ import annotations

import functools

from PIL import Image, ImageDraw

from .common import mix

SS = 2  # supersampling for smooth edges

LOOKS = {
    "a": {  # Sam
        "skin": (141, 90, 59), "skin_dark": (112, 68, 43), "hair": (28, 24, 22),
        "suit": (31, 46, 77), "suit_dark": (21, 32, 56), "shirt": (244, 244, 248),
        "tie": (230, 57, 70), "lips": (96, 52, 40), "iris": (58, 36, 24),
    },
    "b": {  # Nina
        "skin": (232, 184, 148), "skin_dark": (206, 152, 116), "hair": (42, 26, 22),
        "suit": (24, 131, 122), "suit_dark": (16, 98, 92), "shirt": (250, 246, 240),
        "tie": None, "lips": (194, 87, 95), "iris": (70, 45, 30),
    },
}


@functools.lru_cache(maxsize=1024)
def anchor(who: str, size: int, mouth_q: int, blink: bool, look: int, active: bool, sober: bool):
    """Returns an RGBA bust (width=size, height=1.3*size). mouth_q 0..6, look -1/0/1."""
    L = LOOKS[who]
    S = size * SS
    H = int(S * 1.3)
    img = Image.new("RGBA", (S, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ink = (30, 24, 28)
    cx = S * 0.5

    # ── hair behind the head (Nina's long hair) ──
    if who == "b":
        d.rounded_rectangle((cx - S * .33, S * .16, cx + S * .33, S * .98), int(S * .16), fill=L["hair"])
        d.ellipse((cx - S * .34, S * .10, cx + S * .34, S * .62), fill=L["hair"])

    # ── torso ──
    top = S * .80
    d.rounded_rectangle((cx - S * .47, top, cx + S * .47, H + S * .2), int(S * .2), fill=L["suit"])
    # shirt / neckline
    d.polygon([(cx - S * .14, top - S * .02), (cx + S * .14, top - S * .02), (cx, top + S * .26)],
              fill=L["shirt"])
    # lapels
    d.polygon([(cx - S * .17, top - S * .03), (cx - S * .02, top + S * .30), (cx - S * .12, top + S * .40),
               (cx - S * .30, top + S * .02)], fill=L["suit_dark"])
    d.polygon([(cx + S * .17, top - S * .03), (cx + S * .02, top + S * .30), (cx + S * .12, top + S * .40),
               (cx + S * .30, top + S * .02)], fill=L["suit_dark"])
    if L["tie"]:
        d.polygon([(cx - S * .035, top + S * .01), (cx + S * .035, top + S * .01), (cx + S * .025, top + S * .05),
                   (cx - S * .025, top + S * .05)], fill=mix(L["tie"], (0, 0, 0), .2))
        d.polygon([(cx - S * .025, top + S * .05), (cx + S * .025, top + S * .05), (cx + S * .045, top + S * .24),
                   (cx, top + S * .29), (cx - S * .045, top + S * .24)], fill=L["tie"])
    else:  # Nina: delicate necklace
        d.arc((cx - S * .09, top - S * .08, cx + S * .09, top + S * .10), 20, 160, fill=(232, 190, 90),
              width=int(S * .008))
        d.ellipse((cx - S * .013, top + S * .085, cx + S * .013, top + S * .11), fill=(232, 190, 90))
    # lapel pin (channel red dot)
    d.ellipse((cx - S * .25, top + S * .12, cx - S * .21, top + S * .16), fill=(230, 57, 70))

    # ── neck ──
    d.rounded_rectangle((cx - S * .085, S * .62, cx + S * .085, top + S * .03), int(S * .04), fill=L["skin_dark"])

    # ── ears ──
    ey0 = S * .43
    for sx in (-1, 1):
        ex = cx + sx * S * .255
        d.ellipse((ex - S * .045, ey0 - S * .06, ex + S * .045, ey0 + S * .06), fill=L["skin_dark"])
        if who == "b":
            d.ellipse((ex - S * .016, ey0 + S * .06, ex + S * .016, ey0 + S * .095), fill=(232, 190, 90))

    # ── head ──
    d.ellipse((cx - S * .26, S * .14, cx + S * .26, S * .72), fill=L["skin"])

    # ── hair on top ──
    if who == "a":
        d.chord((cx - S * .27, S * .10, cx + S * .27, S * .52), 180, 360, fill=L["hair"])
        d.rectangle((cx - S * .27, S * .30, cx - S * .235, S * .42), fill=L["hair"])
        d.rectangle((cx + S * .235, S * .30, cx + S * .27, S * .42), fill=L["hair"])
        d.chord((cx - S * .245, S * .17, cx + S * .245, S * .36), 0, 180, fill=L["skin"])
        # trimmed beard
        d.chord((cx - S * .245, S * .30, cx + S * .245, S * .735), 15, 165, fill=mix(L["hair"], L["skin"], .25))
        d.ellipse((cx - S * .15, S * .52, cx + S * .15, S * .66), fill=L["skin"])
    else:
        d.pieslice((cx - S * .30, S * .08, cx + S * .22, S * .50), 180, 330, fill=L["hair"])
        d.pieslice((cx - S * .14, S * .09, cx + S * .30, S * .46), 220, 360, fill=L["hair"])
        d.polygon([(cx - S * .27, S * .30), (cx - S * .19, S * .22), (cx - S * .26, S * .62)], fill=L["hair"])

    # ── eyes ──
    ey = S * .42
    for sx in (-1, 1):
        ex = cx + sx * S * .105
        if blink:
            d.arc((ex - S * .055, ey - S * .03, ex + S * .055, ey + S * .03), 10, 170, fill=ink, width=int(S * .014))
            continue
        d.ellipse((ex - S * .055, ey - S * .045, ex + S * .055, ey + S * .045), fill=(255, 255, 255))
        px = ex + look * S * .018
        d.ellipse((px - S * .028, ey - S * .03, px + S * .028, ey + S * .03), fill=L["iris"])
        d.ellipse((px - S * .014, ey - S * .016, px + S * .014, ey + S * .016), fill=ink)
        d.ellipse((px + S * .004, ey - S * .022, px + S * .016, ey - S * .010), fill=(255, 255, 255))
        if who == "b":  # lashes
            d.arc((ex - S * .06, ey - S * .05, ex + S * .06, ey + S * .04), 195, 345, fill=ink, width=int(S * .012))
    # eyebrows
    lift = S * .018 if (active and not sober) else 0
    inner = -S * .014 if sober else 0  # sober: inner ends raised = concerned look
    for sx in (-1, 1):
        ex = cx + sx * S * .105
        d.line((ex - sx * S * .05, ey - S * .085 - lift + inner, ex + sx * S * .06, ey - S * .095 - lift),
               fill=L["hair"], width=int(S * (.02 if who == "a" else .014)))

    # ── nose ──
    d.arc((cx - S * .03, S * .45, cx + S * .03, S * .52), 20, 160, fill=L["skin_dark"], width=int(S * .012))

    # ── mouth ──
    my = S * .585
    if mouth_q == 0:
        if sober:
            d.line((cx - S * .05, my, cx + S * .05, my), fill=L["lips"], width=int(S * .012))
        else:
            d.arc((cx - S * .07, my - S * .045, cx + S * .07, my + S * .025), 25, 155, fill=L["lips"],
                  width=int(S * .014))
    else:
        h = S * (0.012 + 0.012 * mouth_q)
        w = S * (0.05 + 0.006 * mouth_q)
        d.rounded_rectangle((cx - w, my - h / 2, cx + w, my + h / 2), int(min(w, h / 2)), fill=(70, 22, 30))
        if mouth_q >= 2:
            d.rectangle((cx - w * .7, my - h / 2, cx + w * .7, my - h / 2 + S * .012), fill=(250, 250, 250))
        if mouth_q >= 4:
            d.ellipse((cx - w * .5, my, cx + w * .5, my + h / 2 - 1), fill=(214, 96, 104))
        if who == "b":
            d.rounded_rectangle((cx - w - S * .006, my - h / 2 - S * .006, cx + w + S * .006, my + h / 2 + S * .006),
                                int(min(w, h / 2)), outline=L["lips"], width=int(S * .01))
    # subtle cheeks
    if not sober:
        for sx in (-1, 1):
            ex = cx + sx * S * .16
            d.ellipse((ex - S * .04, S * .5, ex + S * .04, S * .54), fill=mix(L["skin"], (230, 90, 100), .25))

    return img.resize((size, int(size * 1.3)), Image.LANCZOS)
