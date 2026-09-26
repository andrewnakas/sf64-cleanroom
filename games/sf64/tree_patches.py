"""Build-tool patches so the sf64 decomp builds natively on Windows (Git Bash + make).

    python -m games.sf64.tree_patches <tree>

Each patch: (file, old, new). Idempotent (skips when `new` is already present).
Toolchain: IDO 5.3 static recomp (windows), libdragon mips64-elf binutils, Torch built with MSVC.
"""
import os
import sys

PATCHES = [
    # Native Windows: the recomp has a windows build; everything else runs under Git Bash.
    ("Makefile",
     "ifeq ($(OS),Windows_NT)\n$(error Native Windows is currently unsupported for building this repository, use WSL instead c:)\n",
     "ifeq ($(OS),Windows_NT)\n    DETECTED_OS := windows\n"),
    ("tools/Makefile",
     "ifeq ($(OS),Windows_NT)\n\t$(error Native Windows is currently unsupported for building this repository, use WSL instead c:)\n",
     "ifeq ($(OS),Windows_NT)\n\tDETECTED_OS := windows\n\tMIO0_FLAGS := --gc-sections\n"),
    # Torch builds with MSVC into cmake-build-release/Release/
    ("Makefile", "TORCH           := $(TOOLS)/Torch/cmake-build-release/torch\n",
     "TORCH           := $(TOOLS)/Torch/cmake-build-release/Release/torch.exe\n"),
    ("Makefile", "MIO0\t\t\t:= $(TOOLS)/mio0\n", "MIO0\t\t\t:= $(TOOLS)/mio0.exe\n"),
    # CreateProcess can't run "tools/mio0.exe" (forward slash, relative) or `rm`
    ("tools/comptool.py", "    run([mio0, '-d', comp_path, decomp_path])",
     "    run([os.path.abspath(mio0), '-d', comp_path, decomp_path])"),
    ("tools/comptool.py", "    run([mio0, '-c', decomp_path, comp_path])",
     "    run([os.path.abspath(mio0), '-c', decomp_path, comp_path])"),
    # IDO's cfe reads backslashes in paths (#line markers, -I) as string escapes: use forward slashes
    ("tools/asm-processor/build.py", "asmproc_flags += opt_flags + [str(in_file)]",
     "asmproc_flags += opt_flags + [in_file.as_posix()]"),
    ("tools/asm-processor/build.py", '+ ["-I", str(in_dir), "-o", str(out_file), str(preprocessed_path)]',
     '+ ["-I", in_dir.as_posix(), "-o", out_file.as_posix(), preprocessed_path.as_posix()]'),
    ("tools/asm-processor/build.py", "            str(out_file),\n", "            out_file.as_posix(),\n"),
    ("tools/asm-processor/build.py", "            str(asm_prelude_path),\n", "            asm_prelude_path.as_posix(),\n"),
    # CreateProcess needs the .exe of the IDO recomp wrapper
    ("tools/asm-processor/build.py", "    try:\n        subprocess.check_call(compile_cmdline)",
     "    import shutil as _sh\n"
     "    compile_cmdline[0] = _sh.which(compile_cmdline[0]) or compile_cmdline[0]\n"
     "    try:\n        subprocess.check_call(compile_cmdline)"),
]


def fix_splat_paths(tree):
    """splat on Windows writes backslash paths into .incbin lines and the linker script."""
    n = 0
    for d in ("asm", "linker_scripts"):
        for root, _, files in os.walk(os.path.join(tree, d)):
            for f in files:
                if not f.endswith((".s", ".ld", ".d")):
                    continue
                p = os.path.join(root, f)
                s = open(p, newline="").read()
                if "\\" in s:
                    open(p, "w", newline="").write(s.replace("\\", "/"))
                    n += 1
    print(f"splat paths: {n} files normalised")


def apply(tree):
    n = 0
    for f, old, new in PATCHES:
        p = os.path.join(tree, f)
        s = open(p, newline="").read()
        if new in s:
            continue
        assert old in s, f"patch target missing in {f}: {old[:60]!r}"
        open(p, "w", newline="").write(s.replace(old, new, 1))
        n += 1
    print(f"tree_patches: {n} applied, {len(PATCHES) - n} already present")


if __name__ == "__main__":
    if "--splat" in sys.argv:
        fix_splat_paths(sys.argv[1])
    else:
        apply(sys.argv[1])
