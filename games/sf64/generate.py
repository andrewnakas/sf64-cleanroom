"""CLEAN ROOM: build an sf64 decomp tree whose extracted assets are all generated.

    python -m games.sf64.generate <pristine> <dirty-code-only inputs> <clean tree out> [--only tex]

Inputs:
  * pristine decomp source (no extracted assets),
  * from the dirty tree ONLY code/geometry that the user scope keeps: splat's asm/ (boot code,
    microcode, libultra asm), Torch's src/assets/*/*.c (display lists, vertices, animations,
    hitboxes, level scripts, message tables) and include/assets headers, the linker scripts,
    and the note sequences (audio_seq.bin),
  * games/sf64/spec (coarse texture facts) + our own drawings (labels, faces, icons).
Writes every Torch texture .inc.c (and TLUT) from the spec; never copies retail pixel data.
Audio samples (audio_table.bin) and the bank (audio_bank.bin) come from games.sf64.audio.
"""
import json
import os
import shutil
import sys

import numpy as np
from scipy.cluster.vq import kmeans2

from cleanroom.decomp.gen import from_digest, h32
from cleanroom.gfx import texfmt

from .extract_spec import FMTS, CSIZE

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")

# files copied from the dirty tree: code and geometry only (never *.inc.c pixel data)
KEEP_DIRS = ["asm", "linker_scripts", "include/assets"]
KEEP_BIN = ["alt_ipl3.textbin.bin", "aspmain.textbin.bin", "f3dex.textbin.bin", "ipl3.textbin.bin",
            "rspboot.textbin.bin", "audio_seq.bin"]


def copy_code(dirty, out):
    for d in KEEP_DIRS:
        src = os.path.join(dirty, d)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(out, d), dirs_exist_ok=True)
    os.makedirs(os.path.join(out, "bin", "us", "rev1"), exist_ok=True)
    for b in KEEP_BIN:
        shutil.copy2(os.path.join(dirty, "bin", "us", "rev1", b), os.path.join(out, "bin", "us", "rev1", b))
    n = 0
    for d in os.listdir(os.path.join(dirty, "src", "assets")):
        for f in os.listdir(os.path.join(dirty, "src", "assets", d)):
            if f.endswith(".c") and not f.endswith(".inc.c"):
                os.makedirs(os.path.join(out, "src", "assets", d), exist_ok=True)
                shutil.copy2(os.path.join(dirty, "src", "assets", d, f), os.path.join(out, "src", "assets", d, f))
                n += 1
    print(f"code/geometry copied: {n} asset .c files, {len(KEEP_BIN)} bins, {KEEP_DIRS}")


# ----------------------------------------------------------------- pictures

WRAP = {}    # symbol -> (wrap_s, wrap_t) from the kept display lists (G_TX_WRAP without mirror)


def wrap_modes(tree):
    import re
    rx = re.compile(r"gsDPLoad(?:Texture|MultiBlock)\w*\(\s*(\w+),[^;]*?G_TX_(NO)?MIRROR \| G_TX_(WRAP|CLAMP),"
                    r"\s*G_TX_(NO)?MIRROR \| G_TX_(WRAP|CLAMP)")
    out = {}
    for d in os.listdir(os.path.join(tree, "src", "assets")):
        f = os.path.join(tree, "src", "assets", d, d + ".c")
        if os.path.exists(f):
            for m in rx.finditer(open(f).read()):
                ws = m.group(2) == "NO" and m.group(3) == "WRAP"
                wt = m.group(4) == "NO" and m.group(5) == "WRAP"
                a, b = out.get(m.group(1), (False, False))
                out[m.group(1)] = (a or ws, b or wt)
    return out


def upsample(grid, n, w, h, ws, wt):
    """Bilinear grid -> w x h; periodic along wrapped axes so tiles join without seams."""
    g = np.asarray(grid, np.float32).reshape(n, n, 4)

    def axis(size, wrap):
        c = (np.arange(size, dtype=np.float32) + 0.5) / size * n - 0.5
        i0 = np.floor(c).astype(int)
        f = c - i0
        if wrap:
            return i0 % n, (i0 + 1) % n, f
        return np.clip(i0, 0, n - 1), np.clip(i0 + 1, 0, n - 1), np.clip(f, 0, 1) * (c > 0) * (c < n - 1) + (c >= n - 1)

    y0, y1, fy = axis(h, wt)
    x0, x1, fx = axis(w, ws)
    fy, fx = fy[:, None, None], fx[None, :, None]
    top = g[y0][:, x0] * (1 - fx) + g[y0][:, x1] * fx
    bot = g[y1][:, x0] * (1 - fx) + g[y1][:, x1] * fx
    return top * (1 - fy) + bot * fy


HOOKS = []   # functions (sym, e) -> rgba or None, tried in order (labels, faces, icons ...)


HOOKED = [0]


def picture(sym, e):
    for hook in HOOKS:
        img = hook(sym, e)
        if img is not None:
            HOOKED[0] += 1
            return img
    ws, wt = WRAP.get(sym, (False, False))
    if ws or wt:
        n = int(round(len(e["grid"]) ** 0.5))
        img = upsample(e["grid"], n, e["w"], e["h"], ws, wt)
        img[..., 3] = from_digest(e["file"], e)[..., 3]
    else:
        img = from_digest(e["file"], e).astype(np.float32)
    # our own per-texel dither (+-1.5 steps of RGBA16): smooth gradients otherwise quantise into
    # the same texel runs as the retail art (taint scan)
    rng = np.random.default_rng(h32("dither", sym))
    img[..., :3] += rng.uniform(-12.0, 12.0, img.shape[:2] + (1,)) + rng.uniform(-4.0, 4.0, img.shape[:2] + (3,))
    return np.clip(img, 0, 255).astype(np.uint8)


