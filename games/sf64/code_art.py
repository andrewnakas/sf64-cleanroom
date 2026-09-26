"""CLEAN ROOM: pixel data that the decomp keeps inside its C source (not extracted by Torch).

  src/engine/fox_wheels.c   two scratch textures the wheel code rotates into every frame
                            (initial contents zeroed) and a copy of the Macbeth train-wheel TLUT
                            (replaced by our generated D_MA_6023788 palette)
  src/sys/sys_fault.c       the crash-screen 5x7 font bitmap (redrawn from our own glyph table)
"""
import os
import re

from . import faultfont


def _replace_array(src, name, values, per=12, width=4):
    m = re.search(r"(\b%s\[[^\]]*\]\s*=\s*\{)(.*?)(\n\};)" % re.escape(name), src, re.S)
    assert m, name
    body = "\n" + "\n".join("    " + " ".join(f"0x{v:0{width}X}," for v in values[i:i + per])
                            for i in range(0, len(values), per))
    return src[:m.start(2)] + body + src[m.end(2):]


def _count(src, name):
    m = re.search(r"\b%s\[[^\]]*\]\s*=\s*\{(.*?)\n\};" % re.escape(name), src, re.S)
    return len(re.findall(r"0x[0-9A-Fa-f]+", m.group(1)))


def apply(out):
    p = os.path.join(out, "src/engine/fox_wheels.c")
    s = open(p).read()
    s = _replace_array(s, "D_Tex_800DACB8", [0] * _count(s, "D_Tex_800DACB8"), 8, 4)
    s = _replace_array(s, "D_Tex_800DB4B8", [0] * _count(s, "D_Tex_800DB4B8"), 16, 2)
    tl = open(os.path.join(out, "src/assets/ast_macbeth/D_MA_6023788.tlut.inc.c")).read()
    vals = [int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", tl)]
    n = _count(s, "D_TLUT_800DB4B8")
    s = _replace_array(s, "D_TLUT_800DB4B8", (vals + [0] * n)[:n], 8, 4)
    open(p, "w", newline="\n").write(s)
    p = os.path.join(out, "src/sys/sys_fault.c")
    s = open(p).read()
    s = _replace_array(s, "sFaultCharPixelFlags", faultfont.pixel_flags(), 8, 8)
    open(p, "w", newline="\n").write(s)
    print("code art: fox_wheels (2 buffers zeroed, TLUT from our palette), sys_fault font redrawn")
