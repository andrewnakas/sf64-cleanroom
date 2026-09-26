"""Title logos drawn from our own design (fonts: Rubik, OFL).

aTitleStarfoxLogoTex 236x60   "STARFOX" wordmark: italic heavy letters, green->yellow gradient, navy rim
aTitle64Logo*        (not drawn here: UV-mapped onto the 3D "64" mesh; the default grid + outline reads right)
aTitleN64LogoTex 128x88       "NINTENDO 64" text logo on a simple four-colour cube
aGreatFoxLogoTex / aGreatFoxStarfoxLogoTex / aOptInvoiceSealTex: fox-head emblem
"""
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import labels

SS = 4


def _text_layer(text, W, H, weight="Black", italic=0.22, fill_h=0.9):
    img = Image.new("L", (W * SS, H * SS), 0)
    d = ImageDraw.Draw(img)
    px = int(H * SS * 1.2)
    while px > 8:
        f = labels.font("rubik", px, weight)
        bb = d.textbbox((0, 0), text, font=f)
        if bb[2] - bb[0] <= W * SS * (0.94 - italic * 0.4) and bb[3] - bb[1] <= H * SS * fill_h:
            break
        px = int(px * 0.95)
    d.text(((W * SS - (bb[2] - bb[0])) / 2 - bb[0], (H * SS - (bb[3] - bb[1])) / 2 - bb[1]), text, fill=255, font=f)
    if italic:
        img = img.transform(img.size, Image.AFFINE, (1, italic, -italic * H * SS / 2, 0, 1, 0), Image.BICUBIC)
    return np.asarray(img, np.float32) / 255.0


def _down(a):
    h, w = a.shape[0] // SS, a.shape[1] // SS
    return a.reshape(h, SS, w, SS, *a.shape[2:]).mean((1, 3))


def _dilate(m, r):
    im = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * r + 1))
    return np.asarray(im, np.float32) / 255.0


def starfox(w, h):
    m = _text_layer("STARFOX", w, h, italic=0.25, fill_h=0.8)
    rim = np.clip(_dilate(m, 3 * SS // 2) - m, 0, 1)
    yy = np.linspace(0, 1, m.shape[0])[:, None, None]
    top, bot = np.array([250, 240, 60]), np.array([40, 190, 60])
    col = top * (1 - yy) + bot * yy
    col = col * np.ones((1, m.shape[1], 1))
    navy = np.array([20, 30, 110])
    a = np.clip(m + rim, 0, 1)
    rgb = (col * m[..., None] + navy * rim[..., None]) / np.maximum(a[..., None], 1e-3)
    out = np.concatenate([_down(rgb), _down(a)[..., None] * 255], -1)
    return np.clip(out, 0, 255).astype(np.uint8)


def sixty_four(w, h, strips=7):
    W = w * strips
    m0 = _text_layer("64", h * 2, h, italic=0.3, fill_h=0.98)
    cols = np.nonzero(m0.max(0) > 0.05)[0]
    m0 = m0[:, cols[0]:cols[-1] + 1]
    img = Image.fromarray((m0 * 255).astype(np.uint8)).resize((int(W * SS * 0.86), h * SS), Image.BICUBIC)
    m = np.zeros((h * SS, W * SS), np.float32)
    x0 = (W * SS - img.size[0]) // 2
    m[:, x0:x0 + img.size[0]] = np.asarray(img, np.float32) / 255.0
    side = np.clip(_dilate(np.roll(np.roll(m, 3 * SS, 1), 2 * SS, 0), SS) - m, 0, 1)
    a = np.clip(m + side, 0, 1)
    yy = np.linspace(0, 1, m.shape[0])[:, None, None]
    face = np.array([240, 50, 40]) * (1 - yy * 0.4) + np.array([255, 150, 140]) * (1 - yy) * 0.2
    face = face * np.ones((1, m.shape[1], 1))
    rgb = (face * m[..., None] + np.array([120, 10, 20]) * side[..., None]) / np.maximum(a[..., None], 1e-3)
    full = np.concatenate([_down(rgb), _down(a)[..., None] * 255], -1)
    return [np.clip(full[:, i * w:(i + 1) * w], 0, 255).astype(np.uint8) for i in range(strips)]


def n64(w, h):
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy, s = w * SS / 2, h * SS * 0.62, h * SS * 0.28
    cols = [(230, 40, 40), (40, 160, 60), (40, 80, 200), (240, 190, 30)]
    pts = [(cx - s, cy - s * 0.5), (cx, cy - s), (cx + s, cy - s * 0.5), (cx, cy)]
    d.polygon(pts, fill=cols[3])
    d.polygon([(cx - s, cy - s * 0.5), (cx, cy), (cx, cy + s), (cx - s, cy + s * 0.5)], fill=cols[0])
    d.polygon([(cx + s, cy - s * 0.5), (cx, cy), (cx, cy + s), (cx + s, cy + s * 0.5)], fill=cols[2])
    d.line([(cx, cy), (cx, cy + s)], fill=cols[1], width=int(SS * 2))
    f = labels.font("rubik", int(h * SS * 0.16), "Black")
    t = "NINTENDO 64"
    bb = d.textbbox((0, 0), t, font=f)
    d.text((cx - (bb[2] - bb[0]) / 2 - bb[0], h * SS * 0.04 - bb[1]), t, fill=(200, 200, 210, 255), font=f)
    return np.asarray(img.resize((w, h), Image.LANCZOS))


def emblem(w, h, e):
    """A stylised fox head in a circle (Star Fox team emblem stand-in)."""
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fg, bg = labels.colours(e)
    fg = tuple(int(v) for v in fg)
    if bg is not None:
        d.rectangle([0, 0, w * SS, h * SS], fill=tuple(int(v) for v in bg) + (255,))
    cx, cy, r = w * SS / 2, h * SS / 2, min(w, h) * SS * 0.45
    pts = [(cx - r, cy - r * 0.8), (cx - r * 0.35, cy - r * 0.2), (cx + r * 0.35, cy - r * 0.2), (cx + r, cy - r * 0.8),
           (cx + r * 0.75, cy + r * 0.1), (cx, cy + r * 0.9), (cx - r * 0.75, cy + r * 0.1)]
    d.polygon(pts, fill=fg + (255,))
    return np.asarray(img.resize((w, h), Image.LANCZOS))


_STRIPS = {}


def hook(sym, e):
    w, h = e.get("w"), e.get("h")
    if sym == "aTitleStarfoxLogoTex":
        return starfox(w, h)
    m = None   # the "64" pieces are UV-mapped onto a 3D mesh (aTitle64LogoDL): grid + outline default
    if m:
        i = int(m.group(2) or m.group(3)) - 1
        key = (w, 64)
        if key not in _STRIPS:
            _STRIPS[key] = sixty_four(w, 64)
        s = _STRIPS[key][i]
        return s[:h] if h <= 64 else s
    if sym == "aTitleN64LogoTex":
        return n64(w, h)
    if sym in ("aGreatFoxLogoTex", "aGreatFoxStarfoxLogoTex", "aOptInvoiceSealTex"):
        return emblem(w, h, e)
    return None
