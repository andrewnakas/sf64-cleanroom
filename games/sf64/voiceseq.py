"""Radio message -> voice sample map, by interpreting the voice sequence (SEQ_ID_VOICE) like the decomp does.

Follows src/audio/audio_seqplayer.c (AudioSeq_SequencePlayerProcessSequence / ..ChannelProcessScript /
..SeqLayerProcessScript) command-for-command: argument sizes, s8 macro register (sp4B) and s8 IO ports,
call/loop/jump/branch, dyntable jumps/calls, C7/CF self-modifying writes, set-font via gSeqFontTable,
set-instrument, large/short notes, transposition, portamento sample choice, drums, and slow sample loads
(0x1n; completed after a few ticks with status 1, which moves the sample to RAM so DCTF samples may play).

For each msgId: fresh seq player, run until channel 15 is idle, then set channel-15 IO exactly like
Audio_UpdateVoice (port0=1, port4=msgId/1000, port5=(msgId%1000)/256, port6=(msgId%1000)%256) and tick until
the voice finishes (no layer active and channel 15 back to its wait loop) or a step limit. Every note that
would allocate a voice is recorded (font, inst, note, TunedSample slot, header, bank, sampleAddr, size).
Tempo is ignored (one tick per step): only control flow and note order matter here. No synthesis.

    python -m games.sf64.voiceseq [--write] [--trace MSGID]
"""
import json
import os
import re
import struct
import sys

import numpy as np

from . import audiofont as A
from . import voicemap as VM

HERE = os.path.dirname(os.path.abspath(__file__))
PRISTINE = "D:/n64work/sf64/pristine"
DIRTY = "D:/n64work/sf64/dirty"
SEQ_ID_VOICE = 1
CODEC_DCTF = 2
MEDIUM_RAM = 0


def s8(v):
    v &= 0xFF
    return v - 256 if v >= 128 else v


def seq_table(tree):
    src = open(f"{tree}/src/audio/audio_tables.c").read()
    body = src[src.index("gSeqTableInit"):]
    ent = re.findall(r"\{\s*(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+),\s*MEDIUM_CART", body)
    return [(int(a, 16), int(b, 16)) for a, b in ent]


def seq_font_table(tree):
    src = open(f"{tree}/src/audio/audio_tables.c").read()
    m = re.search(r"gSeqFontTableInit\[\d+\]\s*=\s*\{(.*?)\};", src, re.S)
    body = re.sub(r"//[^\n]*", "", m.group(1))
    out = []
    for tok in re.findall(r"AS_BYTES\(\s*(\d+)\s*\)|(0x[0-9A-Fa-f]+|\d+)", body):
        if tok[0]:
            v = int(tok[0])
            out += [v >> 8, v & 0xFF]
        else:
            out.append(int(tok[1], 0))
    return out


class Fonts:
    """Instrument / drum lookup over audio_bank.bin (AudioPlayback_GetInstrumentInner / GetDrum)."""

    def __init__(self, bank, fonts):
        self.b, self.f = bank, fonts
        self.ram = set()  # sample header offsets moved to RAM by slow loads

    def _tuned(self, fi, off):
        so, tun = struct.unpack_from(">If", self.b, self.f[fi]["off"] + off)
        if so == 0:
            return {"hdr": None, "tuning": tun}
        h = self.f[fi]["off"] + so
        w0 = A.u32(self.b, h)
        return {"hdr": h, "tuning": tun, "codec": w0 >> 28, "size": w0 & 0xFFFFFF, "addr": A.u32(self.b, h + 4),
                "bank": self.f[fi]["bank"]}

    def inst(self, fi, i):
        f = self.f[fi]
        if i >= f["ninst"]:
            return None
        io = A.u32(self.b, f["off"] + 4 + 4 * i)
        if not io:
            return None
        base = f["off"] + io
        return {"font": fi, "id": i, "lo": self.b[base + 1], "hi": self.b[base + 2],
                "ts": [self._tuned(fi, io + 8 + 8 * k) for k in range(3)]}

    def drum(self, fi, d):
        f = self.f[fi]
        if d >= f["ndrum"]:
            return None
        dl = A.u32(self.b, f["off"])
        if not dl:
            return None
        do = A.u32(self.b, f["off"] + dl + 4 * d)
        if not do:
            return None
        return {"font": fi, "id": d, "ts": self._tuned(fi, do + 4)}

    def font_sample(self, fi, inst_id):  # AudioLoad_GetFontSample
        if inst_id < 0x80:
            ins = self.inst(fi, inst_id)
            return ins["ts"][1] if ins else None
        dr = self.drum(fi, inst_id - 0x80)
        return dr["ts"] if dr else None


