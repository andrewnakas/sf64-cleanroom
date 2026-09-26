# Star Fox 64 clean room: status

_Last update: 2026-09-26 ~08:00_

**Live: https://andrewnakas.github.io/sf64-cleanroom/** (repo https://github.com/andrewnakas/sf64-cleanroom)
Taint: 0 failing (1946 textures/TLUTs as bytes + decoded RGBA, 1132 samples as ADPCM + PCM + codebooks, C pixel arrays).

## For the morning
- **Play it** in Chrome/Edge: arrows = stick, D = A (fire), S = B (bomb), A = Z, Q/E = L/R (tilt/roll), Enter = Start,
  J = boost (C-left), K = brake (C-down), I = view (C-up). Gamepads work (remap under the `` ` `` menu).
  Verified headless: intro -> title -> main menu -> prologue -> map -> Corneria card -> Corneria gameplay with HUD and radio.
- **Look at**: portraits (our own drawn characters, closed/open mouth), the title (our STARFOX wordmark), menus and level cards
  (re-typeset), the radio font, HUD digits, General Pepper's map video panel, voices (TTS placeholders).
- **Record voices** (optional): practice pack at `D:/n64work/sf64/practice_pack/` (724 lines, 15 characters, personal use only:
  the reference clips come from your ROM). Play `practice_<WHO>_call_and_response.wav`, speak after each beep, record the whole
  track (any format), then:
  `python -m games.sf64.takes cut <recording> <WHO> D:/n64work/sf64/practice_pack` for each character,
  `python -m games.sf64.takes place`, `games/sf64/build_clean.sh --audio`, taint, `games/sf64/publish.sh`.
  SCRIPT.txt lists every line with its message id and length. Speakers come from the decomp's `Radio_PlayMessage(msg, RCID_*)`
  calls (440 lines); the other lines are guessed (title = ROB64, map = General Pepper, else Fox) — check FOX's list.

## Decisions (log)
- 2026-09-25 22:40 Decomp: upstream `sonicdcer/sf64` is gone from GitHub (404). Using the most recently pushed fork
  `inspectredc/sf64` @ 3c5d492 ("REACHES 100%", 2026-07-28), US rev1 matching. Cloned LF-only to `D:/n64work/sf64/pristine`.
  Submodules pinned: Torch 6ca699d, splat 441af8f, asm-processor fed1e3d.
- ROM: `Star Fox 64 (USA) (Rev 1).z64`, md5 741a94ee… = decomp's `starfox64.us.rev1.md5`. Decompressed md5 matches too.
- **Web route = 3 (clean N64 ROM + N64Wasm).** Why: no SF64 PC port with a web target (Starship = libultraship/C++,
  desktop only); the decomp matches 100% and builds a ROM. Emulator: N64Wasm (MIT, prebuilt ParaLLEl/mupen64plus core,
  keyboard + gamepad + audio), same as the SSB64 sibling session. 30 game fps (full speed) in headless Edge when the machine is idle.
  Its CDN scripts (jQuery, bootstrap, rivets, toastr, popper, FileSaver, nipplejs; all MIT) are vendored into the site: a slow CDN
  once left `$` undefined and the page dead.
- Toolchain on Windows (no WSL): libdragon mips64-elf binutils (`~/.local/mips64/bin`), Torch built with MSVC 2022,
  Python venv `D:/n64work/sf64/venv` (decomp requirements), `PYTHONUTF8=1` for splat.
  **IDO**: the ido-static-recomp Windows cc (v1.0 and v1.2) fails on any source > 32 KB ("cfe: 4120 Unexpected End-of-file");
  used the PW64 native IDO passes (`C:/Users/andre/n64work/idowin/bin`) through `tools/idowin/ido_cc.py` (added `-verbose`,
  `-EB`, `-use_readwrite_const`). Build-tool patches: `games/sf64/tree_patches.py` (+ `--splat` fixes backslash paths).
- Dirty round-trip: build == retail uncompressed md5 (23e24fb0…). The uncompressed ROM is what we ship (no MIO0 step).
- Kept as code (not art), as in the sibling sessions: IPL3 boot code, RSP microcode (F3DEX, aspMain, rspboot), libultra,
  Torch geometry/animation/script C, dialogue text, note sequences (audio_seq.bin), soundfont structure (books and loop states
  regenerated).
- Retail pixel data inside the decomp's own C: `fox_wheels.c` (scratch textures zeroed, TLUT from our palette) and the
  crash-screen font in `sys_fault.c` (our own 5x7 font) — `code_art.py`.
- Texture text alpha outlines are kept facts (user scope), but every transcribed text texture is re-typeset anyway
  (`text_labels.json`, 161 labels, Rubik / M PLUS Rounded 1c OFL fonts).
- Radio font: 4 glyphs per 16x13 CI4 texture as bit planes; code palettes pick the bit (`radiofont.py`).
- Menu fonts: character order from `sLargeChars`/`sSmallChars` tables (symbol names lie: large 'O' is `aSmallText_O`).
- Tiled textures (G_TX_WRAP in the kept display lists, 232) use periodic grid upsampling: no seams in skies/ground.
- Audio: SF64 fonts have no sfx list (instruments start at +4). 1132 unique samples, all ADPCM; books keep the slot's predictor
  count (2 or 4) so the font sizes and audio heap layout are unchanged. Unreferenced bank bytes are zero.
- Voices: `voiceseq.py` interprets the voice sequence (SEQ_ID_VOICE) exactly like audio_seqplayer.c: 724/779 messages map to
  their speech samples (a line may span 1-3 samples; voice samples play at 6-15 kHz). Piper TTS per character (`voices.py`),
  split across the samples at quiet points; Whisper reads them back correctly on spot checks.
- Taint: dither added to grid textures (first scan: 27 short runs of 35–49 B in smooth gradients).

- 2026-09-26 ~06:40 First-visit bug fixed: N64Wasm's `LoadSram` could open the save DB before its object store existed
  and never resolve, so the ROM downloaded but the emulator didn't start (seen as "Uncaught (in promise)"). `make_site.py`
  now replaces it with a version that creates the store on upgrade and always resolves: 4/4 fresh-profile loads start.

- 2026-09-26 ~08:00 Published: menacing Andross portrait, radio-static portraits, speakers from code tables (title lines
  are General Pepper; map briefings are Pepper then Fox's reply; 473 lines now have a known speaker), 19 lines re-voiced,
  practice pack rebuilt (FOX 317 lines still include guesses). Pitch doesn't separate the characters, so no classifier.

- Not verified in-game: VS mode screens (the headless key events don't move the menu cursor); their banners/labels were
  checked as rendered images only. Please try VS mode by hand.

- 2026-09-26 Sound + touch controls (user report: "no sounds"):
  - The page autostarts the ROM without a user gesture, so browsers create N64Wasm's AudioContext suspended and it was
    never resumed: silence. Now resumed on the first tap/click/key, with a "Tap for sound" button until audio runs.
    The audio itself was fine: mix RMS/peaks over the first minute match the retail build (both clip at the same moments).
  - New touch pad (`ports/emu/touch.js`) on phones/tablets (or `?touch=1`): floating analog stick, A fire, B bomb, Z/R tilt
    (with L/R actually sent: N64Wasm's own mobile UI hard-codes them off, so no barrel rolls), C-left boost, C-down brake,
    C-up view, C-right, Start, Fullscreen (locks landscape where allowed). Portrait: 4:3 screen on top, controls below;
    landscape: full-height screen with translucent controls at the sides. Checked at 390x844 and 844x390: Start skips the
    intro and opens the title, A opens the menu (scripted with `?touchscript=`).
  - Keyboard help corrected: boost is C-left (J) and brake C-down (K), from the decomp's gBoostButton/gBrakeButton.

## Next
- Backdrops/planets/ending pictures: more of our own drawing where grids read as mush.
- A retail-vs-clean screenshot pass of every level (dev only) to find what reads worst.
