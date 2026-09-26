"""Planet and cloud surfaces: our own tileable fBm noise, coloured with the kept 4x4 grid's colours.

The grid alone upsamples to a soft blob; planets on the map read better with continents/clouds. The noise
(value noise, 5 octaves, periodic in both axes because these wrap around spheres) perturbs the grid's own
luminance ranking, and the colour comes from the grid's cells sorted by luminance.
"""
import re

import numpy as np

from cleanroom.decomp.gen import h32

PLANETS = re.compile(r"aMap(Aquas|Corneria|Fortuna|Katina|Macbeth|Titania|Venom|VenomCloud|Zoness)Tex$")


def periodic_noise(w, h, seed, octaves=5, base=4):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        n = base * (2 ** o)
        lat = rng.standard_normal((n, n)).astype(np.float32)
        ys = np.arange(h, dtype=np.float32) / h * n
        xs = np.arange(w, dtype=np.float32) / w * n
        y0, x0 = ys.astype(int), xs.astype(int)
        fy, fx = ys - y0, xs - x0
        fy, fx = (fy * fy * (3 - 2 * fy))[:, None], (fx * fx * (3 - 2 * fx))[None, :]
        y1, x1 = (y0 + 1) % n, (x0 + 1) % n
        v = (lat[y0][:, x0] * (1 - fx) + lat[y0][:, x1] * fx) * (1 - fy) + \
            (lat[y1][:, x0] * (1 - fx) + lat[y1][:, x1] * fx) * fy
        out += amp * v
        tot += amp
        amp *= 0.55
    return out / tot


def surface(sym, e):
    from .generate import upsample
    w, h = e["w"], e["h"]
    n = int(round(len(e["grid"]) ** 0.5))
    base = upsample(e["grid"], n, w, h, True, True)
    g = np.asarray(e["grid"], np.float32)[:, :3]
    lum = g @ np.array([0.3, 0.59, 0.11], np.float32)
    pal = g[np.argsort(lum)]
    pl = np.sort(lum)
    bl = base[..., :3] @ np.array([0.3, 0.59, 0.11], np.float32)
    rank = np.interp(bl, pl, np.linspace(0, 1, len(pl)))
    nz = periodic_noise(w, h, h32("planet", sym))
    t = np.clip(rank + 0.45 * nz, 0, 1) * (len(pal) - 1)
    i0 = np.floor(t).astype(int)
    i1 = np.minimum(i0 + 1, len(pal) - 1)
    f = (t - i0)[..., None]
    col = pal[i0] * (1 - f) + pal[i1] * f
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = 0.3 * base[..., :3] + 0.7 * col
    out[..., :3] *= (1.0 + 0.12 * periodic_noise(w, h, h32("shade", sym), 3, 8))[..., None]
    out[..., 3] = 255
    return np.clip(out, 0, 255).astype(np.uint8)


def hook(sym, e):
    if PLANETS.match(sym) and "alpha2" not in e:
        return surface(sym, e)
    return None