class State:
    def __init__(self, pc):
        self.pc, self.depth, self.stack, self.rem = pc, 0, [0] * 4, [0] * 4


class Layer:
    def __init__(self, ch):
        self.ch = ch
        self.enabled, self.finished, self.muted, self.cont = True, False, False, False
        self.st = State(0)
        self.gate, self.trans, self.delay, self.gateDelay = 0x80, 0, 0, 0
        self.inst, self.instOrWave = None, 0xFF
        self.pmode, self.ptarget = 0, 0
        self.sndd, self.lastDelay = 0, 0
        self.ts, self.note = None, False


class Channel:
    def __init__(self, pl, idx):
        self.pl, self.idx = pl, idx
        self.enabled, self.finished, self.stopScript, self.muted = False, False, False, False
        self.hasInstrument, self.trans, self.largeNotes = False, 0, False
        self.st = State(0)
        self.delay = 0
        self.io = [-1] * 8
        self.fontId = pl.defaultFont
        self.instOrWave, self.inst = 0, None
        self.layers = [None] * 4
        self.dyn = 0
        self.sp4B = 0  # uninitialised stack local in C; kept across calls here
        self.unkC4 = 0
        self.muteBehavior = pl.muteBehavior


class Player:
    def __init__(self, data, fonts, sft, seq_id, log):
        self.d = bytearray(data)
        self.F, self.sft, self.seqId, self.log = fonts, sft, seq_id, log
        off = (sft[2 * seq_id] << 8) | sft[2 * seq_id + 1]
        self.defaultFont = sft[off + sft[off]]  # last font loaded (AudioLoad_SyncInitSeqPlayerInternal)
        self.muteBehavior = 0xE0
        self.enabled, self.muted = True, False
        self.st = State(0)
        self.delay, self.trans, self.sp50, self.unk07 = 0, 0, 0, -1
        self.channels = [None] * 16
        self.none = Channel(self, -1)  # gSeqChannelNone
        self.slow = []  # [ticks_left, channel, port, font, inst]
        self.tick_no = 0

    # ---- readers
    def u8(self, st):
        v = self.d[st.pc]
        st.pc += 1
        return v

    def s16(self, st):
        v = (self.d[st.pc] << 8) | self.d[st.pc + 1]
        st.pc += 2
        return v  # used as u16 offsets

    def cu16(self, st):
        v = self.u8(st)
        if v & 0x80:
            v = ((v << 8) & 0x7F00) | self.u8(st)
        return v

    def ch(self, i):
        c = self.channels[i]
        return c if c is not None else self.none

    def font_of(self, idx):
        off = (self.sft[2 * self.seqId] << 8) | self.sft[2 * self.seqId + 1]
        return self.sft[(off + self.sft[off] - idx) & 0xFFFF]

    # ---- sequence player
    def tick(self):
        self.tick_no += 1
        for s in list(self.slow):  # AudioLoad_ProcessSlowLoads
            s[0] -= 1
            if s[0] <= 0:
                ts = self.F.font_sample(s[3], s[4])
                if ts and ts["hdr"] is not None:
                    self.F.ram.add(ts["hdr"])
                s[1].io[s[2]] = 1
                self.slow.remove(s)
        if not self.enabled:
            return
        if self.delay > 1:
            self.delay -= 1
        else:
            st = self.st
            while True:
                cmd = self.u8(st)
                if cmd == 0xFF:
                    if st.depth == 0:
                        self.disable()
                        break
                    st.depth -= 1
                    st.pc = st.stack[st.depth]
                if cmd == 0xFD:
                    self.delay = self.cu16(st)
                    break
                if cmd == 0xFE:
                    self.delay = 1
                    break
                if cmd >= 0xC0:
                    if cmd == 0xFF:
                        pass
                    elif cmd == 0xFC:
                        a = self.s16(st)
                        st.stack[st.depth] = st.pc
                        st.depth += 1
                        st.pc = a
                    elif cmd == 0xF8:
                        st.rem[st.depth] = self.u8(st)
                        st.stack[st.depth] = st.pc
                        st.depth += 1
                    elif cmd == 0xF7:
                        st.rem[st.depth - 1] = (st.rem[st.depth - 1] - 1) & 0xFF
                        if st.rem[st.depth - 1]:
                            st.pc = st.stack[st.depth - 1]
                        else:
                            st.depth -= 1
                    elif cmd in (0xF5, 0xF9, 0xFA, 0xFB):
                        a = self.s16(st)
                        v = self.sp50
                        if (cmd != 0xFA or v == 0) and (cmd != 0xF9 or v < 0) and (cmd != 0xF5 or v >= 0):
                            st.pc = a
                    elif cmd in (0xF2, 0xF3, 0xF4):
                        r = s8(self.u8(st))
                        v = self.sp50
                        if (cmd != 0xF3 or v == 0) and (cmd != 0xF2 or v < 0):
                            st.pc += r
                    elif cmd == 0xF1:
                        self.u8(st)
                    elif cmd == 0xF0:
                        pass
                    elif cmd == 0xDF:
                        self.trans = s8(self.u8(st))
                    elif cmd == 0xDE:
                        self.trans += s8(self.u8(st))
                    elif cmd in (0xDD, 0xDC, 0xD9, 0xD5, 0xD0):
                        self.u8(st)
                    elif cmd == 0xDA:
                        self.u8(st)
                        self.s16(st)
                    elif cmd == 0xDB:
                        self.u8(st)
                    elif cmd == 0xD7:
                        self.setup_channels(self.s16(st))
                    elif cmd == 0xD6:
                        self.disable_channels(self.s16(st))
                    elif cmd == 0xD4:
                        self.muted = True
                    elif cmd == 0xD3:
                        self.muteBehavior = self.u8(st)
                    elif cmd in (0xD1, 0xD2):
                        self.s16(st)
                    elif cmd == 0xCC:
                        self.sp50 = self.u8(st)
                    elif cmd == 0xC9:
                        self.sp50 &= self.u8(st)
                    elif cmd == 0xC8:
                        self.sp50 -= self.u8(st)
                    elif cmd == 0xC7:
                        c = self.u8(st)
                        a = self.s16(st)
                        self.d[a] = (self.sp50 + c) & 0xFF
                    else:
                        self.log.append(("seq-unk", hex(cmd), st.pc - 1))
                else:
                    hi, lo = cmd & 0xF0, cmd & 0xF
                    if hi == 0x00:
                        self.sp50 = int(self.ch(lo).finished)
                    elif hi == 0x50:
                        self.sp50 -= self.unk07
                    elif hi == 0x70:
                        self.unk07 = s8(self.sp50)
                    elif hi == 0x80:
                        self.sp50 = self.unk07
                    elif hi == 0x90:
                        self.channel_enable(lo, self.s16(st))
        for c in self.channels:
            if c is not None:
                self.channel_process(c)

    def disable(self):
        self.disable_channels(0xFFFF)
        self.enabled = False

    def setup_channels(self, bits):
        for i in range(16):
            if bits & 1:
                c = self.channels[i]
                if c is not None:
                    self.channel_disable(c)
                self.channels[i] = Channel(self, i)
            bits >>= 1

    def disable_channels(self, bits):
        for i in range(16):
            if bits & 1 and self.channels[i] is not None:
                self.channel_disable(self.channels[i])
                self.channels[i] = None
            bits >>= 1

    def channel_enable(self, i, pc):
        c = self.channels[i]
        if c is None:
            return
        c.st = State(pc)
        c.enabled, c.finished, c.delay = True, False, 0
        for k in range(4):
            if c.layers[k] is not None:
                self.layer_free(c, k)

    def channel_disable(self, c):
        for k in range(4):
            self.layer_free(c, k)
        c.enabled, c.finished = False, True

    def layer_free(self, c, k):
        if c.layers[k] is not None:
            c.layers[k].enabled, c.layers[k].finished, c.layers[k].note = False, True, False
            c.layers[k] = None

    def set_layer(self, c, k):
        old = c.layers[k]
        if old is not None:
            old.note = False
        c.layers[k] = Layer(c)
        return 0

    def get_instrument(self, c, iid):
        ins = self.F.inst(c.fontId, iid)
        if ins is None:
            return None, 0
        return ins, iid + 1

    def set_instrument(self, c, iid):
        if iid >= 0x80:
            c.instOrWave, c.inst = iid, None
        elif iid == 0x7F:
            c.instOrWave, c.inst = 0, None
        else:
            c.inst, c.instOrWave = self.get_instrument(c, iid)
            if c.instOrWave == 0:
                c.hasInstrument = False
                return
        c.hasInstrument = True

    # ---- channel
    def channel_process(self, c):
        if not c.enabled:
            return
        if c.stopScript:
            for L in list(c.layers):
                if L is not None:
                    self.layer_process(L)
            return
        if self.muted and (c.muteBehavior & 0x80):
            return
        if c.delay:
            c.delay -= 1
        if c.delay == 0:
            st = c.st
            while True:
                cmd = self.u8(st)
                if cmd > 0xC0:
                    if cmd in (0xD5, 0xD6):
                        pass
                    elif cmd == 0xFF:
                        if st.depth == 0:
                            self.channel_disable(c)
                            break
                        st.depth -= 1
                        st.pc = st.stack[st.depth]
                    elif cmd == 0xFE:
                        break
                    elif cmd == 0xFD:
                        c.delay = self.cu16(st)
                        break
                    elif cmd == 0xEA:
                        c.stopScript = True
                        break
                    elif cmd == 0xFC:
                        a = self.s16(st)
                        st.stack[st.depth] = st.pc
                        st.depth += 1
                        st.pc = a
                    elif cmd == 0xF8:
                        st.rem[st.depth] = self.u8(st)
                        st.stack[st.depth] = st.pc
                        st.depth += 1
                    elif cmd == 0xF7:
                        st.rem[st.depth - 1] = (st.rem[st.depth - 1] - 1) & 0xFF
                        if st.rem[st.depth - 1]:
                            st.pc = st.stack[st.depth - 1]
                        else:
                            st.depth -= 1
                    elif cmd == 0xF6:
                        st.depth -= 1
                    elif cmd in (0xF5, 0xF9, 0xFA, 0xFB):
                        a = self.s16(st)
                        v = c.sp4B
                        if (cmd == 0xFA and v != 0) or (cmd == 0xF9 and v >= 0) or (cmd == 0xF5 and v < 0):
                            continue
                        st.pc = a
                    elif cmd in (0xF2, 0xF3, 0xF4):
                        r = s8(self.u8(st))
                        v = c.sp4B
                        if (cmd == 0xF3 and v != 0) or (cmd == 0xF2 and v >= 0):
                            continue
                        st.pc += r
                    elif cmd == 0xF1:
                        self.u8(st)
                    elif cmd == 0xF0:
                        pass
                    elif cmd == 0xC2:
                        c.dyn = self.s16(st)
                    elif cmd == 0xC5:
                        if c.sp4B != -1:
                            p = (c.dyn + 2 * c.sp4B) & 0xFFFF
                            c.dyn = (self.d[p] << 8) + self.d[p + 1]
                    elif cmd in (0xEB, 0xC1):
                        if cmd == 0xEB:
                            f = self.font_of(self.u8(st))
                            c.fontId = f  # AudioHeap_SearchCaches assumed to hit
                        self.set_instrument(c, self.u8(st))
                    elif cmd == 0xC3:
                        c.largeNotes = False
                    elif cmd == 0xC4:
                        c.largeNotes = True
                    elif cmd in (0xDF, 0xE0, 0xD3, 0xEE, 0xDD, 0xDC, 0xD9, 0xD8, 0xD7, 0xE3, 0xD4, 0xD0, 0xD1,
                                 0xD2, 0xE5, 0xE6, 0xE9, 0xED):
                        self.u8(st)
                    elif cmd in (0xDE, 0xDA):
                        self.s16(st)
                    elif cmd in (0xE2, 0xE1):
                        self.u8(st), self.u8(st), self.u8(st)
                    elif cmd == 0xDB:
                        c.trans = s8(self.u8(st))
                    elif cmd == 0xC6:
                        c.fontId = self.font_of(self.u8(st))
                    elif cmd == 0xC7:
                        v = self.u8(st)
                        a = self.s16(st)
                        self.d[a] = ((c.sp4B & 0xFF) + v) & 0xFF
                    elif cmd in (0xC8, 0xC9, 0xCC):
                        v = s8(self.u8(st))
                        if cmd == 0xC8:
                            c.sp4B = s8(c.sp4B - v)
                        elif cmd == 0xCC:
                            c.sp4B = v
                        else:
                            c.sp4B = s8(c.sp4B & v)
                    elif cmd == 0xCD:
                        t = self.channels[self.u8(st)]
                        if t is not None:
                            self.channel_disable(t)
                    elif cmd == 0xCA:
                        c.muteBehavior = self.u8(st)
                    elif cmd == 0xCB:
                        a = self.s16(st)
                        c.sp4B = s8(self.d[(a + c.sp4B) & 0xFFFF])
                    elif cmd == 0xCE:
                        c.unkC4 = self.s16(st)
                    elif cmd == 0xCF:
                        a = self.s16(st)
                        self.d[a], self.d[a + 1] = (c.unkC4 >> 8) & 0xFF, c.unkC4 & 0xFF
                    elif cmd == 0xE4:
                        if c.sp4B != -1:
                            p = (c.dyn + 2 * c.sp4B) & 0xFFFF
                            st.stack[st.depth] = st.pc
                            st.depth += 1
                            st.pc = (self.d[p] << 8) + self.d[p + 1]
                    elif cmd == 0xE7:
                        a = self.s16(st)
                        c.muteBehavior = self.d[a]
                        c.trans = s8(self.d[a + 3])
                    elif cmd == 0xE8:
                        b = [self.u8(st) for _ in range(8)]
                        c.muteBehavior, c.trans = b[0], s8(b[3])
                    elif cmd == 0xEC:
                        pass
                    elif cmd == 0xEF:
                        self.s16(st)
                        self.u8(st)
                    else:
                        self.log.append(("ch-unk", hex(cmd), st.pc - 1))
                else:
                    hi, lo = cmd & 0xF0, cmd & 0xF
                    if hi == 0x00:
                        L = c.layers[lo]
                        c.sp4B = int(L.finished) if L is not None else -1
                    elif hi == 0x10:
                        c.io[lo] = -1
                        ts = self.F.font_sample(c.fontId, c.sp4B & 0xFF)
                        if ts is None or ts["hdr"] is None:
                            c.io[lo] = 0
                        elif ts["hdr"] in self.F.ram:
                            c.io[lo] = 2
                        else:
                            n = (ts["size"] + 0xFFF) // 0x1000 + 1
                            self.slow.append([n, c, lo, c.fontId, c.sp4B & 0xFF])
                            self.log.append(("slowload", c.fontId, c.sp4B & 0xFF, ts["addr"]))
                    elif hi == 0x70:
                        c.io[lo] = c.sp4B
                    elif hi == 0x80:
                        c.sp4B = c.io[lo]
                        if lo < 4:
                            c.io[lo] = -1
                    elif hi == 0x50:
                        c.sp4B = s8(c.sp4B - c.io[lo])
                    elif hi == 0x60:
                        c.delay = lo
                        break
                    elif hi == 0x90:
                        a = self.s16(st)
                        if self.set_layer(c, lo) == 0:
                            c.layers[lo].st.pc = a
                    elif hi == 0xA0:
                        self.layer_free(c, lo)
                    elif hi == 0xB0:
                        if c.sp4B != -1 and self.set_layer(c, lo) != -1:
                            p = (c.dyn + 2 * c.sp4B) & 0xFFFF
                            c.layers[lo].st.pc = (self.d[p] << 8) + self.d[p + 1]
                    elif hi == 0x20:
                        self.channel_enable(lo, self.s16(st))
                    elif hi == 0x30:
                        port = self.u8(st)
                        self.ch(lo).io[port] = c.sp4B
                    elif hi == 0x40:
                        port = self.u8(st)
                        c.sp4B = self.ch(lo).io[port]
                    else:
                        self.log.append(("ch-unk", hex(cmd), st.pc - 1))
        for L in list(c.layers):
            if L is not None:
                self.layer_process(L)

    # ---- layer
    def layer_process(self, L):
        if not L.enabled:
            return
        if L.delay > 1:
            L.delay -= 1
            if not L.muted and L.gateDelay >= L.delay:
                L.note = False
                L.muted = True
            return
        if not L.cont:
            L.note = False
        if L.pmode & 0x7F in (1, 2):
            L.pmode = 0
        c, st = L.ch, L.st
        while True:
            cmd = self.u8(st)
            if cmd <= 0xC0:
                break
            if cmd == 0xFF:
                if st.depth == 0:
                    L.note, L.enabled, L.finished = False, False, True
                    return
                st.depth -= 1
                st.pc = st.stack[st.depth]
            elif cmd == 0xFC:
                a = self.s16(st)
                st.stack[st.depth] = st.pc
                st.depth += 1
                st.pc = a
            elif cmd == 0xF8:
                st.rem[st.depth] = self.u8(st)
                st.stack[st.depth] = st.pc
                st.depth += 1
            elif cmd == 0xF7:
                st.rem[st.depth - 1] = (st.rem[st.depth - 1] - 1) & 0xFF
                if st.rem[st.depth - 1]:
                    st.pc = st.stack[st.depth - 1]
                else:
                    st.depth -= 1
            elif cmd == 0xFB:
                st.pc = self.s16(st)
            elif cmd == 0xF4:
                r = s8(self.u8(st))
                st.pc += r
            elif cmd in (0xC1, 0xCA, 0xC9, 0xCD):
                self.u8(st)
            elif cmd == 0xC2:
                L.trans = s8(self.u8(st))
            elif cmd in (0xC4, 0xC5):
                L.cont = cmd == 0xC4
                L.note = False
            elif cmd == 0xC3:
                L.sndd = self.cu16(st)
            elif cmd == 0xC6:
                v = self.u8(st)
                if v >= 0x7F:
                    if v == 0x7F:
                        L.instOrWave = 0
                    else:
                        L.instOrWave, L.inst = v, None
                else:
                    L.inst, L.instOrWave = self.get_instrument(c, v)
                    if L.instOrWave == 0:
                        L.instOrWave = 0xFF
            elif cmd == 0xC7:
                L.pmode = self.u8(st)
                v = (self.u8(st) + c.trans + L.trans + self.trans) & 0xFF
                L.ptarget = 0 if v >= 0x80 else v
                if L.pmode & 0x80:
                    self.u8(st)
                else:
                    self.cu16(st)
            elif cmd == 0xC8:
                L.pmode = 0
            elif cmd == 0xCB:
                self.s16(st)
                self.u8(st)
            elif cmd == 0xCC:
                pass
            elif cmd & 0xF0 in (0xD0, 0xE0):
                pass
            else:
                self.log.append(("layer-unk", hex(cmd), st.pc - 1))
        if cmd == 0xC0:
            L.delay = self.cu16(st)
            L.muted = True
        else:
            L.muted = False
            if c.largeNotes:
                k = cmd & 0xC0
                if k == 0x00:
                    d = self.cu16(st)
                    self.u8(st)
                    L.gate = self.u8(st)
                    L.lastDelay = d
                elif k == 0x40:
                    d = self.cu16(st)
                    self.u8(st)
                    L.gate = 0
                    L.lastDelay = d
                else:
                    d = L.lastDelay
                    self.u8(st)
                    L.gate = self.u8(st)
            else:
                k = cmd & 0xC0
                if k == 0x00:
                    d = self.cu16(st)
                    L.lastDelay = d
                elif k == 0x40:
                    d = L.sndd
                else:
                    d = L.lastDelay
            cmd -= cmd & 0xC0
            L.delay = d
            L.gateDelay = (L.gate * d) >> 8
            if (self.muted and (c.muteBehavior & 0x50)) or c.muted:
                L.muted = True
            else:
                iow = L.instOrWave
                if iow == 0xFF:
                    if not c.hasInstrument:
                        return
                    iow = c.instOrWave
                prev = L.ts
                slot = None
                if iow == 0:
                    n = (cmd + c.trans + L.trans) & 0xFF
                    dr = self.F.drum(c.fontId, n)
                    if dr is None:
                        L.muted = True
                        return
                    L.ts, ins, slot = dr["ts"], dr, "drum"
                else:
                    n = (cmd + self.trans + c.trans + L.trans) & 0xFF
                    ins = c.inst if L.instOrWave == 0xFF else L.inst
                    if n >= 0x80:
                        L.muted = True
                    elif ins is None:
                        L.ts = None
                    else:
                        sel = max(n, L.ptarget) if (L.pmode & 0x7F) else n
                        k = 0 if sel < ins["lo"] else (1 if sel <= ins["hi"] else 2)
                        L.ts, slot = ins["ts"][k], ("low", "normal", "high")[k]
                ts = L.ts
                if not L.muted and ts is not None and ts.get("codec") == CODEC_DCTF and ts["hdr"] not in self.F.ram:
                    L.muted = True
                if not L.muted:
                    new = (not L.cont) or (not L.note) or (prev is not ts)
                    if new:
                        L.note = True
                        self.notes.append({
                            "tick": self.tick_no, "ch": c.idx, "font": ins["font"] if ins else c.fontId,
                            "inst": ins["id"] if ins else None, "drum": slot == "drum", "note": n, "slot": slot,
                            "hdr": ts["hdr"] if ts else None, "bank": ts.get("bank") if ts else None,
                            "addr": ts.get("addr") if ts else None, "size": ts.get("size") if ts else None,
                            "codec": ts.get("codec") if ts else None, "tuning": round(ts["tuning"], 4) if ts else None,
                            # output rate: 32 kHz * gPitchFrequencies[note] (2^((n-39)/12)) * tuning
                            "rate_hz": round(32000 * 2 ** ((n - 39) / 12) * ts["tuning"]) if ts else None,
                            "secs": round(ts["size"] // 9 * 16 / (32000 * 2 ** ((n - 39) / 12) * ts["tuning"]), 3)
                            if ts and ts.get("size") and ts["tuning"] > 0 else None})
                return
        if L.muted and L.cont:
            L.note = False


def load():
    fonts, _ = A.font_table(PRISTINE)
    bank = open(f"{DIRTY}/bin/us/rev1/audio_bank.bin", "rb").read()
    seqbin = open(f"{DIRTY}/bin/us/rev1/audio_seq.bin", "rb").read()
    off, size = seq_table(PRISTINE)[SEQ_ID_VOICE]
    return Fonts(bank, fonts), seqbin[off:off + size], seq_font_table(PRISTINE)


def run_voice(F, data, sft, msg_id, max_ticks=20000, trace=False):
    F.ram = set()
    log = []
    p = Player(data, F, sft, SEQ_ID_VOICE, log)
    p.notes = []
    for _ in range(8):  # let the sequence set up channel 15 and reach its wait loop
        p.tick()
    idle_pc = p.channels[15].st.pc if p.channels[15] else None
    c15 = p.channels[15]
    bank, vid = msg_id // 1000, msg_id % 1000
    c15.io[0], c15.io[4], c15.io[5], c15.io[6] = 1, s8(bank), s8(vid // 256), s8(vid % 256)
    started = False
    ticks = 0
    for ticks in range(1, max_ticks + 1):
        p.tick()
        c15 = p.channels[15]
        if c15 is None or not c15.enabled:
            break
        busy = any(L is not None and L.enabled for c in p.channels if c for L in c.layers) or p.slow
        started = started or busy or bool(p.notes)
        if trace and ticks < 400:
            print(ticks, hex(c15.st.pc), c15.sp4B, c15.io, [(i, hex(L.st.pc)) for i, L in enumerate(c15.layers) if L])
        if started and not busy and c15.st.pc == idle_pc and c15.delay == 0:
            break
    return p.notes, log, ticks


def main(argv):
    F, data, sft = load()
    src = open(f"{DIRTY}/src/assets/ast_radio/ast_radio.c").read()
    look, text = VM.messages(src)
    if "--trace" in argv:
        mid = int(argv[argv.index("--trace") + 1])
        notes, log, t = run_voice(F, data, sft, mid, trace=True)
        print(text.get(mid), t, log[:20])
        for n in notes:
            print(n)
        return
    lines, unk = {}, set()
    for mid in look:
        notes, log, t = run_voice(F, data, sft, mid)
        unk.update(x[1] for x in log if x[0].endswith("unk"))
        keys = [f"{n['bank']}_{n['addr']:06x}" for n in notes if n["addr"] is not None]
        fonts = sorted({n["font"] for n in notes})
        lines[str(mid)] = {"text": text[mid], "samples": keys, "font": fonts[0] if len(fonts) == 1 else fonts,
                           "ticks": t, "notes": notes}
    spec = json.load(open(os.path.join(HERE, "spec", "audio.json")))["samples"]
    voice = {k for k in spec if k.startswith("2_")}
    # radio open/close effects: samples shared by many messages; the rest is speech
    cnt = {}
    for v in lines.values():
        for k in set(v["samples"]):
            cnt[k] = cnt.get(k, 0) + 1
    fx = {k for k, n in cnt.items() if n > 20}
    for v in lines.values():
        v["speech"] = [k for k in v["samples"] if k not in fx]
    used = set(cnt)
    none = [m for m, v in lines.items() if not v["speech"]]
    print(f"messages: {len(lines)}  with speech: {len(lines) - len(none)}  no speech: {len(none)} "
          f"({none[:3]}..{none[-2:]})  radio fx samples: {sorted(fx)}")
    print(f"bank-2 samples in spec: {len(voice)}  referenced: {len(used & voice)}  never referenced: "
          f"{sorted(voice - used)}")
    other = used - voice
    print(f"referenced outside bank 2: {len(other)} (banks {sorted({k[0] for k in other})}), "
          f"missing from spec: {len(other - set(spec))}")
    nsp = [len(v["speech"]) for v in lines.values() if v["speech"]]
    print(f"speech samples per message: 1:{nsp.count(1)} 2:{nsp.count(2)} 3+:{sum(n > 2 for n in nsp)}  "
          f"shared speech samples (in >1 msg): {sum(1 for k, n in cnt.items() if n > 1 and k not in fx)}  "
          f"unknown cmds: {sorted(unk)}")
    L, T = [], []
    for v in lines.values():
        if v["speech"] and v["text"]:
            L.append(sum(x["secs"] or 0 for x in v["notes"] if x["addr"] is not None
                         and f"{x['bank']}_{x['addr']:06x}" not in fx))
            T.append(len(v["text"]))
    if len(L) > 2:
        L, T = np.array(L), np.array(T)
        print(f"corr(speech secs [size/9*16 / rate_hz], text chars) r={np.corrcoef(L, T)[0, 1]:.3f} over {len(L)} msgs;"
              f" median secs/char={np.median(L / T):.3f}")
    for m in list(lines)[max(1, len(lines) // 5)::max(1, len(lines) // 5)][:5]:
        v = lines[m]
        print(f"{m}: {v['text'][:44]!r} -> {v['speech']} sizes {[n['size'] for n in v['notes']][2:]} "
              f"secs {[n['secs'] for n in v['notes']][2:]}")
    if "--write" in argv:
        json.dump(lines, open(os.path.join(HERE, "voice_lines.json"), "w"), indent=1)
        print("wrote voice_lines.json")


if __name__ == "__main__":
    main(sys.argv[1:])
