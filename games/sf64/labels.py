"""Re-typeset text-bearing textures (games/sf64/text_labels.json) with our own fonts.

Label entry: "text" (lines split by \\n), or {"text": ..., "font": "rubik|jp|mono", "italic": bool,
"weights": [line size ratios], "align": "center|left", "outline": bool, "fg": [r,g,b], "bg": [r,g,b]}.
Colours come from the kept 4x4 grid: with an alpha outline, text is the mean colour of the opaque cells on
transparency; without, the most common cell colour is the panel and the farthest cell colour is the ink.
Fonts: Rubik (OFL), M PLUS Rounded 1c (OFL) for Japanese, in games/sf64/fonts.
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
LABELS = os.path.join(HERE, "text_labels.json")
SS = 4


def font(kind, px, weight="Bold"):
    if kind == "jp":
        return ImageFont.truetype(os.path.join(FONTS, "MPLUSRounded1c-ExtraBold.ttf"), px)
    if kind == "mono":
        return ImageFont.truetype(os.path.join(FONTS, "PressStart2P-Regular.ttf"), px)
    f = ImageFont.truetype(os.path.join(FONTS, "Rubik.ttf"), px)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass
    return f


def colours(e):
    g = np.asarray(e["grid"], np.float32)
    if e.get("fmt", "").startswith("IA") and "alpha2" in e:
        return np.array([255.0, 255.0, 255.0]), None   # intensity art: the game tints it
    if "alpha2" in e:
        # cell colours average in the transparent texels too: undo that, then weight by coverage
        a = g[:, 3:4] / 255.0
        ok = a[:, 0] > 0.08
        if not ok.any():
            return np.array([255.0, 255.0, 255.0]), None
        rgb = np.clip(g[ok, :3] / a[ok], 0, 255)
        fg = (rgb * a[ok]).sum(0) / a[ok].sum()
        return fg, None
    rgb = g[:, :3]
    bg = np.median(rgb, 0)
    far = rgb[np.argmax(((rgb - bg) ** 2).sum(1))]
    if ((far - bg) ** 2).sum() < 40 ** 2:
        far = np.array([0, 0, 0]) if bg.mean() > 128 else np.array([255, 255, 255])
    return far, bg


def _is_jp(s):
    return any(ord(c) > 0x2E80 for c in s)


def render(label, w, h, e=None):
    if isinstance(label, str):
        label = {"text": label}
    text = label["text"]
    lines = text.split("\n")
    kind = label.get("font") or ("jp" if _is_jp(text) else "rubik")
    ratios = label.get("weights") or ([1.0] if len(lines) == 1 else [1.0] + [0.72] * (len(lines) - 1))
    ratios = np.asarray(ratios[:len(lines)], np.float32)
    fg, bg = colours(e) if e is not None else (np.array([255, 255, 255]), None)
    if "fg" in label:
        fg = np.asarray(label["fg"], np.float32)
    if "bg" in label:
        bg = np.asarray(label["bg"], np.float32)
    W, H = w * SS, h * SS
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    pad = max(1, int(0.04 * H)) if len(lines) == 1 else 0
    avail = H - 2 * pad
    line_h = avail * ratios / ratios.sum()
    y = pad
    for ln, lh in zip(lines, line_h):
        if not ln.strip():
            y += lh
            continue
        px = max(4, int(lh * 1.25))
        while px > 4:
            f = font(kind, px)
            bb = d.textbbox((0, 0), ln, font=f)
            tw, th = bb[2] - bb[0], bb[3] - bb[1]
            if tw <= W * 0.97 and th <= lh * 0.92:
                break
            px -= max(1, px // 16)
        x = (W - tw) / 2 - bb[0] if label.get("align", "center") == "center" else SS - bb[0]
        d.text((x, y + (lh - th) / 2 - bb[1]), ln, fill=255, font=f)
        y += lh
    m = np.asarray(mask, np.float32).reshape(h, SS, w, SS).mean((1, 3)) / 255.0
    if label.get("italic"):
        sh = np.zeros_like(m)
        for r in range(h):
            s = int(round((h / 2 - r) * 0.25))
            sh[r] = np.roll(m[r], s)
        m = sh
    img = np.zeros((h, w, 4), np.float32)
    if "grad" in label:   # banner style: vertical gradient fill with a coloured rim
        top, bot = (np.asarray(c, np.float32) for c in label["grad"])
        yy = np.linspace(0, 1, h)[:, None, None]
        fillc = top * (1 - yy) + bot * yy
        r = int(label.get("rim_w", 1))
        dil = m
        for _ in range(r):
            dil = np.maximum.reduce([np.roll(np.roll(dil, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
        rim = np.clip(dil - m, 0, 1)
        a = np.clip(m + rim, 0, 1)
        rc = np.asarray(label.get("rim", [150, 20, 20]), np.float32)
        img[..., :3] = (fillc * m[..., None] + rc * rim[..., None]) / np.maximum(a[..., None], 1e-3)
        img[..., 3] = a * 255
        return np.clip(img, 0, 255).astype(np.uint8)
    if bg is None:
        img[..., :3] = fg
        img[..., 3] = np.clip(m * 1.15, 0, 1) * 255
        if label.get("outline", not (e or {}).get("fmt", "").startswith("IA")) and fg.mean() > 150:
            # thin dark rim so white text reads on bright scenes
            dil = np.maximum.reduce([np.roll(np.roll(m, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)])
            rim = np.clip(dil - m, 0, 1)
            a = np.clip(m + rim * 0.8, 0, 1)
            col = (fg[None, None] * m[..., None] + np.array([20, 20, 40])[None, None] * rim[..., None] * 0.8)
            img[..., :3] = col / np.maximum(a[..., None], 1e-3)
            img[..., 3] = a * 255
    else:
        img[..., :3] = bg[None, None] * (1 - m[..., None]) + fg[None, None] * m[..., None]
        img[..., 3] = 255
    return np.clip(img, 0, 255).astype(np.uint8)


_L = None


def labels():
    global _L
    if _L is None:
        _L = json.load(open(LABELS, encoding="utf-8")) if os.path.exists(LABELS) else {}
    return _L


def hook(sym, e):
    lab = labels().get(sym)
    if lab is None:
        return None
    return render(lab, e["w"], e["h"], e)
