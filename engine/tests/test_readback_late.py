"""RX_VK_READBACK_LATE (gpu/vk/readback_late.h): the rules that name the CPU reads of GPU results read without their wait.

The header is compiled with a small program that parses rule lists and asks which ranges are late:
- no rule, "0" and an empty list name nothing; "newest" names the ranges whose writer is the newest submission handed out;
- a hex size names every range of exactly that size; "-<hex size>" never, whatever the other rules say.
And, by the text, that invalidate() asks the rules only for a range that is pending, after the write-back's value is known, and
that the wait is skipped for a late range only (an unnamed range goes through wait_recorded / wait_value as before).

python -I -B tests/test_readback_late.py --cxx <compiler>
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CPP = r'''
#include "readback_late.h"
#include <cstdio>
static int fails;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
int main() {
    using namespace readback_late;
    CHECK(!parse(nullptr).any());
    CHECK(!parse("").any());
    CHECK(!parse("0").any());
    const Rules n = parse("newest");
    CHECK(n.any() && wanted(n, 0x40, true) && !wanted(n, 0x40, false));
    const Rules s = parse("3980,2000");
    CHECK(wanted(s, 0x3980, false) && wanted(s, 0x2000, true) && !wanted(s, 0x40, true) && !wanted(s, 0x1040, false));
    const Rules m = parse("newest,-1040,-c0");
    CHECK(wanted(m, 0x40, true) && !wanted(m, 0x1040, true) && !wanted(m, 0xc0, true) && !wanted(m, 0x40, false));
    const Rules b = parse("2000,-2000");
    CHECK(!wanted(b, 0x2000, false) && !wanted(b, 0x2000, true));
    CHECK(!parse("-1040").any());
    if (!fails) std::printf("PASS the rules\n");
    return fails;
}
'''


def function(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / "t.cpp", Path(tmp) / "t.exe"
        cpp.write_text(CPP)
        subprocess.run([args.cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "gpu/vk"), str(cpp), "-o", str(exe)],
                       check=True)
        subprocess.run([str(exe)], check=True)
    rp = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    inv = function(rp, "void invalidate(uint64_t gpu, uint64_t size) {")
    assert 'getenv("RX_VK_READBACK_LATE")' in function(rp, "bool readback_late_wanted(uint64_t size, bool newest) {"), \
        "the switch is not read from RX_VK_READBACK_LATE"
    i_val = inv.index("memory_writeback_value(host->gpu_guest(gpu), size, nullptr);")
    i_late = inv.index("readback_late_wanted(size, v >= f0)")
    i_wait = inv.index("if (pend && !late) {")
    assert i_val < i_late < i_wait, "the rules are asked before the write-back's value is known, or after the wait"
    assert "const bool pend = v > completed();" in inv and "pend && readback_late_wanted" in inv, "a range that is not pending is asked"
    print("PASS the wiring")


if __name__ == "__main__":
    main()
