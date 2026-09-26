"""SF64 audio: dirty-room facts and clean-room samples.

    python -m games.sf64.audio spec <dirty tree>          # DIRTY: facts -> games/sf64/spec/audio.json + bank_layout.bin
    python -m games.sf64.audio gen <clean tree>           # CLEAN: audio_bank.bin + audio_table.bin from the spec

Kept facts (user scope): per sample its length, loop points, a coarse spectral outline and a median pitch;
the soundfont structure (instrument key ranges, envelopes, tunings, pointers) with every ADPCM codebook
and loop predictor state zeroed (bank_layout.bin). Sequences (audio_seq.bin) are kept note data.
Generated: every sample waveform (resynthesised), our own VADPCM codebooks (same predictor count as the
slot, so the fonts keep their size and the audio heaps their layout), loop states from our own encoding.
Placeholder voices (TTS) replace bank 2 waveforms when games/sf64/voices/<bank>_<addr>.wav exists.
"""
import json
import os
import struct
import sys

import numpy as np

from cleanroom.audio import descriptor, vadpcm
from cleanroom.audio.pitch import median_f0
from cleanroom.decomp.gen import h32

from . import audiofont as A

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "spec")
VOICES = os.path.join(HERE, "voices")
NOMINAL = 32000


def book_from_bank(b, off):
    order, npred = struct.unpack_from(">ii", b, off)
    coefs = struct.unpack_from(">%dh" % (order * npred * 8), b, off + 8)
    return {"order": order, "npred": npred, "book": list(coefs)}


def spec(dirty):
    fonts, banks = A.font_table(dirty)
    bank = bytearray(open(os.path.join(dirty, "bin/us/rev1/audio_bank.bin"), "rb").read())
    table = open(os.path.join(dirty, "bin/us/rev1/audio_table.bin"), "rb").read()
    hdrs = A.samples(bytes(bank), fonts)
    uniq = {}
    for h in hdrs.values():
        uniq.setdefault((h["bank"], h["addr"]), []).append(h)
    out = {}
    for (bk, addr), hs in sorted(uniq.items()):
        h = hs[0]
        start = banks[bk][0] + addr
        data = table[start:start + h["size"]]
        n = h["size"] // 9 * 16
        pcm = vadpcm.decode(data, book_from_bank(bank, h["book"]), n)
        rate = NOMINAL
        d = {"bank": bk, "addr": addr, "size": h["size"], "n": n, "npred": h["npred"], "order": h["order"],
             "hdrs": [x["hdr"] for x in hs], "books": sorted(set(x["book"] for x in hs)),
             "loops": sorted(set(x["loop"] for x in hs)),
             "lstart": h["lstart"], "lend": h["lend"], "lcount": h["lcount"],
             "desc": descriptor.describe(pcm, rate), "f0": median_f0(pcm.astype(np.float64) / 32768.0, rate),
             "rms": float(np.sqrt(np.mean((pcm.astype(np.float64) / 32768.0) ** 2)))}
        out[f"{bk}_{addr:06x}"] = d
    # structure: zero every book's coefficients and every loop predictor state
    for d in out.values():
        for bo in d["books"]:
            order, npred = struct.unpack_from(">ii", bank, bo)
            bank[bo + 8:bo + 8 + order * npred * 16] = bytes(order * npred * 16)
        for lo in d["loops"]:
            if struct.unpack_from(">I", bank, lo + 8)[0]:
                bank[lo + 16:lo + 48] = bytes(32)
    os.makedirs(SPEC, exist_ok=True)
    json.dump({"banks": banks, "samples": out}, open(os.path.join(SPEC, "audio.json"), "w"))
    open(os.path.join(SPEC, "bank_layout.bin"), "wb").write(bank)
    print(f"samples: {len(out)} unique ({len(hdrs)} headers); per bank "
          f"{[sum(1 for d in out.values() if d['bank'] == k) for k in range(4)]}; loops {sum(1 for d in out.values() if d['lcount'])}")


