"""Our own drawings for pictures a colour grid can't carry (text, faces, icons).
Each hook: (symbol, spec entry) -> RGBA uint8 (h, w, 4) or None; generate.HOOKS tries them in order.
For CI textures whose palette lives in code, channel 0 carries the palette index."""
import numpy as np

from . import endings, glyphsets, labels, logos, planets, portraits, prologue, radiofont

_RADIO = None


def radio_font(sym, e):
    global _RADIO
    if not sym.startswith("gTextChar"):
        return None
    if _RADIO is None:
        _RADIO = radiofont.textures()
    idx = _RADIO[sym]
    img = np.zeros((e["h"], e["w"], 4), np.uint8)
    img[..., 0] = idx
    img[..., 3] = 255
    return img


HOOKS = [radio_font, labels.hook, glyphsets.hook, portraits.hook, logos.hook, endings.hook, planets.hook, prologue.hook]

