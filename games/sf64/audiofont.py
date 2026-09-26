"""SF64 soundfont / sample-bank layout (Zelda-style audio engine, big-endian, offsets relative to the font).

Font:   u32 drumListOff, u32 instOff[numInst]   (no sfx list in SF64)
Inst:   u8 reloc, lo, hi, decayIdx; u32 envOff; TunedSample low, normal, high  (TunedSample = u32 sampleOff, f32 tuning)
Drum:   u8 decayIdx, pan, reloc, pad; TunedSample; u32 envOff
Sample: u32 codec:4 medium:2 bit26:1 reloc:1 size:24; u32 sampleAddr (in bank); u32 loopOff; u32 bookOff
Loop:   u32 start, end, count, pad; s16 predictorState[16] if count
Book:   s32 order, npred; s16 book[order*npred*8]
Font/bank tables come from src/audio/audio_tables.c (code, kept).
"""
import re
import struct

CODECS = {0: "ADPCM", 1: "S8", 2: "S16_INMEMORY", 3: "SMALL_ADPCM", 4: "REVERB", 5: "S16"}


def font_table(tree):
    src = open(f"{tree}/src/audio/audio_tables.c").read()
    fonts = []
    for m in re.finditer(r"SOUNDFONT_ENTRY\((0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+),\s*\w+,\s*\w+,\s*(\w+),\s*(\w+),\s*(\d+),\s*(\d+)\)", src):
        bank = {"SAMPLES_SFX": 0, "SAMPLES_MAP": 1, "SAMPLES_VOICE": 2, "SAMPLES_INST": 3}.get(m.group(3), 255)
        fonts.append({"off": int(m.group(1), 16), "size": int(m.group(2), 16), "bank": bank,
                      "ninst": int(m.group(5)), "ndrum": int(m.group(6))})
    banks = [(int(a, 16), int(b, 16)) for a, b in
             re.findall(r"\{\s*(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+),\s*MEDIUM_CART,\s*CACHE_LOAD_EITHER_NOSYNC\s*\}", src)]
    return fonts, banks


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def samples(bankbin, fonts):
    """Every Sample header reachable from the fonts: {(font_idx, hdr_off_in_bankbin): info}."""
    out = {}

    def tuned(fi, f, o):
        so = u32(bankbin, f["off"] + o)
        if so == 0:
            return
        h = f["off"] + so
        if h in out:
            return
        w0 = u32(bankbin, h)
        s = {"font": fi, "hdr": h, "codec": w0 >> 28, "size": w0 & 0xFFFFFF, "addr": u32(bankbin, h + 4),
             "loop": f["off"] + u32(bankbin, h + 8), "book": f["off"] + u32(bankbin, h + 12), "bank": f["bank"]}
        lp = s["loop"]
        s["lstart"], s["lend"], s["lcount"] = u32(bankbin, lp), u32(bankbin, lp + 4), u32(bankbin, lp + 8)
        bk = s["book"]
        s["order"], s["npred"] = struct.unpack_from(">ii", bankbin, bk)
        out[h] = s

    for fi, f in enumerate(fonts):
        base = f["off"]
        drum_list = u32(bankbin, base)
        for i in range(f["ninst"]):
            io = u32(bankbin, base + 4 + 4 * i)
            if io == 0:
                continue
            for k in range(3):
                tuned(fi, f, io + 8 + 8 * k)
        if drum_list:
            for i in range(f["ndrum"]):
                do = u32(bankbin, base + drum_list + 4 * i)
                if do:
                    tuned(fi, f, do + 4)
    return out
