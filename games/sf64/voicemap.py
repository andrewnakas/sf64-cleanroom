"""Which voice sample speaks which radio message (for placeholder TTS and the practice pack).

Hypothesis (from counts): message block msgId // 1000 = b plays from voice font F(b) (per-level fonts 3..20),
whose instruments are [3 radio effects] + one per message of the block. This script checks the ordering by
correlating each instrument's sample length with its message's text length, and writes voice_lines.json.

    python -m games.sf64.voicemap [--write]
"""
import json
import os
import re
import sys

import numpy as np

from . import audiofont as A

HERE = os.path.dirname(os.path.abspath(__file__))
RADIO = "D:/n64work/sf64/pristine/src/assets/ast_radio/ast_radio.c"
CH = {"SPC": " ", "PRD": ".", "CMA": ",", "EXM": "!", "QST": "?", "DSH": "-", "APS": "'", "LPR": "(", "RPR": ")",
      "CLN": ":", "NWL": " ", "QSP": "", "HSP": " "}


def messages(src):
    look = [int(x) for x in re.findall(r"\{ (\d+), gMsg_ID_\d+ \}", src)]
    out = {}
    for i in look:
        m = re.search(r"u16 gMsg_ID_%d\[\] = \{(.*?)\};" % i, src, re.S)
        toks = re.findall(r"\b\w+\b", m.group(1)) if m else []
        txt = "".join(t[1:] if t.startswith("_") else CH.get(t, "") for t in toks)
        out[i] = re.sub(r"\s+", " ", txt).strip()
    return look, out


def inst_samples(bankbin, f):
    res = []
    for i in range(f["ninst"]):
        io = A.u32(bankbin, f["off"] + 4 + 4 * i)
        if not io:
            res.append(None)
            continue
        so = A.u32(bankbin, f["off"] + io + 0x10)
        if not so:
            res.append(None)
            continue
        h = f["off"] + so
        res.append((h, A.u32(bankbin, h) & 0xFFFFFF, A.u32(bankbin, h + 4)))
    return res


def main(argv):
    tree = "D:/n64work/sf64/pristine"
    src = open(os.path.join("D:/n64work/sf64/dirty", "src/assets/ast_radio/ast_radio.c")).read()
    look, text = messages(src)
    fonts, banks = A.font_table(tree)
    bank = open("D:/n64work/sf64/dirty/bin/us/rev1/audio_bank.bin", "rb").read() if os.path.exists(
        "D:/n64work/sf64/dirty/bin/us/rev1/audio_bank.bin") else open(os.path.join(HERE, "spec", "bank_layout.bin"), "rb").read()
    blocks = sorted(set(i // 1000 for i in look))
    lines = {}
    for b in blocks:
        ids = sorted(i for i in look if i // 1000 == b)
        best = None
        for fi in range(1, 21):
            S = inst_samples(bank, fonts[fi])
            valid = [s for s in S if s]
            for off in range(0, 5):
                if off + len(ids) > len(valid):
                    continue
                a = np.array([valid[off + k][1] for k in range(len(ids))], float)
                t = np.array([len(text[i]) for i in ids], float)
                if a.std() == 0 or t.std() == 0:
                    continue
                r = float(np.corrcoef(a, t)[0, 1])
                if best is None or r > best[0]:
                    best = (r, fi, off, len(valid))
        if best is None:
            continue
        r, fi, off, nv = best
        print(f"block {b:2d}: {len(ids):3d} msgs -> font {fi:2d} ({nv} instruments) offset {off}  r={r:.2f}")
        if r > 0.6:
            valid = [s for s in inst_samples(bank, fonts[fi]) if s]
            for k, i in enumerate(ids):
                h, size, addr = valid[off + k]
                lines[str(i)] = {"text": text[i], "font": fi, "sample": f"2_{addr:06x}", "adpcm_bytes": size}
    if "--write" in argv:
        json.dump(lines, open(os.path.join(HERE, "voice_lines.json"), "w"), indent=1)
        print(f"voice_lines.json: {len(lines)} lines")


if __name__ == "__main__":
    main(sys.argv[1:])
