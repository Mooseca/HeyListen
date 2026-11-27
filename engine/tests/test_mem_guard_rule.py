# Copyright (C) 2026 Sacrappy
"""The memory guard's rule (gpu/vk/mem_guard_rule.h, tests/mem_guard_rule_test.cpp) and its wiring in vk_ram_guard.cpp, vk_draw.cpp and
vk_texture.cpp: on by default for an integrated AMD GPU on Windows (pools only), switches force it on or off.
python -I -B tests/test_mem_guard_rule.py [--cxx clang++]"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_wiring():
    g = (ROOT / "gpu/vk/vk_ram_guard.cpp").read_text(encoding="utf-8")
    for needle in ('#include "mem_guard_rule.h"', "mem_guard::decide(dev.props.vendorID", "VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU",
                   'getenv("RX_VK_MEM_GUARD")', 'getenv("RX_VK_MEM_GUARD_POOLS")', 'getenv("RX_VK_MEM_GUARD_BLOCKS")'):
        if needle not in g:
            raise SystemExit("vk_ram_guard.cpp no longer has: " + needle)
    d = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    for needle in ("ram_guard_pool_ok()", "ram_guard_draw_left_out()"):
        if needle not in d:
            raise SystemExit("vk_draw.cpp no longer has: " + needle)
    t = (ROOT / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    if "ram_guard_blocks()" not in t:
        raise SystemExit("vk_texture.cpp's budget cut no longer follows the guard's blocks part")
    sh = (ROOT / "gpu/vk/vk_shader.cpp").read_text(encoding="utf-8")
    if "mem_guard" in sh:
        raise SystemExit("vk_shader.cpp (the translator's stamp) reads the memory guard: every player's programs would be translated again")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="clang++")
    a = p.parse_args()
    check_wiring()
    with tempfile.TemporaryDirectory(prefix="mem-guard-") as temp:
        exe = Path(temp) / "mem_guard_rule_test.exe"
        subprocess.run([a.cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests/mem_guard_rule_test.cpp"), "-o", str(exe)], check=True)
        out = subprocess.run([str(exe)], check=True, timeout=60, capture_output=True, text=True).stdout
        assert " 0 failures" in out, out
    print("PASS:", out.strip())


if __name__ == "__main__":
    main()
