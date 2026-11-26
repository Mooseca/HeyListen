# Copyright (C) 2026 Sacrappy
"""The EQUAL depth margin's default (gpu/vk/equal_depth_rule.h), compiled and run on the GPUs players have; no game, no GPU.

Intel's Windows driver gets a 64-unit margin on colour passes that test EQUAL after a depth prepass (the ground's holes, issue 17,
Arc B390), and the margin's LESS_OR_EQUAL passes every fragment in front of the prepass: where an alpha-tested prepass cut a leaf
away, the colour pass draws the whole quad, and the foliage comes out as solid blocks. On discrete Battlemage (0xE2xx: Arc B570,
B580) and on Lunar Lake (0x64xx: Arc 140V) with Intel's Windows driver it is therefore off by default. Other Intel GPUs keep 64
(Alchemist 0x56xx, Meteor Lake and Arc 155H, Panther Lake 0xB0xx, UHD), Mesa's Intel driver too as in this tree before, and every
other vendor has 0. RX_VK_EQ_BIAS decides over the default (read in vk_draw.cpp; test_equal_depth_margin.py).

Ported from Longshot's tests (test_device_policy.py rule edges of 03a6e8d0e by tiktiki, #1801, and 641030ed9 by twisted89, #2299).
python -I -B tests/test_equal_depth_rule.py [--cxx g++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROGRAM = r'''
#include <cstdio>
#include "equal_depth_rule.h"
using equal_depth_rule::default_margin;
static int failures = 0;
static void expect(const char* what, float got, float want) {
    if (got != want) { std::fprintf(stderr, "%s: %g, expected %g\n", what, got, want); failures++; }
}
int main() {
    const uint32_t intel = 0x8086, amd = 0x1002, nvidia = 0x10de;
    // Intel's Windows driver
    expect("Arc B570 (0xE20C)", default_margin(intel, 0xE20C, true), 0);
    expect("Arc B580 (0xE20B)", default_margin(intel, 0xE20B, true), 0);
    expect("Arc 140V, Lunar Lake (0x64A0)", default_margin(intel, 0x64A0, true), 0);
    expect("Arc 130V, Lunar Lake (0x6420)", default_margin(intel, 0x6420, true), 0);
    expect("Arc A750 (0x56A1)", default_margin(intel, 0x56A1, true), 64);
    expect("Iris Xe (0x9A78)", default_margin(intel, 0x9A78, true), 64);
    expect("Arc 155H, Meteor Lake (0x7D55)", default_margin(intel, 0x7D55, true), 64);
    expect("Arc B390, Panther Lake (0xB080)", default_margin(intel, 0xB080, true), 64);
    expect("the neighbours of 0xE2xx and 0x64xx", default_margin(intel, 0xE1FF, true) + default_margin(intel, 0xE300, true) +
                                                   default_margin(intel, 0x63FF, true) + default_margin(intel, 0x6500, true), 256);
    // Mesa's Intel driver: as before this rule (64 on every Intel GPU), whatever the device
    expect("Mesa ANV on Battlemage", default_margin(intel, 0xE20C, false), 64);
    expect("Mesa ANV on Iris Xe", default_margin(intel, 0x9A49, false), 64);
    // other vendors
    expect("AMD", default_margin(amd, 0x744C, false), 0);
    expect("AMD, a device number that looks like Battlemage", default_margin(amd, 0xE20C, true), 0);
    expect("NVIDIA", default_margin(nvidia, 0x2204, false), 0);
    if (!failures) std::puts("equal depth margin rule ok");
    return failures ? 1 : 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    header = (ROOT / "gpu/vk/equal_depth_rule.h").read_text(encoding="utf-8")
    for needle in ("(device_id & 0xFF00u) == 0xE200u", "(device_id & 0xFF00u) == 0x6400u"):
        if needle not in header:
            raise SystemExit("equal_depth_rule.h lacks " + needle)
    with tempfile.TemporaryDirectory(prefix="equal-depth-rule-") as tmp:
        src = Path(tmp) / "rule.cpp"
        exe = Path(tmp) / "rule.exe"
        src.write_text(PROGRAM, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "gpu/vk"), str(src), "-o", str(exe)],
                       check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
