#!/bin/sh
# Clean pipeline: generate assets -> build ROM -> web site.
#   games/sf64/build_clean.sh [--audio] [site dir]
# --audio also regenerates the samples (slow: ~15 min on 10 cores).
set -e
R="$(cd "$(dirname "$0")/../.." && pwd)"
W=D:/n64work/sf64
SITE=$W/site
AUDIO=0
for a in "$@"; do case $a in --audio) AUDIO=1;; *) SITE=$a;; esac; done
cd "$R"
python -m games.sf64.generate $W/pristine $W/dirty $W/clean 2>&1 | grep -v "Warning\|return fun"
[ $AUDIO = 1 ] && python -m games.sf64.audio gen $W/clean
[ -f $W/clean/bin/us/rev1/audio_table.bin ] || { echo "no clean audio yet: run with --audio"; exit 1; }
# flags/includes aren't make dependencies: drop objects whose inputs we regenerate
rm -rf $W/clean/build/src/assets $W/clean/build/bin $W/clean/build/src/engine/fox_wheels.o $W/clean/build/src/sys/sys_fault.o
sh games/sf64/build.sh $W/clean > $W/build_clean.log 2>&1 || { grep -m5 "rror" $W/build_clean.log; exit 1; }
ROM=$W/clean/build/starfox64.us.rev1.uncompressed.z64
ls -la $ROM | awk '{print "rom", $5, "bytes"}'
python ports/emu/make_site.py "$SITE" $ROM
