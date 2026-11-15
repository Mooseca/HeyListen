"""Compile and run gpu/vk/exe_base.h's check (Linux): RX_VK_RB_PROF's call sites as offsets in the exe's link map.

    python -I -B tests/test_exe_base.py [--cxx g++]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_source():
    """vk_replay.cpp's RbScope still takes its sites' base from exe_base()"""
    src = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    for needle in ('#include "exe_base.h"', "static const uintptr_t base = exe_base();",
                   "CaptureStackBackTrace(1, 14, bt, nullptr);"):
        if needle not in src:
            raise SystemExit("vk_replay.cpp no longer has: " + needle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    if sys.platform == "win32":
        print("exe_base: the POSIX path only (skipped)")
        return
    with tempfile.TemporaryDirectory(prefix="exe-base-") as tmp:
        exe = Path(tmp) / "exe-base"
        subprocess.run([args.cxx, "-std=c++20", "-O1", "-D_GNU_SOURCE", "-Wall", "-Wextra", "-Werror", "-fPIE", "-pie",
                        str(ROOT / "tests/test_exe_base.cpp"), "-o", str(exe), "-ldl"], check=True)
        nm = subprocess.run(["nm", "-S", "--defined-only", str(exe)], check=True, capture_output=True, text=True).stdout
        for line in nm.splitlines():
            p = line.split()
            if len(p) == 4 and p[3] == "outer":
                subprocess.run([str(exe), p[0], p[1]], check=True)
                return
        raise SystemExit("nm: no outer in " + str(exe))


if __name__ == "__main__":
    main()
