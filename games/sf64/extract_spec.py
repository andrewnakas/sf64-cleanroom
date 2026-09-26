"""DIRTY ROOM: Torch-extracted SF64 assets -> clean-room spec (coarse facts only).

    python -m games.sf64.extract_spec <dirty tree> [--png D:/n64work/sf64/dirty_png]

Textures: every TEXTURE entry of assets/yaml/us/rev1/*.yaml whose data Torch wrote to
src/assets/<file>/<symbol>.<fmt>.inc.c. Facts kept: format, size, TLUT link/colour count,
a colour grid (4x4, 16x16 for >= 128 px) and a 2-bit alpha outline (cleanroom.decomp.spec).
CI textures are decoded through their TLUT first (the facts are about the picture, the
palette is rebuilt by generate.py). --png writes decoded dirty PNGs for contact sheets
(dirty room only, never committed).
"""
import json
import os
import re
import sys

import numpy as np

from cleanroom.decomp.spec import texture_fact
from cleanroom.gfx import png, texfmt

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")

FMTS = {"RGBA16": (texfmt.RGBA, texfmt.B16), "RGBA32": (texfmt.RGBA, texfmt.B32),
        "IA8": (texfmt.IA, texfmt.B8), "IA16": (texfmt.IA, texfmt.B16), "IA4": (texfmt.IA, texfmt.B4),
        "I4": (texfmt.I, texfmt.B4), "I8": (texfmt.I, texfmt.B8),
        "CI4": (texfmt.CI, texfmt.B4), "CI8": (texfmt.CI, texfmt.B8), "TLUT": (texfmt.RGBA, texfmt.B16)}
CSIZE = {"u8": 1, "s8": 1, "u16": 2, "s16": 2, "u32": 4, "s32": 4, "u64": 8, "Gfx": 8}
ENTRY = re.compile(r"^(\w+):[ \t]*(?:#[^\n]*)?\n\s*\{([^}]*)\}|^(\w+):[ \t]*\{([^}]*)\}", re.M)


def yaml_entries(path):
    """Tiny parser for Torch's one-line flow maps: returns [(name, {k: v})]."""
    txt = open(path, encoding="utf-8").read()
    out = []
    for m in ENTRY.finditer(txt):
        d = {}
        name, body = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        for kv in body.split(","):
            if ":" in kv:
                k, v = kv.split(":", 1)
                d[k.strip()] = v.strip()
        out.append((name, d))
    # block-style entries ("name:\n  type: TEXTURE\n  width: ...")
    for m in re.finditer(r"^(\w+):[ \t]*\n((?:  \w+:[^\n]*\n?)+)", txt, re.M):
        d = dict((k.strip(), v.strip()) for k, v in (ln.split(":", 1) for ln in m.group(2).splitlines() if ":" in ln))
        if "type" in d:
            out.append((m.group(1), d))
    return out


def inc_bytes(path, csize):
    vals = re.findall(r"0x[0-9A-Fa-f]+|\b\d+\b", open(path).read())
    return b"".join(int(v, 0).to_bytes(csize, "big") for v in vals)


