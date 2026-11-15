"""Compile and run the full FPS overlay's CPU temperature reader (gpu/vk/cpu_temp.h, Linux hwmon; no game/GPU required).

    python -I -B tests/test_cpu_temp.py [--cxx g++] [--real]

--real: also reads this machine's /sys and prints what it found (fails when no k10temp or coretemp is there).
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_source():
    """vk_perf.cpp still finds the file once on Linux and reads it each sample"""
    perf = (ROOT / "gpu/vk/vk_perf.cpp").read_text(encoding="utf-8")
    for needle in ('#include "cpu_temp.h"', 'cpu_temp::open("/sys")', "s.cpu_temp_c = cpu_temp::sample(cpu_temp_files);"):
        if needle not in perf:
            raise SystemExit("vk_perf.cpp no longer has: " + needle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--real", action="store_true")
    args = parser.parse_args()
    check_source()
    if sys.platform == "win32":
        print("cpu_temp: hwmon is Linux only (skipped)")
        return
    with tempfile.TemporaryDirectory(prefix="cpu-temp-") as tmp:
        exe = Path(tmp) / "cpu-temp"
        subprocess.run([args.cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/test_cpu_temp.cpp"), "-o", str(exe)], check=True)
        tree = Path(tmp) / "sys"
        tree.mkdir()
        subprocess.run([str(exe), str(tree)], check=True)
        if args.real:
            subprocess.run([str(exe), "--real"], check=True)


if __name__ == "__main__":
    main()
