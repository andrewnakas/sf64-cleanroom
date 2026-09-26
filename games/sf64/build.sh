#!/bin/sh
# Build the sf64 decomp ROM natively on Windows (Git Bash).
#   games/sf64/build.sh <tree> [make args...]
# Needs: ~/bin shims (tools/setup_winbin.sh), libdragon mips64-elf binutils, the PW64 native IDO
# passes (IDO_BIN) driven by tools/idowin/ido_cc.py, the decomp venv (D:/n64work/sf64/venv).
set -e
HERE="$(cd "$(dirname "$0")/../.." && pwd -W 2>/dev/null || pwd)"
T="$1"; shift
export PATH="$HOME/bin:$HOME/.local/mips64/bin:$PATH" PYTHONUTF8=1
export IDO_BIN="${IDO_BIN:-C:/Users/andre/n64work/idowin/bin}"
PY=C:/Users/andre/AppData/Local/Programs/Python/Python312/python.exe
cd "$T"
make uncompressed -j6 RUN_CC_CHECK=0 COMPARE=0 PYTHON=D:/n64work/sf64/venv/Scripts/python.exe \
  IDO="$PY $HERE/tools/idowin/ido_cc.py" "$@"
