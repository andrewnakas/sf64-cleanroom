"""Ending stills composed from our own portraits and type (316x240 RGBA16, drawn by fox_end2.c as full-screen rects).

aEndingNormalRewardTex   the cast, a grid of our character heads on black, "THANK YOU !" in pink
aEndingExpertRewardTex   the Star Fox team over the kept colour field (sunset), "GREAT!" on top
"""
import numpy as np
from PIL import Image, ImageDraw

from cleanroom.decomp.gen import upsample_grid

from . import labels, portraits

CAST = ["rob", "boss_co1", "pepper", "peppy", "pigma", "slippy", "boss_co2", "fox", "wolf", "shogun",
        "falco", "katt", "andross", "bill", "tanuki", "leon", "caiman", "andrew", "james", "spyborg"]


def _text(img, text, box, fill, weight="Black", outline=None):
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    px = int((y1 - y0) * 1.3)
    while px > 6:
        f = labels.font("rubik", px, weight)
        bb = d.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= x1 - x0 and bb[3] - bb[1] <= y1 - y0:
            break
        px -= 1
    x = x0 + (x1 - x0 - (bb[2] - bb[0])) / 2 - bb[0]
    y = y0 + (y1 - y0 - (bb[3] - bb[1])) / 2 - bb[1]
    if outline:
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                d.text((x + dx, y + dy), text, fill=outline, font=f)
    d.text((x, y), text, fill=fill, font=f)


def _head(who, size):
    a = portraits.draw(who, False, size, size, frame=False)
    im = Image.fromarray(a, "RGBA")
    # round vignette so heads float on the background
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse([1, 1, size - 2, size - 2], fill=255)
    im.putalpha(m)
    return im


def normal(w, h):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    cols, s = 5, 40
    for i, who in enumerate(CAST):
        r, c = divmod(i, cols)
        x = 18 + c * (w - 36 - s) // (cols - 1) + (8 if r % 2 else -8)
        y = 10 + r * 44
        img.alpha_composite(_head(who, s), (int(x), int(y)))
    _text(img, "THANK YOU !", (20, 190, w - 20, 232), (250, 120, 220, 255), outline=(60, 0, 60, 255))
    return np.asarray(img)


def expert(w, h, e):
    n = int(round(len(e["grid"]) ** 0.5))
    bg = upsample_grid(e["grid"], n, w, h)
    rng = np.random.default_rng(7)   # our own dither: smooth gradients otherwise match retail texel runs
    bg[..., :3] += rng.uniform(-12, 12, (h, w, 1)) + rng.uniform(-4, 4, (h, w, 3))
    bg = np.clip(bg, 0, 255).astype(np.uint8)
    bg[..., 3] = 255
    img = Image.fromarray(bg, "RGBA")
    for i, who in enumerate(["peppy", "slippy", "fox", "falco"]):
        s = 84 if who == "fox" else 70
        x = [24, 88, 150, 228][i]
        y = 240 - s - 30 - (10 if who == "fox" else 0)
        img.alpha_composite(_head(who, s), (x, y))
    _text(img, "GREAT!", (30, 10, w - 30, 90), (250, 250, 250, 255), outline=(40, 30, 60, 255))
    return np.asarray(img)


def hook(sym, e):
    if sym == "aEndingNormalRewardTex":
        return normal(e["w"], e["h"])
    if sym == "aEndingExpertRewardTex":
        return expert(e["w"], e["h"], e)
    return None
