"""Font glyph textures drawn by the game's text routines (fox_std_lib.c), redrawn with our fonts.

Character <- texture mapping comes from the decomp's tables, not the symbol names:
  sLargeChars "ABCDEFGHIJKLMNOPQRSTUVWXYZ. 0123456789st-" -> sLargeCharTex (large 'O' is aSmallText_O),
      advance widths sLargeCharWidths; drawn 15 px tall.
  sSmallChars " ABCDEFGHIJKLMNOPQRSTUVWXYZ!:-.0123456789" -> sSmallCharTex (aSmallText_o_/p/q/r/s are capitals);
      8 px tall, letters 8 wide, digits 16 wide.
  aHudNumber_<n> (CI4 16x8, one TLUT each) and sLargeText_1997_<n>: digits.
"""
import re

import numpy as np
from PIL import Image, ImageDraw

from . import labels

LARGE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ. 0123456789st-"
LARGE_TEX = ("aLargeText_A aLargeText_B aLargeText_C aLargeText_D aLargeText_E aLargeText_F aLargeText_G "
             "aLargeText_H aLargeText_I aLargeText_J aLargeText_K aLargeText_L aLargeText_M aLargeText_N "
             "aSmallText_O aLargeText_P aLargeText_Q aLargeText_R aLargeText_S aLargeText_T aLargeText_U "
             "aLargeText_V aLargeText_W aLargeText_X aLargeText_Y aLargeText_Z aLargeText_DOT - "
             "aLargeText_0 aLargeText_1 aLargeText_2 aLargeText_3 aLargeText_4 aLargeText_5 aLargeText_6 "
             "aLargeText_7 aLargeText_8 aLargeText_9 aLargeText_s_ aLargeText_t_ aLargeText_HYPHEN").split()
LARGE_W = [15, 14, 14, 13, 13, 13, 14, 14, 5, 12, 14, 12, 16, 14, 15, 13, 16, 14, 13, 13, 13,
           16, 17, 17, 16, 13, 5, 16, 13, 13, 13, 13, 13, 13, 13, 13, 13, 13, 10, 9, 14]
SMALL_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZ!:-.0123456789"
SMALL_TEX = ("- aSmallText_A aSmallText_B aSmallText_C aSmallText_D aSmallText_E aSmallText_F aSmallText_G "
             "aSmallText_H aSmallText_I aSmallText_J aSmallText_K aSmallText_L aSmallText_M aSmallText_N "
             "aSmallText_o_ aSmallText_p aSmallText_q aSmallText_r aSmallText_s aSmallText_T aSmallText_U "
             "aSmallText_V aSmallText_W aSmallText_X aSmallText_Y aSmallText_Z aSmallTextExclamMark "
             "aSmallText_COLON aSmallText_HYPHEN aSmallText_DOT aSmallText_0 aSmallText_1 aSmallText_2 "
             "aSmallText_3 aSmallText_4 aSmallText_5 aSmallText_6 aSmallText_7 aSmallText_8 aSmallText_9").split()

GLYPHS = {}   # symbol -> (char, advance px, drawn height)
for c, t, w in zip(LARGE_CHARS, LARGE_TEX, LARGE_W):
    if t != "-":
        GLYPHS[t] = (c, w - 1, 15)
for i, (c, t) in enumerate(zip(SMALL_CHARS, SMALL_TEX)):
    if t != "-":
        GLYPHS[t] = (c, 7 if i <= 30 else 7, 8)


def draw_glyph(ch, w, h, adv, cap):
    """White glyph mask (h, w): cap-height `cap`, left-aligned in `adv` columns."""
    ss = 8
    img = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(img)
    px = int(cap * ss * 1.38)
    for _ in range(30):
        f = labels.font("rubik", px, "Bold")
        bb = d.textbbox((0, 0), ch, font=f)
        gw, gh = bb[2] - bb[0], bb[3] - bb[1]
        ref = d.textbbox((0, 0), "H", font=f)
        if (ref[3] - ref[1]) <= cap * ss:
            break
        px = int(px * 0.95)
    ref = d.textbbox((0, 0), "H", font=f)
    base = (h * ss + (ref[3] - ref[1])) // 2 - ref[3]
    if gw > adv * ss:   # too wide for its advance: draw on a wider canvas, squeeze horizontally
        tmp = Image.new("L", (gw + 2 * ss, h * ss), 0)
        ImageDraw.Draw(tmp).text((ss - bb[0], base), ch, fill=255, font=f)
        tmp = tmp.resize((adv * ss, h * ss), Image.LANCZOS)
        img.paste(tmp, (0, 0))
    else:
        x = (adv * ss - gw) // 2 - bb[0]
        d.text((max(-bb[0], x), base), ch, fill=255, font=f)
    return np.asarray(img, np.float32).reshape(h, ss, w, ss).mean((1, 3)) / 255.0


def hook(sym, e):
    m = re.fullmatch(r"aHudNumber_(\d)", sym) or re.fullmatch(r"sLargeText_1997_(\d)", sym)
    if m:
        ch, adv, cap = m.group(1), e["w"], e["h"] - 1
    elif sym in GLYPHS:
        ch, adv, dh = GLYPHS[sym]
        if SMALL_CHARS.find(ch) > 30 and sym.startswith("aSmallText_") and ch.isdigit():
            adv = 7
        cap = dh - 2 if ch not in ".:-!" else dh - 2
        if ch in "st":
            cap = dh - 2
    else:
        return None
    w, h = e["w"], e["h"]
    mask = draw_glyph(ch, w, h, min(adv, w), min(cap, h))
    fg = np.array([255.0, 255.0, 255.0])   # the game tints these with its primitive colour
    img = np.zeros((h, w, 4), np.float32)
    img[..., :3] = fg
    img[..., 3] = np.clip(mask * 1.2, 0, 1) * 255
    return img.astype(np.uint8)
