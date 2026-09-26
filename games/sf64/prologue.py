"""Map prologue stills (aMapPrologue1..7Tex, 96x52) and the briefing picture, composed from our own drawings:
starfield backgrounds, our planet surfaces and our character portraits, following the prologue text:
1 Corneria in space, 2 Andross, 3 James / Peppy / Pigma sent to Venom, 4 battle over Venom, 5 Venom,
6 Andross unleashes his army, 7 the new Star Fox team.
"""
import re

import numpy as np
from PIL import Image, ImageDraw

from cleanroom.decomp.gen import h32

from . import planets, portraits


def _stars(w, h, seed, tint=(0, 0, 0)):
    rng = np.random.default_rng(seed)
    img = np.zeros((h, w, 4), np.uint8)
    img[..., :3] = tint
    img[..., 3] = 255
    for _ in range(w * h // 40):
        x, y = rng.integers(0, w), rng.integers(0, h)
        v = rng.integers(120, 255)
        img[y, x, :3] = (v, v, min(255, v + 20))
    return Image.fromarray(img, "RGBA")


def _planet(size, colours, seed):
    e = {"w": size, "h": size, "grid": [list(c) + [255] for c in colours]}
    tex = planets.surface(f"prologue{seed}", e)
    yy, xx = np.mgrid[0:size, 0:size]
    r = np.hypot(xx - size / 2 + 0.5, yy - size / 2 + 0.5) / (size / 2)
    shade = np.clip(1.15 - 0.9 * np.hypot(xx / size - 0.35, yy / size - 0.35), 0.15, 1.1)
    out = tex.astype(np.float32)
    out[..., :3] *= shade[..., None]
    out[..., 3] = np.clip((1 - r) * size / 2, 0, 1) * 255
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def _head(who, size, open_=False):
    im = Image.fromarray(portraits.draw(who, open_, size, size, frame=False), "RGBA")
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).ellipse([0, 0, size - 1, size - 1], fill=255)
    im.putalpha(m)
    return im


CORNERIA = [(40, 90, 170), (60, 120, 190), (230, 235, 240), (90, 140, 80)] * 4
VENOM = [(160, 60, 30), (200, 90, 40), (90, 30, 20), (230, 140, 60)] * 4


def still(i, w, h):
    img = _stars(w, h, h32("pro", i))
    d = ImageDraw.Draw(img)
    if i == 1:
        img.alpha_composite(_planet(44, CORNERIA, 1), (26, 4))
    elif i == 2:
        img = _stars(w, h, 2, (40, 10, 5))
        img.alpha_composite(_head("andross", 46), (25, 3))
    elif i == 3:
        for k, who in enumerate(["peppy", "james", "pigma"]):
            img.alpha_composite(_head(who, 30), (4 + k * 31, 11))
    elif i == 4:
        img.alpha_composite(_planet(60, VENOM, 4), (18, 20))
        for k in range(5):
            x, y = 10 + k * 17, 6 + (k % 2) * 8
            d.polygon([(x, y + 4), (x + 8, y), (x + 8, y + 8)], fill=(200, 40, 40, 255))
        d.ellipse([60, 14, 72, 26], fill=(255, 200, 80, 255))
    elif i == 5:
        img.alpha_composite(_planet(40, VENOM, 5), (28, 6))
    elif i == 6:
        img = _stars(w, h, 6, (30, 5, 5))
        img.alpha_composite(_head("andross", 40, True), (28, 6))
        for x in (6, 76):
            d.polygon([(x, 44), (x + 7, 20), (x + 14, 44)], fill=(150, 90, 60, 255))
    elif i == 7:
        for k, who in enumerate(["falco", "fox", "peppy", "slippy"]):
            s = 30 if who == "fox" else 24
            img.alpha_composite(_head(who, s), ([2, 24, 52, 72][k], 26 - s // 2 + (0 if who == "fox" else 4)))
    return np.asarray(img)


def hook(sym, e):
    m = re.fullmatch(r"aMapPrologue(\d)Tex", sym)
    if m:
        return still(int(m.group(1)), e["w"], e["h"])
    if sym == "aMapBriefingFoxTex":
        img = _stars(e["w"], e["h"], 9, (10, 20, 40))
        img.alpha_composite(_head("fox", min(e["h"] - 4, 44)), (e["w"] // 2 - 22, 3))
        return np.asarray(img)
    return None