def main(argv):
    tree = argv[0]
    png_dir = argv[argv.index("--png") + 1] if "--png" in argv else None
    ydir = os.path.join(tree, "assets", "yaml", "us", "rev1")
    tex, tluts, missing, bad = {}, {}, [], []
    for yf in sorted(os.listdir(ydir)):
        base = os.path.splitext(yf)[0]
        ents = [(n, d) for n, d in yaml_entries(os.path.join(ydir, yf)) if d.get("type") == "TEXTURE"]
        by_off = {int(d["offset"], 16): d["symbol"] for _, d in ents}
        for name, d in ents:
            sym, fmt = d["symbol"], d["format"]
            rel = f"src/assets/{base}/{name}.{fmt.lower()}.inc.c"
            p = os.path.join(tree, rel)
            if not os.path.exists(p):
                missing.append(rel)
                continue
            data = inc_bytes(p, CSIZE[d.get("ctype", "u8")])
            e = {"file": rel, "fmt": fmt, "ctype": d.get("ctype", "u8"), "bytes": len(data)}
            if fmt == "TLUT":
                e["colors"] = int(d["colors"], 0)
                tluts[sym] = (e, data)
            else:
                e["w"], e["h"] = int(d["width"], 0), int(d["height"], 0)
                if "tlut" in d and fmt.startswith("CI"):
                    e["tlut"] = by_off.get(int(d["tlut"], 16))
                e["_data"] = data
            tex[sym] = e
    # CI textures without a yaml tlut: take the TLUT loaded just before them in the asset DLs
    for yf in sorted(os.listdir(os.path.join(tree, "src", "assets"))):
        cf = os.path.join(tree, "src", "assets", yf, yf + ".c")
        if not os.path.exists(cf):
            continue
        last = None
        for m in re.finditer(r"gsDPLoadTLUT\w*\(\s*(\w+)|gsDPLoadTextureBlock\w*\(\s*(\w+)|gsDPLoadMultiBlock\w*\(\s*(\w+)",
                             open(cf).read()):
            if m.group(1):
                last = m.group(1)
            else:
                t = tex.get(m.group(2) or m.group(3))
                if t and t["fmt"].startswith("CI") and not t.get("tlut") and last in tluts:
                    t["tlut"] = last
                    t["tlut_from_dl"] = True
    for sym, (e, data) in tluts.items():
        e["_pal"] = texfmt.decode(data, e["colors"], 1, texfmt.RGBA, texfmt.B16).reshape(-1, 4)
    n_png = 0
    for sym, e in tex.items():
        if e["fmt"] == "TLUT":
            continue
        fmt_name = e["fmt"]
        f, s = FMTS[fmt_name]
        pal = None
        if f == texfmt.CI:
            t = tex.get(e.get("tlut") or "")
            if t is None or "_pal" not in t:
                bad.append(f"{sym} (tlut {e.get('tlut')} missing)")
                pal = np.stack([np.arange(256)] * 3 + [np.full(256, 255)], -1)
            else:
                pal = t["_pal"]
                need = 16 if s == texfmt.B4 else 256
                if len(pal) < need:
                    pal = np.concatenate([pal, np.zeros((need - len(pal), 4), np.uint8)])
        need = texfmt.texel_bytes(e["w"], e["h"], s)
        if len(e["_data"]) < need:
            bad.append(f"{sym} ({len(e['_data'])} < {need} bytes)")
            continue
        rgba = texfmt.decode(e["_data"], e["w"], e["h"], f, s, pal)
        e.update(texture_fact(e["file"], rgba))
        e["fmt"] = fmt_name
        if png_dir:
            op = os.path.join(png_dir, e["file"].split("/")[2], sym + ".png")
            os.makedirs(os.path.dirname(op), exist_ok=True)
            png.write(op, rgba)
            n_png += 1
    for e in tex.values():
        e.pop("_data", None)
        e.pop("_pal", None)
    # TLUT spec: only size + which textures use it (colours are rebuilt from the pictures)
    for sym, e in tex.items():
        if e["fmt"] == "TLUT":
            e["users"] = sorted(s for s, t in tex.items() if t.get("tlut") == sym)
    os.makedirs(SPEC, exist_ok=True)
    json.dump(tex, open(os.path.join(SPEC, "textures.json"), "w"), indent=0, sort_keys=True)
    kinds = {}
    for e in tex.values():
        kinds[e["fmt"]] = kinds.get(e["fmt"], 0) + 1
    print(f"textures: {len(tex)} {kinds}")
    print(f"missing .inc.c: {len(missing)} {missing[:3]}")
    print(f"problems: {len(bad)} {bad[:5]}")
    if png_dir:
        print(f"dirty pngs: {n_png} -> {png_dir}")


if __name__ == "__main__":
    main(sys.argv[1:])
