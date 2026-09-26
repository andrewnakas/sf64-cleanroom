"""Voice practice pack (PERSONAL USE: reference clips come from the user's own ROM extraction; written outside the
repo, never published).

Per character: practice_<WHO>_call_and_response.wav = for each line: the reference line (all its speech samples
decoded with the retail codebooks, at 22.05 kHz), 0.3 s, an 80 ms 880 Hz beep, then a gap of 1.5x + 1.5 s to
repeat it in your own voice. SCRIPT.txt lists the lines in track order; lines.json maps each track slot to the
message id and its sample keys, so recordings can later be cut and placed (games/sf64/voices/<key>.wav).

    python -m games.sf64.practice <dirty tree> <out dir>
"""
import json
import os
import struct
import sys
import wave

import numpy as np

from cleanroom.audio import vadpcm

from .voices import speaker

HERE = os.path.dirname(os.path.abspath(__file__))
HZ = 22050


def main(argv):
    dirty, out = argv[1], argv[2]
    J = json.load(open(os.path.join(HERE, "spec", "audio.json")))
    L = json.load(open(os.path.join(HERE, "voice_lines.json")))
    S = json.load(open(os.path.join(HERE, "speakers.json")))
    bank = open(os.path.join(dirty, "bin/us/rev1/audio_bank.bin"), "rb").read()
    table = open(os.path.join(dirty, "bin/us/rev1/audio_table.bin"), "rb").read()
    banks = J["banks"]
    os.makedirs(out, exist_ok=True)

    def clip(key, hz):
        d = J["samples"][key]
        st = banks[d["bank"]][0] + d["addr"]
        bo = d["books"][0]
        order, npred = struct.unpack_from(">ii", bank, bo)
        book = {"order": order, "npred": npred,
                "book": list(struct.unpack_from(">%dh" % (order * npred * 8), bank, bo + 8))}
        x = vadpcm.decode(table[st:st + d["size"]], book, d["n"]).astype(np.float32) / 32768
        return np.interp(np.arange(0, len(x) * HZ / hz) * hz / HZ, np.arange(len(x)), x).astype(np.float32)

    def wr(path, x):
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(HZ)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())

    beep = (0.2 * np.sin(2 * np.pi * 880 * np.arange(int(0.08 * HZ)) / HZ)).astype(np.float32)
    tracks, script, manifest = {}, {}, {}
    for mid in sorted(L, key=int):
        v = L[mid]
        notes = [n for n in v.get("notes", []) if "%d_%06x" % (n["bank"], n["addr"]) in v.get("speech", [])]
        if not notes:
            continue
        who = speaker(mid, S)
        x = np.concatenate([clip("%d_%06x" % (n["bank"], n["addr"]), n["rate_hz"]) for n in notes])
        gap = np.zeros(int((len(x) / HZ * 1.5 + 1.5) * HZ), np.float32)
        tracks.setdefault(who, []).extend([x, np.zeros(int(0.3 * HZ), np.float32), beep, gap])
        k = len(manifest.setdefault(who, [])) + 1
        manifest[who].append({"n": k, "msg": mid, "text": v["text"], "samples": ["%d_%06x" % (n["bank"], n["addr"]) for n in notes],
                              "secs": round(len(x) / HZ, 2), "frames": len(x)})
        script.setdefault(who, []).append(f"{k:03d}  msg {mid:>5}  {len(x) / HZ:4.1f}s  \"{v['text']}\"")
    lines = ["Star Fox 64 voice practice script. For each character, play practice_<WHO>_call_and_response.wav",
             "and repeat each line after the beep, in character (2-3 takes if you like).",
             "Speakers marked from the game's code; lines whose speaker the code doesn't name are guessed",
             "(ROB64 for the title, General Pepper for the map, Fox otherwise).", ""]
    for who in sorted(tracks):
        wr(os.path.join(out, f"practice_{who}_call_and_response.wav"), np.concatenate(tracks[who]))
        lines += [f"== {who} ({len(script[who])} lines, practice_{who}_call_and_response.wav)"] + script[who] + [""]
    lines += ["These reference clips come from your own ROM: practice only, do not share or commit them."]
    open(os.path.join(out, "SCRIPT.txt"), "w", encoding="utf8").write("\n".join(lines))
    json.dump(manifest, open(os.path.join(out, "lines.json"), "w"), indent=1)
    print(f"practice pack: {sum(len(v) for v in manifest.values())} lines, "
          f"{', '.join(f'{w} {len(v)}' for w, v in sorted(manifest.items()))} -> {out}")


if __name__ == "__main__":
    main(sys.argv)
