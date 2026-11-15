"""Compile and run the full FPS overlay's amdgpu sysfs reader (gpu/vk/amdgpu_stats.h, Linux; no game/GPU required).

    python -I -B tests/test_amdgpu_stats.py [--cxx g++]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_source():
    """vk_perf.cpp still reads amdgpu's files on Linux and NVML's Linux library, and vk_menu.cpp hands it the card's ids"""
    perf = (ROOT / "gpu/vk/vk_perf.cpp").read_text(encoding="utf-8")
    menu = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")
    for src, needle in ((perf, '#include "amdgpu_stats.h"'), (perf, 'amdgpu_stats::open("/sys"'),
                        (perf, "amd_sample(s);"), (perf, 'LoadLibraryA("libnvidia-ml.so.1")'),
                        (menu, "id.has_pci = true;"), (menu, "perf_sampling(true, pr.deviceName, (float)(vram >> 20), &id)")):
        if needle not in src:
            raise SystemExit("the source no longer has: " + needle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    if sys.platform == "win32":
        print("amdgpu_stats: sysfs is Linux only (skipped)")
        return
    with tempfile.TemporaryDirectory(prefix="amdgpu-stats-") as tmp:
        exe = Path(tmp) / "amdgpu-stats"
        subprocess.run([args.cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/test_amdgpu_stats.cpp"), "-o", str(exe)], check=True)
        tree = Path(tmp) / "sys"
        tree.mkdir()
        subprocess.run([str(exe), str(tree)], check=True)


if __name__ == "__main__":
    main()
