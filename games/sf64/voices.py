"""Placeholder voices: every radio line spoken by Piper TTS in a per-character voice (our own performances of
the decomp's text; no original audio, no cloning), split across the line's speech samples.

voice_lines.json (from voiceseq.py) gives, per message id, the text and the notes the voice sequence plays:
sample key, sample length and playback rate. The speaker comes from the decomp's Radio_PlayMessage(msg, RCID_*)
calls (speakers.json, from speakers()); unknown speakers fall back by message block.
Writes games/sf64/voices/<sample key>.wav (mono, the sample's playback rate, exactly its length);
audio.py uses them instead of the resynthesised outline for those slots.

    python -m games.sf64.voices speakers          # scan the decomp for msg -> RCID, write speakers.json
    python -m games.sf64.voices build [ids...]    # speak lines (cached per line)
"""
import json
import os
import re
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "voices")
PIPER = os.environ.get("PIPER_VOICES", "C:/Users/andre/n64work/piper_voices")
PRISTINE = "D:/n64work/sf64/pristine"

# character -> (piper model, semitones, speed (length scale), radio grit)
CAST = {
    "FOX": ("en_US-joe-medium", 1.0, 0.95, 0.0),
    "FALCO": ("en_US-ryan-high", 0.5, 0.9, 0.0),
    "PEPPY": ("en_US-ryan-high", -2.5, 1.05, 0.0),
    "SLIPPY": ("en_US-joe-medium", 6.0, 0.9, 0.0),
    "ROB64": ("en_US-ryan-high", -1.5, 1.1, 1.0),
    "GEN_PEPPER": ("en_US-ryan-high", -4.0, 1.05, 0.0),
    "WOLF": ("en_US-ryan-high", -3.0, 1.0, 0.0),
    "LEON": ("en_US-joe-medium", 3.0, 1.05, 0.0),
    "PIGMA": ("en_US-joe-medium", -1.5, 1.0, 0.0),
    "ANDREW": ("en_US-joe-medium", 4.0, 0.95, 0.0),
    "KATT": ("en_US-kristin-medium", 1.0, 0.95, 0.0),
    "BILL": ("en_US-ryan-high", -1.0, 1.0, 0.0),
    "JAMES": ("en_US-ryan-high", -2.0, 1.1, 0.0),
    "ANDROSS": ("en_US-ryan-high", -6.0, 1.15, 0.0),
    "BOSS": ("en_US-joe-medium", -2.5, 1.0, 0.0),
    "TR": ("en_US-amy-medium", 0.0, 1.0, 0.0),
}


def who_of(rcid):
    r = rcid.replace("RCID_", "")
    for k in ("GEN_PEPPER", "ROB64", "FOX", "FALCO", "PEPPY", "SLIPPY", "WOLF", "LEON", "PIGMA", "ANDREW", "KATT",
              "BILL", "JAMES", "ANDROSS", "TR"):
        if r.startswith(k):
            return k
    if r.startswith("BOSS") or r.startswith("CAIMAN"):
        return "BOSS"
    return None


def speakers():
    rx = re.compile(r"gMsg_ID_(\d+)[^;{}]{0,80}?(RCID_[A-Z0-9_]+)")
    out = {}
    for root, _, files in os.walk(os.path.join(PRISTINE, "src")):
        for f in files:
            if f.endswith(".c"):
                for m in rx.finditer(open(os.path.join(root, f), errors="ignore").read()):
                    w = who_of(m.group(2))
                    if w:
                        out.setdefault(m.group(1), w)
    # tables without an RCID next to the message: the title's sGralPepperMsg and the map's sBriefingMsg pairs
    # (General Pepper's briefing, then Fox's reply)
    title = open(os.path.join(PRISTINE, "src/overlays/ovl_menu/fox_title.c")).read()
    m = re.search(r"sGralPepperMsg\[\d+\] = \{(.*?)\};", title, re.S)
    for i in re.findall(r"gMsg_ID_(\d+)", m.group(1)):
        out[i] = "GEN_PEPPER"
    mp = open(os.path.join(PRISTINE, "src/overlays/ovl_menu/fox_map.c")).read()
    m = re.search(r"sBriefingMsg\[\d+\]\[2\] = \{(.*?)\};", mp, re.S)
    for a, b in re.findall(r"\{ gMsg_ID_(\d+), gMsg_ID_(\d+) \}", m.group(1)):
        out.setdefault(a, "GEN_PEPPER")
        out.setdefault(b, "FOX")
    json.dump(out, open(os.path.join(HERE, "speakers.json"), "w"), indent=0, sort_keys=True)
    print(f"speakers: {len(out)} messages with a known speaker")


def speaker(mid, S):
    if mid in S:
        return S[mid]
    i = int(mid)
    if i < 1000:
        return "ROB64"
    if i < 2000:
        return "GEN_PEPPER"
    return "FOX"


_V = {}


