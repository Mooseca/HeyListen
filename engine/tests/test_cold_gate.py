# Copyright (C) 2026 Sacrappy

"""STUT3: the cold-pages pass takes pages out of the working set only while the PC is short of RAM (host/hl_mem_coldgate.h).

The header is compiled with a small program: the pass is off while the free RAM is at the start line or over it, starts under
it, stays on until the free RAM is back at the stop line (the hysteresis: no change between the two lines), a stop line under the
start line counts as the start line, and a start line of 0 keeps the pass on whatever the free RAM (as before). Then, by the
text of host/hl_mem.c: the switches are read with their defaults, the pass looks at the free RAM before the pools' and the
heaps' parts, both are skipped when the gate is off, and each change of state is logged with the free RAM.

python -I -B tests/test_cold_pool_gate.py --cxx <compiler>
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CPP = r'''
#include "hl_mem_coldgate.h"
#include <cstdio>
static int fails;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
int main() {
    const uint64_t lo = HL_COLDGATE_LOW_DEFAULT_MB, hi = HL_COLDGATE_HIGH_DEFAULT_MB;
    CHECK(lo == 4096 && hi == 6144);
    // off with RAM to spare, at the start line too
    CHECK(hl_coldgate_next(0, 20000, lo, hi) == 0);
    CHECK(hl_coldgate_next(0, 4096, lo, hi) == 0);
    // under the start line: on
    CHECK(hl_coldgate_next(0, 4095, lo, hi) == 1);
    CHECK(hl_coldgate_next(0, 0, lo, hi) == 1);
    // the hysteresis: on stays on between the lines, off stays off between them
    CHECK(hl_coldgate_next(1, 4096, lo, hi) == 1);
    CHECK(hl_coldgate_next(1, 6143, lo, hi) == 1);
    CHECK(hl_coldgate_next(0, 5000, lo, hi) == 0);
    // back at the stop line: off
    CHECK(hl_coldgate_next(1, 6144, lo, hi) == 0);
    CHECK(hl_coldgate_next(1, 30000, lo, hi) == 0);
    // a walk down and up: the state changes only at the lines
    int on = 0, changes = 0;
    const uint64_t walk[] = {9000, 7000, 5000, 4200, 4000, 3000, 4500, 6000, 6100, 6200, 8000, 4100, 3900};
    const int want[] = {0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 1};
    for (int i = 0; i < 13; i++) {
        const int n = hl_coldgate_next(on, walk[i], lo, hi);
        changes += n != on;
        on = n;
        CHECK(on == want[i]);
    }
    CHECK(changes == 3);
    // a stop line under the start line is the start line: no flapping
    CHECK(hl_coldgate_high(4096, 1000) == 4096 && hl_coldgate_high(4096, 8000) == 8000);
    CHECK(hl_coldgate_next(1, 4096, 4096, 1000) == 0 && hl_coldgate_next(0, 4095, 4096, 1000) == 1);
    // start line 0: always on, as before the rule
    CHECK(hl_coldgate_next(0, 30000, 0, hi) == 1 && hl_coldgate_next(1, 30000, 0, 0) == 1);
    if (!fails) std::printf("PASS the cold gate's decision\n");
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
        subprocess.run([args.cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "host"), str(cpp), "-o", str(exe)],
                       check=True)
        subprocess.run([str(exe)], check=True)
    src = (ROOT / "host/hl_mem.c").read_text(encoding="utf-8")
    assert '#include "hl_mem_coldgate.h"' in src
    assert 'getenv("HL_MEM_COLD_LOW_MB")' in src and ": 4096;" in src, "the start line's switch or default"
    assert 'getenv("HL_MEM_COLD_HIGH_MB")' in src and ": 6144;" in src, "the stop line's switch or default"
    cold = function(src, "static DWORD WINAPI cold_main(void *unused) {")
    i_gate = cold.index("gate_on = hl_coldgate_next(gate_on, avail_mb, gate_low_mb, gate_high_mb);")
    i_skip = cold.index("if (!gate_on) continue;")
    i_pools = cold.index("else pools_pass();")
    i_heaps = cold.index("if (heaps_on) {")
    assert i_gate < i_skip < i_pools < i_heaps, "the gate is not looked at before both parts"
    assert "gate_on != was || !gate_told" in cold and "RAM available" in cold, "a change of state is not logged with the free RAM"
    print("PASS the wiring")


if __name__ == "__main__":
    main()
