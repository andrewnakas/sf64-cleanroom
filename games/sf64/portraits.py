"""Radio / menu portraits, drawn from our own written descriptions (no retail pixels).

Each character is a species template (head shape, ears, muzzle, eyes) plus colours and props
(helmet, cap, goggles, eyepatch, sunglasses, visor, collar). Portrait1 = mouth closed,
Portrait2 = mouth open (the radio alternates them while the character talks).
Drawn with PIL at 8x supersampling, simple two-tone shading, a frame in the character's colour.

    python -m games.sf64.portraits <out.png>     # preview sheet of every character
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SS = 8

# ------------------------------------------------------------------ characters
C = {
    "fox":     dict(species="fox", fur=(214, 150, 70), light=(250, 235, 210), eye=(40, 140, 70), frame=(240, 150, 30),
                    collar=(235, 235, 235), jacket=(60, 110, 60)),
    "foxexp":  dict(species="fox", fur=(214, 150, 70), light=(250, 235, 210), eye=(40, 140, 70), frame=(240, 200, 40),
                    collar=(235, 235, 235), jacket=(60, 110, 60), shades=True),
    "james":   dict(species="fox", fur=(200, 140, 70), light=(245, 225, 200), eye=(40, 140, 70), frame=(240, 210, 40),
                    collar=(120, 90, 60), jacket=(90, 70, 50), shades=True, cap=(70, 70, 80)),
    "falco":   dict(species="bird", fur=(60, 100, 200), light=(235, 235, 245), eye=(20, 20, 30), frame=(40, 110, 230),
                    mask=(210, 40, 40), beak=(245, 190, 40), collar=(235, 235, 235), jacket=(60, 110, 60)),
    "peppy":   dict(species="hare", fur=(170, 165, 160), light=(240, 235, 225), eye=(40, 30, 30), frame=(220, 40, 40),
                    collar=(235, 235, 235), jacket=(60, 110, 60)),
    "slippy":  dict(species="toad", fur=(90, 180, 70), light=(235, 240, 200), eye=(30, 30, 30), frame=(60, 200, 60),
                    collar=(235, 235, 235), jacket=(60, 110, 60), cap=(245, 245, 245)),
    "katt":    dict(species="cat", fur=(230, 120, 170), light=(250, 215, 230), eye=(40, 40, 120), frame=(240, 110, 200),
                    collar=(40, 40, 50), jacket=(40, 40, 50), hair=(40, 30, 60)),
    "bill":    dict(species="dog", fur=(130, 130, 140), light=(220, 220, 225), eye=(30, 30, 30), frame=(40, 170, 90),
                    collar=(60, 90, 60), jacket=(60, 90, 60), helmet=(60, 90, 60), goggles=(230, 200, 60)),
    "pepper":  dict(species="dog", fur=(150, 100, 60), light=(230, 200, 160), eye=(30, 30, 30), frame=(200, 170, 60),
                    collar=(90, 80, 60), jacket=(90, 80, 60), cap=(80, 70, 50), moustache=(240, 240, 230)),
    "rob":     dict(species="robot", fur=(90, 110, 150), light=(200, 210, 230), eye=(230, 60, 170), frame=(80, 140, 220),
                    collar=(120, 130, 150), jacket=(120, 130, 150)),
    "wolf":    dict(species="fox", fur=(120, 125, 140), light=(210, 210, 220), eye=(200, 60, 40), frame=(120, 120, 140),
                    collar=(60, 60, 70), jacket=(50, 50, 60), eyepatch=True, brow=(170, 40, 60), wolf=True),
    "leon":    dict(species="lizard", fur=(80, 160, 70), light=(190, 210, 120), eye=(240, 220, 40), frame=(80, 160, 70),
                    collar=(60, 60, 70), jacket=(50, 50, 60)),
    "pigma":   dict(species="pig", fur=(220, 150, 140), light=(245, 200, 190), eye=(30, 30, 30), frame=(200, 120, 110),
                    collar=(60, 60, 70), jacket=(50, 50, 60), goggles=(200, 170, 60)),
    "andrew":  dict(species="monkey", fur=(150, 90, 60), light=(230, 170, 150), eye=(30, 30, 30), frame=(140, 80, 160),
                    collar=(60, 60, 70), jacket=(50, 50, 60), helmet=(120, 60, 150)),
    "andross": dict(species="ape", fur=(150, 80, 50), light=(215, 150, 120), eye=(255, 60, 30), frame=(160, 60, 40),
                    collar=(80, 40, 30), jacket=(80, 40, 30), bald=True),
    "boss_co1": dict(species="monkey", fur=(140, 90, 50), light=(220, 160, 120), eye=(60, 230, 230), frame=(120, 60, 140),
                     collar=(70, 70, 80), jacket=(70, 70, 80), helmet=(110, 50, 130), emblem=(230, 60, 60)),
    "boss_co2": dict(species="lizard", fur=(60, 130, 60), light=(150, 190, 100), eye=(230, 230, 60), frame=(60, 120, 60),
                     collar=(70, 70, 80), jacket=(70, 70, 80), helmet=(40, 100, 40), emblem=(230, 60, 60)),
    "boss_a6": dict(species="monkey", fur=(160, 100, 60), light=(230, 170, 130), eye=(30, 30, 30), frame=(200, 40, 40),
                    collar=(70, 70, 80), jacket=(70, 70, 80), helmet=(200, 40, 40), emblem=(245, 245, 245)),
    "caiman":  dict(species="lizard", fur=(70, 150, 90), light=(170, 210, 140), eye=(250, 250, 250), frame=(60, 140, 80),
                    collar=(70, 70, 80), jacket=(70, 70, 80), helmet=(60, 130, 80), emblem=(245, 245, 245), goggles=(200, 200, 210)),
    "boss_me": dict(species="lizard", fur=(90, 150, 90), light=(170, 200, 130), eye=(230, 60, 60), frame=(90, 150, 70),
                    collar=(70, 70, 80), jacket=(70, 70, 80), helmet=(80, 140, 70), emblem=(230, 60, 60)),
    "shogun":  dict(species="monkey", fur=(190, 90, 40), light=(240, 170, 110), eye=(30, 30, 30), frame=(220, 90, 40),
                    collar=(70, 70, 80), jacket=(70, 70, 80), helmet=(210, 70, 40), emblem=(245, 245, 245)),
    "spyborg": dict(species="robot", fur=(60, 60, 70), light=(150, 150, 170), eye=(240, 30, 30), frame=(120, 40, 140),
                    collar=(60, 60, 70), jacket=(40, 40, 50), cyclops=True),
    "tanuki":  dict(species="dog", fur=(150, 90, 50), light=(240, 230, 220), eye=(30, 30, 30), frame=(200, 140, 60),
                    collar=(60, 60, 70), jacket=(60, 60, 70), mask=(60, 40, 30), round_ears=True),
}

# symbol -> (character, open mouth)
PORTRAITS = {}
for sym, who in {
    "Fox": "fox", "FoxExpert": "foxexp", "Falco": "falco", "Peppy": "peppy", "Slippy": "slippy",
    "James": "james", "Katt": "katt", "Bill": "bill", "KaBill": "bill", "Pepper": "pepper",
    "GreatFoxGralPepper": "pepper", "Rob64": "rob", "GreatFoxRob64": "rob", "FoUnusedRob64": "rob",
    "StarWolfWolf": "wolf", "StarWolfWolf2": "wolf", "StarWolfLeon": "leon", "StarWolfLeon2": "leon",
    "StarWolfPigma": "pigma", "StarWolfPigma2": "pigma", "StarWolfAndrew": "andrew", "StarWolfAndrew2": "andrew",
    "And": "andross", "A6And": "andross", "CoCorneriaBoss1": "boss_co1", "CoCorneriaBoss2": "boss_co2",
    "A6Boss": "boss_a6", "A6Caiman": "caiman", "MeBoss": "boss_me", "SyShogun": "shogun", "SxSpyborg": "spyborg",
}.items():
    PORTRAITS[f"a{sym}Portrait1Tex"] = (who, False)
    PORTRAITS[f"a{sym}Portrait2Tex"] = (who, True)
PORTRAITS.update({
    "aTrYaruDePonFace1Tex": ("tanuki", False), "aTrYaruDePonFace2Tex": ("tanuki", True),
    "aMapRadioCharFalcoTex": ("falco", False), "aMapRadioCharPeppyTex": ("peppy", False),
    "aMapRadioCharSlippyTex": ("slippy", False),
    "aVsFoxFaceTex": ("fox", False), "aVsFalcoFaceTex": ("falco", False), "aVsPeppyFaceTex": ("peppy", False),
    "aVsSlippyFaceTex": ("slippy", False),
    "D_VS_MENU_7007FC0": ("falco", False), "D_VS_MENU_7009E00": ("fox", False),
    "D_VS_MENU_700BC40": ("peppy", False), "D_VS_MENU_700DA80": ("slippy", False),
    "D_versus_3020048": ("slippy", False), "D_versus_3021958": ("peppy", False),
    "D_versus_302A138": ("fox", False), "D_versus_302AC68": ("falco", False),
})


# ------------------------------------------------------------------ drawing helpers
def _shade(c, k):
    return tuple(int(max(0, min(255, v * k))) for v in c)


class P:
    """Painter in a 100x100 design space (x right, y down), rendered at size*SS."""

    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.im = Image.new("RGB", (w * SS, h * SS), bg)
        self.d = ImageDraw.Draw(self.im)
        self.sx, self.sy = w * SS / 100.0, h * SS / 100.0

    def xy(self, pts):
        return [(x * self.sx, y * self.sy) for x, y in pts]

    def ell(self, cx, cy, rx, ry, c, outline=None, width=0):
        self.d.ellipse([(cx - rx) * self.sx, (cy - ry) * self.sy, (cx + rx) * self.sx, (cy + ry) * self.sy],
                       fill=c, outline=outline, width=int(width * self.sx))

    def poly(self, pts, c):
        self.d.polygon(self.xy(pts), fill=c)

    def line(self, pts, c, w):
        self.d.line(self.xy(pts), fill=c, width=max(1, int(w * self.sx)), joint="curve")

    def rect(self, x0, y0, x1, y1, c):
        self.d.rectangle([x0 * self.sx, y0 * self.sy, x1 * self.sx, y1 * self.sy], fill=c)

    def arc(self, cx, cy, rx, ry, a0, a1, c, w):
        self.d.arc([(cx - rx) * self.sx, (cy - ry) * self.sy, (cx + rx) * self.sx, (cy + ry) * self.sy],
                   a0, a1, fill=c, width=max(1, int(w * self.sx)))

    def result(self):
        return self.im.resize((self.w, self.h), Image.LANCZOS)


def _eye(p, cx, cy, r, iris, look=0.0, lid=0.0, angry=False, right=False):
    p.ell(cx, cy, r, r * 1.15, (250, 250, 250))
    p.ell(cx + look * r * 0.3, cy + r * 0.1, r * 0.62, r * 0.75, iris)
    p.ell(cx + look * r * 0.3, cy + r * 0.12, r * 0.3, r * 0.38, (10, 10, 15))
    p.ell(cx + look * r * 0.3 - r * 0.25, cy - r * 0.25, r * 0.16, r * 0.16, (255, 255, 255))
    if angry:
        s = -1 if right else 1
        p.poly([(cx - r * 1.3, cy - r * (1.3 if right else 0.5)), (cx + r * 1.3, cy - r * (0.5 if right else 1.3)),
                (cx + r * 1.3, cy - r * 2.0), (cx - r * 1.3, cy - r * 2.0)], None or (0, 0, 0, 0))
    if lid > 0:
        p.rect(cx - r * 1.1, cy - r * 1.3, cx + r * 1.1, cy - r * 1.3 + 2 * r * 1.15 * lid, None)


def _brow(p, cx, cy, r, c, right, angry):
    tilt = 0.45 if angry else -0.15
    if right:
        p.line([(cx - r * 1.1, cy - r * (1.25 + tilt)), (cx + r * 1.0, cy - r * (1.25 - tilt))], c, r * 0.45)
    else:
        p.line([(cx - r * 1.0, cy - r * (1.25 - tilt)), (cx + r * 1.1, cy - r * (1.25 + tilt))], c, r * 0.45)


def _mouth(p, cx, cy, w, open_, c_dark=(90, 20, 30), c_line=(40, 20, 20), teeth=False):
    if open_:
        p.ell(cx, cy + w * 0.25, w * 0.55, w * 0.42, c_dark)
        p.ell(cx, cy + w * 0.45, w * 0.3, w * 0.18, (200, 80, 90))
        if teeth:
            p.rect(cx - w * 0.2, cy - w * 0.15, cx + w * 0.2, cy + w * 0.12, (250, 250, 245))
    else:
        p.arc(cx, cy - w * 0.15, w * 0.5, w * 0.3, 20, 160, c_line, w * 0.12)
        if teeth:
            p.rect(cx - w * 0.16, cy + w * 0.12, cx + w * 0.16, cy + w * 0.34, (250, 250, 245))


def _body(p, c):
    jk, col = c["jacket"], c["collar"]
    p.poly([(8, 100), (18, 82), (50, 76), (82, 82), (92, 100)], jk)
    p.poly([(28, 100), (34, 80), (50, 90), (66, 80), (72, 100)], _shade(jk, 0.8))
    p.poly([(30, 80), (50, 92), (70, 80), (64, 74), (50, 82), (36, 74)], col)


# ------------------------------------------------------------------ species
def draw(who, open_, w=44, h=44, frame=True):
    c = C[who]
    sp = c["species"]
    bg0 = _shade(c["frame"], 0.18)
    p = P(w, h, bg0)
    # soft backdrop gradient
    for i in range(10):
        p.ell(50, 40, 70 - i * 5, 60 - i * 4, _shade(c["frame"], 0.18 + i * 0.02))
    fur, light, eye = c["fur"], c["light"], c["eye"]
    dark = _shade(fur, 0.7)
    _body(p, c)
    angry = who in ("wolf", "andross", "leon", "pigma", "andrew", "boss_co1", "boss_co2", "boss_a6", "boss_me", "shogun", "caiman")
    if sp == "fox":
        ear = [(18, 12), (34, 36), (22, 44)] if not c.get("wolf") else [(16, 8), (34, 36), (20, 44)]
        p.poly(ear, dark)
        p.poly([(82, 12), (66, 36), (78, 44)] if not c.get("wolf") else [(84, 8), (66, 36), (80, 44)], dark)
        p.poly([(21, 18), (31, 36), (24, 40)], light)
        p.poly([(79, 18), (69, 36), (76, 40)], light)
        p.ell(50, 48, 30, 28, fur)
        p.ell(50, 40, 22, 14, _shade(fur, 1.08))
        # cheek tufts and muzzle
        p.poly([(22, 52), (12, 66), (34, 64)], light)
        p.poly([(78, 52), (88, 66), (66, 64)], light)
        p.ell(50, 64, 17, 13, light)
        p.ell(50, 55, 6, 4, (25, 20, 20))
        _eye(p, 39, 45, 5.5, eye)
        _eye(p, 61, 45, 5.5, eye)
        _brow(p, 39, 45, 5.5, dark, False, angry)
        _brow(p, 61, 45, 5.5, dark, True, angry)
        _mouth(p, 50, 67, 12, open_)
        if c.get("eyepatch"):
            p.ell(61, 45, 7, 7, (20, 20, 25))
            p.line([(40, 34), (78, 52)], (20, 20, 25), 2.5)
        if c.get("brow"):
            p.poly([(30, 18), (50, 28), (70, 18), (60, 30), (40, 30)], c["brow"])
    elif sp == "bird":
        p.ell(50, 46, 30, 30, fur)
        p.poly([(26, 26), (40, 6), (48, 28)], fur)
        p.poly([(44, 24), (58, 2), (62, 26)], _shade(fur, 1.1))
        p.ell(50, 44, 26, 9, c["mask"])
        _eye(p, 39, 44, 5, eye)
        _eye(p, 61, 44, 5, eye)
        _brow(p, 39, 44, 5, _shade(fur, 0.6), False, True)
        _brow(p, 61, 44, 5, _shade(fur, 0.6), True, True)
        p.ell(50, 70, 22, 12, light)
        beak = c["beak"]
        if open_:
            p.poly([(34, 54), (66, 54), (50, 68)], beak)
            p.poly([(38, 70), (62, 70), (50, 80)], _shade(beak, 0.85))
            p.poly([(40, 64), (60, 64), (50, 71)], (110, 20, 30))
        else:
            p.poly([(34, 54), (66, 54), (50, 76)], beak)
            p.line([(38, 62), (62, 62)], _shade(beak, 0.7), 1.5)
    elif sp == "hare":
        p.ell(38, 16, 7, 22, fur)
        p.ell(62, 16, 7, 22, fur)
        p.ell(38, 18, 3.5, 17, (230, 180, 180))
        p.ell(62, 18, 3.5, 17, (230, 180, 180))
        p.ell(50, 52, 28, 26, fur)
        p.ell(50, 66, 18, 13, light)
        p.ell(50, 57, 5, 3.5, (200, 110, 120))
        _eye(p, 39, 48, 5, eye)
        _eye(p, 61, 48, 5, eye)
        _brow(p, 39, 48, 5, _shade(fur, 0.6), False, False)
        _brow(p, 61, 48, 5, _shade(fur, 0.6), True, False)
        _mouth(p, 50, 68, 11, open_, teeth=True)
    elif sp == "toad":
        p.ell(50, 54, 34, 26, fur)
        if c.get("cap"):
            p.d.chord([30 * p.sx, 22 * p.sy, 70 * p.sx, 50 * p.sy], 180, 360, fill=c["cap"])
            p.poly([(44, 36), (74, 32), (80, 37), (52, 40)], _shade(c["cap"], 0.85))
        p.ell(34, 34, 12, 12, fur)
        p.ell(66, 34, 12, 12, fur)
        p.ell(34, 34, 9, 9, (250, 250, 250))
        p.ell(66, 34, 9, 9, (250, 250, 250))
        p.ell(35, 36, 4, 4.5, eye)
        p.ell(65, 36, 4, 4.5, eye)
        p.ell(50, 68, 24, 10, light)
        if open_:
            p.ell(50, 66, 16, 8, (140, 30, 40))
            p.ell(50, 70, 9, 3.5, (220, 90, 100))
        else:
            p.arc(50, 58, 20, 8, 15, 165, (30, 60, 30), 1.6)
    elif sp in ("cat",):
        p.poly([(18, 14), (36, 34), (22, 44)], fur)
        p.poly([(82, 14), (64, 34), (78, 44)], fur)
        p.poly([(22, 22), (32, 34), (25, 38)], light)
        p.poly([(78, 22), (68, 34), (75, 38)], light)
        p.ell(50, 50, 29, 27, fur)
        p.poly([(26, 30), (50, 20), (74, 30), (64, 40), (50, 32), (36, 40)], c["hair"])
        p.ell(50, 64, 15, 11, light)
        p.ell(50, 56, 4, 3, (200, 80, 120))
        _eye(p, 39, 47, 5.5, eye)
        _eye(p, 61, 47, 5.5, eye)
        p.line([(33, 42), (45, 43)], (30, 20, 40), 1.4)
        p.line([(55, 43), (67, 42)], (30, 20, 40), 1.4)
        _mouth(p, 50, 66, 10, open_)
    elif sp == "dog":
        if c.get("round_ears"):
            p.ell(26, 26, 10, 10, _shade(fur, 0.8))
            p.ell(74, 26, 10, 10, _shade(fur, 0.8))
        else:
            p.ell(22, 50, 9, 18, _shade(fur, 0.7))
            p.ell(78, 50, 9, 18, _shade(fur, 0.7))
        p.ell(50, 48, 28, 28, fur)
        if c.get("mask"):
            p.ell(50, 46, 24, 8, c["mask"])
        p.ell(50, 66, 19, 14, light)
        p.ell(50, 57, 7, 5, (25, 20, 20))
        _eye(p, 39, 45, 5, eye)
        _eye(p, 61, 45, 5, eye)
        _brow(p, 39, 45, 5, _shade(fur, 0.6), False, False)
        _brow(p, 61, 45, 5, _shade(fur, 0.6), True, False)
        if c.get("moustache"):
            p.ell(42, 63, 9, 4, c["moustache"])
            p.ell(58, 63, 9, 4, c["moustache"])
        _mouth(p, 50, 70, 12, open_)
    elif sp in ("monkey", "ape"):
        p.ell(20, 48, 8, 10, _shade(fur, 0.8))
        p.ell(80, 48, 8, 10, _shade(fur, 0.8))
        p.ell(50, 46, 30, 30 if sp == "ape" else 28, fur)
        p.ell(50, 54, 22, 20, light)
        p.ell(40, 44, 10, 8, light)
        p.ell(60, 44, 10, 8, light)
        _eye(p, 40, 45, 5, eye)
        _eye(p, 60, 45, 5, eye)
        _brow(p, 40, 45, 5, _shade(fur, 0.55), False, angry)
        _brow(p, 60, 45, 5, _shade(fur, 0.55), True, angry)
        p.ell(46, 56, 2, 1.5, (60, 30, 30))
        p.ell(54, 56, 2, 1.5, (60, 30, 30))
        if sp == "ape":
            p.poly([(26, 36), (50, 42), (74, 36), (72, 42), (50, 47), (28, 42)], _shade(fur, 0.5))   # brow ridge
            for x0 in (40, 60):
                p.ell(x0, 45, 7, 7, (255, 120, 60))
                p.ell(x0, 45, 4, 4, (255, 240, 160))
            for vx in (34, 44, 58):
                p.line([(vx, 14), (vx + 3, 22), (vx - 1, 30)], _shade(fur, 0.6), 1.2)
            if open_:
                p.ell(50, 68, 13, 9, (70, 10, 10))
            else:
                p.ell(50, 67, 13, 5, (70, 10, 10))
            for tx in (41, 47, 53, 59):
                p.poly([(tx - 2, 62), (tx + 2, 62), (tx, 67)], (245, 240, 220))
        else:
            _mouth(p, 50, 66, 14, open_)
    elif sp == "lizard":
        p.ell(50, 46, 28, 26, fur)
        p.ell(50, 64, 26, 14, _shade(fur, 1.05))
        p.ell(50, 68, 20, 8, light)
        p.ell(33, 40, 9, 9, _shade(fur, 0.85))
        p.ell(67, 40, 9, 9, _shade(fur, 0.85))
        p.ell(33, 40, 6, 6, eye)
        p.ell(67, 40, 6, 6, eye)
        p.rect(32, 36, 34, 44, (10, 10, 10))
        p.rect(66, 36, 68, 44, (10, 10, 10))
        if open_:
            p.ell(50, 68, 20, 6, (150, 30, 40))
        else:
            p.line([(30, 66), (70, 66)], _shade(fur, 0.5), 1.5)
    elif sp == "pig":
        p.poly([(22, 20), (36, 32), (24, 40)], _shade(fur, 0.85))
        p.poly([(78, 20), (64, 32), (76, 40)], _shade(fur, 0.85))
        p.ell(50, 50, 31, 28, fur)
        p.ell(50, 60, 12, 9, light)
        p.ell(46, 60, 2.2, 3, (120, 60, 60))
        p.ell(54, 60, 2.2, 3, (120, 60, 60))
        _eye(p, 38, 44, 4.5, eye)
        _eye(p, 62, 44, 4.5, eye)
        _brow(p, 38, 44, 4.5, _shade(fur, 0.5), False, True)
        _brow(p, 62, 44, 4.5, _shade(fur, 0.5), True, True)
        _mouth(p, 50, 73, 14, open_, teeth=True)
    elif sp == "robot":
        p.rect(24, 22, 76, 74, fur)
        p.rect(28, 26, 72, 70, _shade(fur, 1.2))
        p.rect(20, 40, 26, 56, _shade(fur, 0.8))
        p.rect(74, 40, 80, 56, _shade(fur, 0.8))
        p.line([(50, 22), (50, 10)], light, 2)
        p.ell(50, 9, 3, 3, eye)
        if c.get("cyclops"):
            p.ell(50, 46, 14, 14, (30, 30, 35))
            p.ell(50, 46, 9, 9, eye)
            p.ell(47, 43, 3, 3, (255, 200, 200))
        else:
            p.rect(32, 38, 68, 48, (20, 20, 30))
            p.rect(35, 41, 65, 45, eye)
        grille = (40, 45, 60) if not open_ else (220, 220, 240)
        for i in range(4):
            p.rect(38, 56 + i * 3.2, 62, 57.4 + i * 3.2, grille)
    # props
    if c.get("helmet"):
        hc = c["helmet"]
        p.d.chord([22 * p.sx, 8 * p.sy, 78 * p.sx, 60 * p.sy], 180, 360, fill=hc)
        p.rect(22, 32, 78, 36, _shade(hc, 0.75))
        if c.get("emblem"):
            p.poly([(44, 30), (50, 14), (56, 30), (53, 30), (50, 22), (47, 30)], c["emblem"])
            p.rect(46.5, 24, 53.5, 26, c["emblem"])
    if c.get("cap") and sp not in ("toad",):
        cc = c["cap"]
        p.d.chord([24 * p.sx, 12 * p.sy, 76 * p.sy, 50 * p.sy], 180, 360, fill=cc)
        p.poly([(24, 31), (76, 31), (84, 36), (18, 36)], _shade(cc, 0.8))
    if c.get("goggles"):
        g = c["goggles"]
        p.ell(39, 33 if c.get("helmet") else 45, 8, 6, g)
        p.ell(61, 33 if c.get("helmet") else 45, 8, 6, g)
        p.ell(39, 33 if c.get("helmet") else 45, 5, 3.5, (120, 170, 200))
        p.ell(61, 33 if c.get("helmet") else 45, 5, 3.5, (120, 170, 200))
    if c.get("shades"):
        p.ell(39, 45, 8.5, 6, (15, 15, 20))
        p.ell(61, 45, 8.5, 6, (15, 15, 20))
        p.line([(47, 44), (53, 44)], (15, 15, 20), 2)
        p.ell(36, 43, 2, 1.2, (200, 200, 220))
        p.ell(58, 43, 2, 1.2, (200, 200, 220))
    img = p.result().convert("RGBA")
    a = np.asarray(img).copy()
    if frame:
        f = np.asarray(c["frame"], np.uint8)
        a[0, :, :3] = a[-1, :, :3] = f
        a[:, 0, :3] = a[:, -1, :3] = f
    a[..., 3] = 255
    return a


def pepper_panel(open_):
    """Map-screen video of General Pepper: 128x96 = [Tex3|Tex4] / [Tex1|Tex2] / [Bottom1|Bottom2] (from the DL quads)."""
    face = draw("pepper", open_, 96, 72, frame=False)
    img = np.zeros((96, 128, 4), np.uint8)
    img[..., :3] = (10, 30, 70)
    img[..., 3] = 255
    img[0:72, 16:112] = face
    img[0:72:2, :, :3] = (img[0:72:2, :, :3] * 0.8).astype(np.uint8)     # scanlines
    bar = Image.new("RGB", (128 * 4, 24 * 4), (15, 20, 40))
    d = ImageDraw.Draw(bar)
    from . import labels
    f = labels.font("rubik", 44, "Bold")
    d.text((24, 22), "LIVE  CN.", fill=(230, 230, 240), font=f)
    d.ellipse([400, 30, 440, 70], fill=(220, 40, 40))
    img[72:96, :, :3] = np.asarray(bar.resize((128, 24), Image.LANCZOS))
    return img


_PANEL = {}


def static(w, h, sym):
    """Radio static: our own noise bands."""
    from cleanroom.decomp.gen import h32
    rng = np.random.default_rng(h32("static", sym))
    v = rng.integers(40, 230, (h, w)).astype(np.float32)
    v *= (0.75 + 0.25 * np.sin(np.arange(h) * 1.7))[:, None]
    out = np.zeros((h, w, 4), np.uint8)
    out[..., 0] = out[..., 1] = out[..., 2] = np.clip(v, 0, 255).astype(np.uint8)
    out[..., 2] = np.clip(v * 1.1, 0, 255).astype(np.uint8)
    out[..., 3] = 255
    return out


def hook(sym, e):
    import re
    if sym in ("aRadioStaticPortraitTex", "aUnusedStaticPortraitTex"):
        return static(e["w"], e["h"], sym)
    m = re.fullmatch(r"aMapGralPepperFace(1|2|Bottom)Tex(\d)", sym)
    if m:
        kind, i = m.group(1), int(m.group(2))
        op = kind == "2"
        if op not in _PANEL:
            _PANEL[op] = pepper_panel(op)
        P_ = _PANEL[op]
        if kind == "Bottom":
            y, x = 64, (i - 1) * 64
            piece = np.zeros((32, 64, 4), np.uint8)
            piece[:] = P_[y:y + 32, x:x + 64] if y + 32 <= 96 else 0
            return piece
        y, x = {1: (32, 0), 2: (32, 64), 3: (0, 0), 4: (0, 64)}[i]
        return P_[y:y + 32, x:x + 64].copy()
    if sym not in PORTRAITS:
        return None
    who, open_ = PORTRAITS[sym]
    return draw(who, open_, e["w"], e["h"], frame=not sym.startswith("aMapRadioChar"))


if __name__ == "__main__":
    import sys
    tiles = []
    for who in C:
        tiles.append(np.concatenate([draw(who, False), draw(who, True)], 1))
    rows = [np.concatenate(tiles[i:i + 6] + [np.zeros_like(tiles[0])] * (6 - len(tiles[i:i + 6])), 1)
            for i in range(0, len(tiles), 6)]
    sheet = np.concatenate(rows, 0)
    Image.fromarray(np.repeat(np.repeat(sheet, 3, 0), 3, 1)).save(sys.argv[1])
