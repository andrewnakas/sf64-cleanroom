"""Our radio/dialog font (fox_message.c): 1-bit glyphs, drawn at a 7 px advance, 15 px line pitch.

Storage (from the decomp's draw code): gTextCharTextures[k] is a 16x13 CI4 texture holding chars
4k..4k+3 as bit planes: char 4k+j is bit j of every texel; gTextCharPalettes[j] (code) shows bit j.
The rectangle starts at texel column 2, so a glyph occupies columns 2..14.
Glyphs are rasterised from Rubik SemiBold (OFL, games/sf64/fonts) and thresholded to 1 bit.
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
W, H, X0 = 16, 13, 2
BASE = 10          # baseline row
CHARS = {}         # msgChar -> str
for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    CHARS[24 + i] = c
for i, c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    CHARS[50 + i] = c
for i, c in enumerate("!?-,.0123456789'():"):
    CHARS[76 + i] = c
CHARS[95] = "e"   # placeholder slot in US (è in PAL)
SYMBOLS = {16: "cl", 17: "cu", 18: "cr", 19: "cd", 20: "au", 21: "al", 22: "ad", 23: "ar"}
TEX_ORDER = ["gTextCharSpecial0", "gTextCharSpecial4", "gTextCharSpecial8", "gTextCharSpecial12",
             "gTextCharCDIR", "gTextCharADIR", "gTextCharABCD", "gTextCharEFGH", "gTextCharIJKL",
             "gTextCharMNOP", "gTextCharQRST", "gTextCharUVWX", "gTextCharYZABBoth", "gTextCharCDEFLower",
             "gTextCharGHIJLower", "gTextCharKLMNLower", "gTextCharOPQRLower", "gTextCharSTUVLower",
             "gTextCharWXYZLower", "gTextCharPIDC", "gTextCharP012", "gTextChar3456", "gTextChar789A",
             "gTextCharPPDP"]


def _font(size):
    f = ImageFont.truetype(os.path.join(FONTS, "Rubik.ttf"), size)
    try:
        f.set_variation_by_name("SemiBold")
    except Exception:
        pass
    return f


def glyph(ch, size=11, thresh=0.42):
    """1-bit glyph in a 13x13 box (column 0 = texture column 2)."""
    ss = 4
    f = _font(size * ss)
    img = Image.new("L", (13 * ss, H * ss), 0)
    d = ImageDraw.Draw(img)
    asc = f.getmetrics()[0]
    bbox = d.textbbox((0, 0), ch, font=f)
    x = -bbox[0] + ss * 0
    d.text((x, BASE * ss - asc), ch, fill=255, font=f)
    a = np.asarray(img, np.float32).reshape(H, ss, 13, ss).mean((1, 3)) / 255.0
    m = a >= thresh
    # keep glyphs inside the 6 px advance (+1 px gap)
    cols = np.nonzero(m.any(0))[0]
    if len(cols) and cols[-1] > 5:
        # squeeze wide glyphs (M, W, m, w) horizontally
        src = a[:, :cols[-1] + 1]
        xs = np.linspace(0, src.shape[1] - 1, 6)
        sq = np.stack([np.interp(xs, np.arange(src.shape[1]), r) for r in src])
        m = np.zeros((H, 13), bool)
        m[:, :6] = sq >= thresh * 0.9
    cols = np.nonzero(m.any(0))[0]
    if len(cols):
        w = cols[-1] - cols[0] + 1
        shift = (6 - w) // 2 - cols[0]
        m = np.roll(m, shift, 1) if shift > 0 else m
    return m


def symbol(name):
    m = np.zeros((H, 13), bool)
    yy, xx = np.mgrid[0:H, 0:13]
    if name.startswith("c"):   # C button: ring with an arrow
        r = np.hypot(yy - 6, xx - 5.5)
        m |= (r <= 5.6) & (r >= 4.2)
    d = name[1]
    cx, cy = 5.5, 6
    if d == "u":
        m |= (yy >= 3) & (yy <= 7) & (np.abs(xx - cx) <= (yy - 3) * 0.7)
    elif d == "d":
        m |= (yy >= 4) & (yy <= 8) & (np.abs(xx - cx) <= (8 - yy) * 0.7)
    elif d == "l":
        m |= (xx >= 3) & (xx <= 7) & (np.abs(yy - cy) <= (xx - 3) * 0.7)
    elif d == "r":
        m |= (xx >= 3) & (xx <= 7) & (np.abs(yy - cy) <= (7 - xx) * 0.7)
    return m


def char_mask(code):
    if code in CHARS:
        return glyph(CHARS[code])
    if code in SYMBOLS:
        return symbol(SYMBOLS[code])
    return np.zeros((H, 13), bool)


def textures():
    """{symbol: (13, 16) uint8 CI4 index image}"""
    out = {}
    for k, sym in enumerate(TEX_ORDER):
        idx = np.zeros((H, W), np.uint8)
        for j in range(4):
            m = char_mask(4 * k + j)
            idx[:, X0:X0 + 13] |= (m.astype(np.uint8) << j)
        out[sym] = idx
    return out


def preview(text, path, scale=4):
    rev = {v: k for k, v in CHARS.items()}
    lines = text.split("\n")
    img = np.zeros((15 * len(lines) + 4, 7 * max(len(l) for l in lines) + 16, 3), np.uint8)
    img[:] = (10, 20, 70)
    for li, line in enumerate(lines):
        for i, ch in enumerate(line):
            if ch == " ":
                continue
            m = char_mask(rev.get(ch, 0))
            y, x = 2 + li * 15, 2 + i * 7
            sub = img[y:y + H, x:x + 13]
            sub[m[:sub.shape[0], :sub.shape[1]]] = 255
    Image.fromarray(np.repeat(np.repeat(img, scale, 0), scale, 1)).save(path)


if __name__ == "__main__":
    import sys
    preview("Fox, get this guy off me!\nDo a barrel roll! Press Z or R twice.\n"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789\nabcdefghijklmnopqrstuvwxyz !?-,.'():", sys.argv[1])
