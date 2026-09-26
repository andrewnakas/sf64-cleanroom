"""Import the user's own recordings made against the practice call-and-response tracks.

    python -m games.sf64.takes cut <recording.wav|m4a|...> <WHO> <practice pack dir>
        aligns the recording to the track's beeps (layout from <pack>/lines.json), cuts each response window,
        trims it to the voiced part and writes games/sf64/takes/<WHO>/<msg>.wav (22.05 kHz or the recording rate)
    python -m games.sf64.takes place [WHO]
        spreads every take over its line's speech samples (voices.fit_split) -> games/sf64/voices/<key>.wav,
        replacing the TTS placeholder for those lines; then rebuild audio (build_clean.sh --audio)

Only the lengths in lines.json are used to rebuild the layout; the reference clips are not read.
"""
import json
import os
import sys

import numpy as np

from cleanroom.voice.takes import find_offset, load_audio, voiced

from . import voices

HERE = os.path.dirname(os.path.abspath(__file__))
TAKES = os.path.join(HERE, "takes")
HZ = 22050


def layout(pack, who):
    t, out = 0.0, []
    for row in json.load(open(os.path.join(pack, "lines.json")))[who]:
        clip = row.get("frames", int(round(row["secs"] * HZ))) / HZ
        beep_t = t + clip + 0.3
        gap = int((clip * 1.5 + 1.5) * HZ) / HZ
        out.append((row["msg"], t, clip, beep_t, beep_t + 0.08, gap))
        t = beep_t + 0.08 + gap
    return out


def cut(path, who, pack):
    x, sr = load_audio(path)
    lay = layout(pack, who)
    off, conf = find_offset(x, sr, lay)
    d = os.path.join(TAKES, who)
    os.makedirs(d, exist_ok=True)
    short = 0
    for msg, cs, cl, bs, be, gap in lay:
        a, b = int((be + off) * sr), int((be + off + gap) * sr)
        seg = voiced(x[a:b], sr)
        voices.write_wav(os.path.join(d, f"{msg}.wav"), seg, sr)
        short += len(seg) < 0.05 * sr
    print(f"{who}: offset {off:+.2f}s (beep match {conf:.1f}); {len(lay)} takes, {short} empty -> {d}")


def place(only=None):
    L = json.load(open(os.path.join(HERE, "voice_lines.json")))
    n = 0
    for who in sorted(os.listdir(TAKES)) if os.path.isdir(TAKES) else []:
        if only and who != only:
            continue
        for f in os.listdir(os.path.join(TAKES, who)):
            mid = f[:-4]
            v = L.get(mid)
            if not v:
                continue
            notes = [m for m in v["notes"] if "%d_%06x" % (m["bank"], m["addr"]) in v.get("speech", [])]
            x = voices.read_wav(os.path.join(TAKES, who, f))
            if len(x) < 100 or not notes:
                continue
            import wave
            with wave.open(os.path.join(TAKES, who, f)) as w:
                sr = w.getframerate()
            x = voices.radio(x, sr, 0.0)
            for key, (y, hz) in voices.fit_split(x, sr, notes).items():
                voices.write_wav(os.path.join(voices.OUT, key + ".wav"), y, hz)
            n += 1
    print(f"placed {n} recorded lines into {voices.OUT}; now run games/sf64/build_clean.sh --audio")


if __name__ == "__main__":
    if sys.argv[1] == "cut":
        cut(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        place(sys.argv[2] if len(sys.argv) > 2 else None)
