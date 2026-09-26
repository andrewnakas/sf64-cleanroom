"""Taint report: generated SF64 assets vs the retail extraction (dev check, dirty tree needed).

Scanned (clean vs every retail stream, cleanroom.taint windows, runs >= FAIL_RUN fail):
  * every texture/TLUT .inc.c as stored bytes and, for non-CI formats, decoded RGBA,
  * every sample: its VADPCM bytes in audio_table.bin and its decoded PCM,
  * the ADPCM codebooks and loop states in audio_bank.bin,
  * the pixel arrays the decomp keeps in C (fox_wheels.c, sys_fault.c).
Kept facts (note sequences, soundfont structure, code, geometry) are listed, not scanned.

    python -m games.sf64.taint_report <dirty tree> <clean tree>
"""
import json
import os
import re
import struct
import sys

import numpy as np

from cleanroom import taint
from cleanroom.audio import vadpcm
from cleanroom.gfx import texfmt

from .extract_spec import CSIZE, FMTS, inc_bytes

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")


def c_array(path, name):
    s = open(path).read()
    m = re.search(r"\b%s\[[^\]]*\]\s*=\s*\{(.*?)\n\};" % re.escape(name), s, re.S)
    vals = re.findall(r"0x[0-9A-Fa-f]+", m.group(1))
    w = max(len(v) - 2 for v in vals)
    cs = 1 if w <= 2 else 2 if w <= 4 else 4
    return b"".join(int(v, 16).to_bytes(cs, "big") for v in vals)


def streams(tree, tex, aud):
    for sym, e in tex.items():
        b = inc_bytes(os.path.join(tree, e["file"]), CSIZE[e["ctype"]])
        yield "tex:" + sym, b
        if e["fmt"] != "TLUT" and "w" in e:
            f, s = FMTS[e["fmt"]]
            if f != texfmt.CI:
                img = texfmt.decode(b, e["w"], e["h"], f, s)
                yield "rgba:" + sym, img[img[..., 3] > 0].tobytes()
    table = open(os.path.join(tree, "bin/us/rev1/audio_table.bin"), "rb").read()
    bank = open(os.path.join(tree, "bin/us/rev1/audio_bank.bin"), "rb").read()
    banks = aud["banks"]
    for key, d in aud["samples"].items():
        st = banks[d["bank"]][0] + d["addr"]
        data = table[st:st + d["size"]]
        yield "adpcm:" + key, data
        bo = d["books"][0]
        order, npred = struct.unpack_from(">ii", bank, bo)
        book = {"order": order, "npred": npred,
                "book": list(struct.unpack_from(">%dh" % (order * npred * 8), bank, bo + 8))}
        yield "book:" + key, bank[bo + 8:bo + 8 + order * npred * 16]
        yield "pcm:" + key, vadpcm.decode(data, book, d["n"]).astype(">i2").tobytes()
    yield "code:fox_wheels", b"".join(c_array(os.path.join(tree, "src/engine/fox_wheels.c"), n)
                                      for n in ("D_Tex_800DACB8", "D_Tex_800DB4B8", "D_TLUT_800DB4B8"))
    yield "code:sys_fault", c_array(os.path.join(tree, "src/sys/sys_fault.c"), "sFaultCharPixelFlags")


def main(argv):
    dirty, clean = argv[1], argv[2]
    tex = json.load(open(os.path.join(SPEC, "textures.json")))
    aud = json.load(open(os.path.join(SPEC, "audio.json")))
    index = taint.build_index(s for _, s in streams(dirty, tex, aud))
    hits = taint.scan(index, streams(clean, tex, aud))
    bad = sorted((h for h in hits if h[3] >= taint.FAIL_RUN), key=lambda h: -h[3])
    n = sum(1 for _ in streams(clean, tex, {"banks": aud["banks"], "samples": {}}))
    print(f"scanned {len(tex)} textures/TLUTs (+decoded) and {len(aud['samples'])} samples (bytes, PCM, books); "
          f"{len(hits)} streams with short coincidental matches; {len(bad)} failing (run >= {taint.FAIL_RUN} B)")
    print("kept facts, not scanned: audio_seq.bin (note data), soundfont structure (books/loop states regenerated), "
          "asm (boot code, microcode, libultra), Torch geometry/animation/script C")
    for label, off, nw, run in bad[:12]:
        print(f"  FAIL {label} run {run} B ({nw} windows)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