def fmt_inc(data, ctype):
    cs = CSIZE[ctype]
    vals = [int.from_bytes(data[i:i + cs], "big") for i in range(0, len(data), cs)]
    per = {1: 16, 2: 8, 4: 4, 8: 2}[cs]
    w = 2 * cs
    lines = [", ".join(f"0x{v:0{w}x}" for v in vals[i:i + per]) + ", " for i in range(0, len(vals), per)]
    return "\n".join(lines) + "\n"


def build_palette(imgs, n, want_alpha):
    """Our own palette for all pictures sharing one TLUT: k-means over their opaque pixels."""
    px = np.concatenate([im.reshape(-1, 4) for im in imgs]).astype(np.float32)
    opaque = px[px[:, 3] >= 128][:, :3]
    k = n - 1 if want_alpha else n
    pal = np.zeros((n, 4), np.uint8)
    if len(opaque):
        rng = np.random.default_rng(h32("pal", n, len(opaque)))
        sample = opaque[rng.choice(len(opaque), min(len(opaque), 4096), replace=False)]
        uniq = np.unique(sample.astype(np.uint8), axis=0).astype(np.float32)
        kk = max(1, min(k, len(uniq)))
        cent, _ = kmeans2(sample, uniq[rng.choice(len(uniq), kk, replace=False)], minit="matrix", iter=12, seed=1)
        cent = np.clip(cent, 0, 255)
        off = 1 if want_alpha else 0
        pal[off:off + kk, :3] = cent.astype(np.uint8)
        pal[off:off + kk, 3] = 255
        pal[off + kk:, :] = pal[off + kk - 1]
    return pal


def index_image(img, pal, has_alpha):
    rgb = img[..., :3].reshape(-1, 1, 3).astype(np.float32)
    cand = pal[1:] if has_alpha else pal
    d = ((rgb - cand[None, :, :3].astype(np.float32)) ** 2).sum(-1)
    idx = d.argmin(1) + (1 if has_alpha else 0)
    if has_alpha:
        idx[img[..., 3].reshape(-1) < 128] = 0
    return idx.reshape(img.shape[:2])


def pal_rgba16(pal):
    """RGBA16 TLUT bytes; opaque entries keep a=1, the transparent slot is 0x0000."""
    return texfmt.encode(pal.reshape(1, -1, 4), texfmt.RGBA, texfmt.B16)


def write_inc(out, rel, data, ctype):
    p = os.path.join(out, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", newline="\n") as f:
        f.write(fmt_inc(data, ctype))


def gen_textures(out):
    spec = json.load(open(os.path.join(SPEC, "textures.json")))
    imgs, n = {}, 0
    for sym, e in spec.items():
        if e["fmt"] != "TLUT" and "grid" in e:
            imgs[sym] = picture(sym, e)
    # CI groups: one palette per TLUT, built from the pictures of all its users
    done_ci = set()
    for sym, e in spec.items():
        if e["fmt"] != "TLUT":
            continue
        users = [u for u in e["users"] if u in imgs]
        users += [u for u, t in spec.items() if t.get("tlut") == sym and u in imgs and u not in users]
        if not users:
            pal = np.zeros((e["colors"], 4), np.uint8)
            write_inc(out, e["file"], pal_rgba16(pal), e["ctype"])
            continue
        size = e["colors"]
        cap = 16 if any(spec[u]["fmt"] == "CI4" for u in users) else 256
        k = min(size, cap)
        has_a = any((imgs[u][..., 3] < 128).any() for u in users)
        pal = build_palette([imgs[u] for u in users], k, has_a)
        full = np.zeros((size, 4), np.uint8)
        full[:k] = pal
        full[k:] = pal[-1]
        write_inc(out, e["file"], pal_rgba16(full), e["ctype"])
        for u in users:
            if u in done_ci:
                continue
            t = spec[u]
            f, s = FMTS[t["fmt"]]
            idx = index_image(imgs[u], pal, has_a)
            buf = np.zeros(idx.shape + (4,), np.uint8)
            buf[..., 0] = idx
            write_inc(out, t["file"], texfmt.encode(buf, f, s), t["ctype"])
            done_ci.add(u)
            n += 1
    # everything else (and CI pictures whose palette lives in code: index facts, no noise)
    for sym, e in spec.items():
        if e["fmt"] == "TLUT" or sym in done_ci or "grid" not in e:
            continue
        f, s = FMTS[e["fmt"]]
        img = imgs[sym]
        if f == texfmt.CI:
            buf = np.zeros_like(img)
            g = np.clip(np.round(img[..., 0].astype(np.float32)), 0, 15 if s == texfmt.B4 else 255)
            buf[..., 0] = g.astype(np.uint8)
            img = buf
        write_inc(out, e["file"], texfmt.encode(img, f, s), e["ctype"])
        n += 1
    print(f"textures written: {n} (+{sum(1 for e in spec.values() if e['fmt'] == 'TLUT')} TLUTs), drawn by hooks: {HOOKED[0]}")
    return imgs


def main(argv):
    pristine, dirty, out = argv[:3]
    if not os.path.exists(out):
        shutil.copytree(pristine, out, ignore=shutil.ignore_patterns(".git", "cmake-build-release", "build"))
    copy_code(dirty, out)
    from . import drawn
    HOOKS[:] = drawn.HOOKS
    WRAP.update(wrap_modes(out))
    print(f"wrap modes: {sum(1 for v in WRAP.values() if v[0] or v[1])} textures tile (periodic grid upsampling)")
    print(f"hooks: {[h.__module__.split('.')[-1] + '.' + h.__name__ for h in HOOKS]}")
    gen_textures(out)
    from . import code_art
    code_art.apply(out)


if __name__ == "__main__":
    main(sys.argv[1:])