def piper(model, text, length):
    from piper import PiperVoice, SynthesisConfig
    if model not in _V:
        _V[model] = PiperVoice.load(os.path.join(PIPER, model + ".onnx"))
    v = _V[model]
    cfg = SynthesisConfig(length_scale=length, noise_scale=0.7, noise_w_scale=0.8)
    x = np.concatenate([c.audio_float_array for c in v.synthesize(text, syn_config=cfg)]).astype(np.float64)
    return x, v.config.sample_rate


def trim(x, thr=0.01):
    idx = np.nonzero(np.abs(x) > thr)[0]
    return x[max(0, idx[0] - 200):idx[-1] + 200] if len(idx) else x[:0]


def resample(x, sr, hz, n=None):
    n = n or int(round(len(x) * hz / sr))
    if len(x) < 2 or n < 1:
        return np.zeros(max(n, 0))
    # band-limit before decimating (voice slots play at 6-8 kHz)
    if hz < sr:
        k = max(1, int(sr / hz))
        x = np.convolve(x, np.ones(k) / k, "same")
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def radio(x, sr, grit):
    """A little radio: gentle high-pass, soft clip, optional ring modulation for the robot."""
    y = x - np.convolve(x, np.ones(40) / 40, "same")
    if grit:
        t = np.arange(len(y)) / sr
        y = y * (0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 70 * t)))
    return np.tanh(y * 2.0) / np.tanh(2.0)


def speak_line(mid, v, who):
    model, semis, speed, grit = CAST[who]
    notes = [n for n in v["notes"] if "%d_%06x" % (n["bank"], n["addr"]) in v.get("speech", [])]
    if not notes:
        return {}
    total = sum(n["size"] // 9 * 16 / n["rate_hz"] for n in notes)
    f = 2 ** (semis / 12)
    text = v["text"].strip() or "..."
    x = None
    for k in range(7):
        raw, sr = piper(model, text, speed * f * (0.88 ** k))
        y = trim(raw)
        y = resample(y, sr * f, sr)          # pitch lift (the line was spoken slower by f)
        if len(y) / sr <= total * 0.98 or k == 6:
            x = y
            break
    if len(x) / sr > total:
        x = resample(x, sr, sr, int(total * sr * 0.98))
    x = radio(x, sr, grit)
    return fit_split(x, sr, notes, total)


def fit_split(x, sr, notes, total=None):
    """Spread one spoken line over the line's speech samples: cut at quiet points near each sample's share of the
    time, resample each piece to that sample's playback rate and exact length. -> {key: (float array, rate)}"""
    total = total or sum(n["size"] // 9 * 16 / n["rate_hz"] for n in notes)
    if len(x) / sr > total:
        x = resample(x, sr, sr, int(total * sr * 0.98))
    x = x / (np.abs(x).max() + 1e-9) * 0.85
    out, pos = {}, 0
    env = np.convolve(np.abs(x), np.ones(int(sr * 0.02)) / int(sr * 0.02), "same")
    bounds = np.cumsum([n["size"] // 9 * 16 / n["rate_hz"] for n in notes]) / total * len(x)
    for i, n in enumerate(notes):
        end = len(x) if i == len(notes) - 1 else int(bounds[i])
        if i < len(notes) - 1:
            lo, hi = max(pos + 1, end - int(0.15 * sr)), min(len(x) - 1, end + int(0.15 * sr))
            if hi > lo:
                end = lo + int(np.argmin(env[lo:hi]))
        seg = x[pos:end]
        nn = n["size"] // 9 * 16
        seg = resample(seg, sr, n["rate_hz"])[:nn]
        full = np.zeros(nn)
        full[:len(seg)] = seg
        out["%d_%06x" % (n["bank"], n["addr"])] = (full, n["rate_hz"])
        pos = end
    return out


def write_wav(path, x, hz):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(hz))
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())


def build(only=None):
    L = json.load(open(os.path.join(HERE, "voice_lines.json")))
    S = json.load(open(os.path.join(HERE, "speakers.json"))) if os.path.exists(os.path.join(HERE, "speakers.json")) else {}
    os.makedirs(OUT, exist_ok=True)
    done = 0
    for mid, v in L.items():
        if only and mid not in only:
            continue
        if not v.get("speech"):
            continue
        if not only and all(os.path.exists(os.path.join(OUT, k + ".wav")) for k in v["speech"]):
            continue
        for key, (x, hz) in speak_line(mid, v, speaker(mid, S)).items():
            write_wav(os.path.join(OUT, key + ".wav"), x, hz)
        done += 1
        if done % 50 == 0:
            print(f"  {done} lines", flush=True)
    n = len([f for f in os.listdir(OUT) if f.endswith(".wav")])
    print(f"voices: {done} lines spoken now; {n} sample wavs in {OUT}")


def read_wav(path):
    with wave.open(path) as w:
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768.0


if __name__ == "__main__":
    if sys.argv[1] == "speakers":
        speakers()
    else:
        build(sys.argv[2:] or None)
