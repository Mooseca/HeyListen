# Copyright (C) 2026 Sacrappy

"""An allowance AMD's driver gives as the count itself is taken as past it (gpu/vk/vram_allowance.h, vk_vma.cpp vram_usage);
Longshot #1091. And, past the allowance, no floor under the textures' budget (floor_within, Longshot 8941d01b4, #2082: the 1 GB floor of
texture_frame's TICK-023 rule). Compiles and runs the rules; no game/GPU."""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    src = (ROOT / "gpu/vk/vk_vma.cpp").read_text(encoding="utf-8")
    for needle in ('#include "vram_allowance.h"', "vram_allowance::past_allowance(u, t)", "RX_VK_ALLOWED_AT_COUNT"):
        if needle not in src:
            raise SystemExit("vk_vma.cpp no longer has: " + needle)
    tex = (ROOT / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    for needle in ('#include "vram_allowance.h"',
                   "std::max<uint64_t>(target > rest ? target - rest : 0, vram_allowance::target_floor(used, allowed))"):
        if needle not in tex:
            raise SystemExit("vk_texture.cpp no longer has: " + needle)
    if "target > rest ? target - rest : 0, 1024ull << 20)" in tex:
        raise SystemExit("vk_texture.cpp: the budget's 1 GB floor holds past the allowance again (vram_allowance::target_floor)")
    with tempfile.TemporaryDirectory(prefix="vram-allowance-") as tmp:
        exe = Path(tmp) / "vram-allowance"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests/test_vram_allowance.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