def k_predictors(x, k):
    """Our own order-2 predictor set with k entries: k-means over per-frame least-squares fits."""
    fits = []
    for s in range(2, len(x) - 16, 16):
        y, p1, p2 = x[s:s + 16], x[s - 1:s + 15], x[s - 2:s + 14]
        if (y ** 2).sum() < 1e3:
            continue
        a, *_ = np.linalg.lstsq(np.stack([p1, p2], 1), y, rcond=None)
        fits.append(a)
    base = [(0.0, 0.0), (1.0, 0.0), (1.8, -0.82), (1.95, -0.96), (1.5, -0.6), (0.5, 0.0), (1.9, -0.92), (1.2, -0.3)]
    if len(fits) < k:
        return base[:k]
    f = np.clip(np.asarray(fits), [-1.95, -0.98], [1.95, 0.98])
    c = f[np.linspace(0, len(f) - 1, k).astype(int)][np.argsort(f[np.linspace(0, len(f) - 1, k).astype(int), 0])].copy()
    order = np.argsort(f[:, 0])
    c = np.stack([f[order[int((i + 0.5) * len(f) / k)]] for i in range(k)])
    for _ in range(12):
        lab = np.argmin(((f[:, None, :] - c[None]) ** 2).sum(-1), 1)
        for j in range(k):
            if (lab == j).any():
                c[j] = f[lab == j].mean(0)
    out = []
    for a1, a2 in c:
        a2 = float(np.clip(a2, -0.98, 0.98))
        out.append((float(np.clip(a1, -(1 - a2) + 0.02, (1 - a2) - 0.02)), a2))
    return out


def waveform(key, d):
    n = d["n"]
    vp = os.path.join(VOICES, key + ".wav")
    if d["bank"] in (1, 2) and os.path.exists(vp):
        from .voices import read_wav
        x = read_wav(vp)
        x = np.concatenate([x, np.zeros(max(0, n - len(x)))])[:n]
        peak = np.abs(x).max() or 1.0
        x = x / peak * 0.8
    else:
        x = descriptor.synthesize(d["desc"], n, NOMINAL, seed=h32("sf64smp", key))
    x = np.asarray(x, np.float64)
    if d["lcount"] and d["lend"] > d["lstart"] + 32:
        x = descriptor.make_loop_seamless(x, d["lstart"], min(d["lend"], n))
    # loudness: match the slot's kept RMS (the synthesiser and TTS output near full scale, which made the
    # game's mix clip); never exceed 0.98 peak
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    if rms > 1e-6 and d.get("rms"):
        x = x * (d["rms"] / rms)
        peak = float(np.abs(x).max())
        if peak > 0.98:
            x = x * (0.98 / peak)
    return np.clip(np.round(x * 32767.0), -32768, 32767).astype(np.int64)


def _one(item):
    key, d = item
    pcm = waveform(key, d)
    preds = k_predictors(pcm.astype(np.float64), d["npred"])
    book = vadpcm.make_book(preds)
    while max(abs(v) for v in book["book"]) > 32767:   # keep every coefficient in s16
        preds = [(a1 * 0.97, a2 * 0.97) for a1, a2 in preds]
        book = vadpcm.make_book(preds)
    data, book, dec = vadpcm.encode(pcm, book)
    data = (data + bytes(d["size"]))[:d["size"]]
    st = vadpcm.loop_state(dec, d["lstart"]) if d["lcount"] else None
    return key, data, [int(np.clip(v, -32768, 32767)) for v in book["book"]], st


def gen(clean, jobs=None):
    from multiprocessing import Pool
    J = json.load(open(os.path.join(SPEC, "audio.json")))
    banks, S = J["banks"], J["samples"]
    bank = bytearray(open(os.path.join(SPEC, "bank_layout.bin"), "rb").read())
    table = bytearray(banks[-1][0] + banks[-1][1])
    items = sorted(S.items(), key=lambda kv: -kv[1]["n"])   # longest first for load balance
    with Pool(jobs or max(2, (os.cpu_count() or 4) - 2)) as pool:
        for i, (key, data, coefs, st) in enumerate(pool.imap_unordered(_one, items, chunksize=2)):
            d = S[key]
            start = banks[d["bank"]][0] + d["addr"]
            table[start:start + d["size"]] = data
            blob = struct.pack(">ii", 2, d["npred"]) + struct.pack(">%dh" % len(coefs), *coefs)
            for bo in d["books"]:
                bank[bo:bo + len(blob)] = blob
            if st is not None:
                for lo in d["loops"]:
                    bank[lo + 16:lo + 48] = struct.pack(">16h", *st)
            if i % 100 == 0:
                print(f"  {i}/{len(S)}", flush=True)
    out = os.path.join(clean, "bin", "us", "rev1")
    open(os.path.join(out, "audio_bank.bin"), "wb").write(bank)
    open(os.path.join(out, "audio_table.bin"), "wb").write(table)
    dev = os.path.join(clean, "DEV_RETAIL_AUDIO")
    if os.path.exists(dev):
        os.remove(dev)
    print(f"audio: {len(S)} samples resynthesised; bank {len(bank)} B, table {len(table)} B")


if __name__ == "__main__":
    {"spec": spec, "gen": gen}[sys.argv[1]](sys.argv[2])
