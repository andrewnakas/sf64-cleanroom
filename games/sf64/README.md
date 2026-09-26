# Star Fox 64 — clean room web build

Play: **https://andrewnakas.github.io/sf64-cleanroom/**

Star Fox 64 (US 1.1) built from the [sf64 decompilation](https://github.com/inspectredc/sf64) and played
in the browser with [N64Wasm](https://github.com/nbarkhina/N64Wasm) (MIT), with **every asset the decomp
normally extracts from a ROM regenerated**: textures, fonts, HUD, palettes, instrument/sound/voice samples.
No ROM is needed to play it.

Controls: arrow keys = stick · `D` = A (fire) · `S` = B (bomb) · `A` = Z · `Q`/`E` = L/R ·
`Enter` = Start · `J` = boost (C-left) · `K` = brake (C-down) · `I` = view (C-up) · gamepads work too (remap under the `` ` `` menu).

## What is kept, what is generated

The decomp is source code: game logic, and — through its Torch asset extractor — display lists, vertices,
animations, hitboxes, level scripts and the dialogue text as C. Everything else comes from the ROM. This
project reads the ROM **once, in a "dirty room" step** (`extract_spec.py`, `audio.py spec`), keeps only coarse
facts in `spec/`, and builds every asset from those facts plus our own drawings:

| Asset | Kept fact | Generated |
|---|---|---|
| Textures (1635) + palettes (311) | format, size, a 4×4 colour grid (16×16 for ≥128 px), a 2-bit alpha outline | colour from the grid, our own dither; palettes rebuilt by k-means over the pictures that share them |
| Text in textures (182: level and menu cards, results, options, VS banners) | the words (transcribed) | re-typeset with Rubik / M PLUS Rounded 1c (OFL) — `text_labels.json`, `labels.py` |
| Dialogue font (radio) | the 4-glyphs-per-texture bit-plane layout from the draw code | our glyphs (`radiofont.py`) |
| Menu fonts, HUD digits | character order from the decomp's tables | our glyphs (`glyphsets.py`) |
| Portraits (radio, VS, map video, ending cast) | — | drawn from our own character descriptions (`portraits.py`, `endings.py`, `prologue.py`) |
| Title logos, planets | — | our STARFOX wordmark and emblem (`logos.py`); planet surfaces from our own noise in the grid's colours (`planets.py`) |
| Crash-screen font, wheel scratch textures (in the decomp's C) | layout | our 5×7 font (`faultfont.py`); buffers zeroed |
| Samples (1132: sfx, voices, instruments) | length, loop points, a coarse spectral outline, a median pitch | resynthesised; our own VADPCM codebooks with the slot's predictor count (the audio heaps keep their layout) |
| Soundfont structure | key ranges, envelopes, tunings | books and loop states regenerated |
| Music | note sequences (kept) | played by the resynthesised instruments |
| Voices (724 radio lines) | the words (decomp text); which samples each line plays (read from the voice sequence by `voiceseq.py`); sample lengths and rates | spoken by Piper TTS in per-character voices (`voices.py`, placeholders); `practice.py` + `takes.py` let you record your own |

`taint_report.py` scans every generated texture (stored bytes and decoded RGBA), sample (ADPCM bytes, decoded
PCM, codebooks) and the C pixel arrays against the retail extraction for shared runs of 32 bytes or more.

Kept as code, as in any decomp build: IPL3 boot code, RSP microcode, libultra, the game code.

## Build (Windows, Git Bash)

Needs Python 3 (numpy, scipy, Pillow), GNU make, libdragon's mips64-elf binutils, a native IDO 5.3
(recompiled passes driven by `tools/idowin/ido_cc.py`), Torch (built with MSVC) and the decomp's Python
requirements.

```sh
# dirty room, once: needs your own ROM, never published
git clone https://github.com/inspectredc/sf64 dirty      # + submodules; clone with core.autocrlf=false
python -m games.sf64.tree_patches dirty                  # Windows build patches
cp baserom.us.rev1.z64 dirty/ && make -C dirty decompress extract && python -m games.sf64.tree_patches dirty --splat
torch code/header baserom.us.rev1.uncompressed.z64       # Torch asset C
python -m games.sf64.extract_spec dirty                  # -> spec/textures.json
python -m games.sf64.audio spec dirty                    # -> spec/audio.json, spec/bank_layout.bin

# clean room: from the spec only
python -m games.sf64.generate pristine dirty clean       # code/geometry from the decomp, assets generated
python -m games.sf64.audio gen clean
games/sf64/build.sh clean                                # ROM
python ports/emu/make_site.py site clean/build/starfox64.us.rev1.uncompressed.z64
python -m games.sf64.taint_report dirty clean            # dev check
```
