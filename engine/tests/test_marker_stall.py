"""RX_VK_CHECKPOINTS's marker watch (issue 14): the AMD buffer markers scanned, and a GPU stuck for the stall time reported
once, before any reset, with no submission coming back. gpu/vk/vk_draw.cpp's MarkerScan, marker_scan and MarkerStall,
compiled alone against a marker buffer of the test's own."""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()

    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    start, end = draw.index("struct MarkerScan {"), draw.index("double marker_stall_seconds() {")
    ring = draw[draw.index("std::atomic<uint64_t> reach_seen[1 << 16];"):draw.index("// ---- end of the ring ----")]
    work = draw[draw.index("/// What a marker's work is, for the report"):draw.index("const char* checkpoint_kind(char c) {")]
    shape = draw[draw.index("struct Checkpoint {"):draw.index("Checkpoint checkpoints[1 << 16];")]
    fixture = r'''
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
std::atomic<uint32_t> checkpoint_n{0};
uint32_t words[2 << 16];
volatile uint32_t* marker_words = words;
''' + shape + "Checkpoint checkpoints[1 << 16];\nthread_local uint32_t checkpoint_last = 0;\n" + ring + work + draw[start:end] + r'''
// (marker s reached: its top-of-pipe word; finished: its bottom-of-pipe word, all the work before it done)
void reach(uint32_t s) { words[2 * ((s - 1) & 0xFFFF)] = s; }
void finish(uint32_t s) { reach(s), words[2 * ((s - 1) & 0xFFFF) + 1] = s; }

int main() {
    MarkerStall w;
    w.stall_s = 2.0;
    // (no markers: nothing under way, never a stall)
    for (double t = 0; t < 10; t += 0.25) assert(!w.step(marker_scan(), t));

    // (ten recorded and sent, four finished, the fifth's work stuck)
    checkpoint_n = 10;
    for (uint32_t s = 1; s <= 10; s++) reach(s);
    for (uint32_t s = 1; s <= 4; s++) finish(s);
    MarkerScan m = marker_scan();
    assert(m.done == 4 && m.last_done == 4 && m.pending == 6 && m.n == 10);
    assert(!w.step(m, 10.0));   // (four more finished than before: progress, the clock starts)
    assert(!w.step(marker_scan(), 11.0) && !w.step(marker_scan(), 11.9));
    // (the CPU records twenty more the GPU never reaches: not progress)
    checkpoint_n = 30;
    assert(marker_scan().pending == 6);
    assert(w.step(marker_scan(), 12.1));   // (2.1 s: the stall, reported)
    assert(!w.step(marker_scan(), 12.5) && !w.step(marker_scan(), 20.0));   // (once a stall)

    // (marker 5 finishes: progress, and the watch is armed again)
    finish(5);
    assert(!w.step(marker_scan(), 21.0));
    assert(!w.step(marker_scan(), 22.9));
    assert(w.step(marker_scan(), 23.1));

    // (all of them finished: nothing under way, no stall however long)
    for (uint32_t s = 1; s <= 30; s++) finish(s);
    for (double t = 24; t < 40; t += 0.25) assert(!w.step(marker_scan(), t));

    // (the oldest finished ones pushed out of the 65535 as markers are recorded: fewer finished is not progress)
    MarkerStall v;
    v.stall_s = 2.0;
    MarkerScan a{100, 100, 1, 200}, b{90, 100, 1, 300};
    assert(!v.step(a, 0.0) && !v.step(b, 1.0) && v.step(b, 2.5));

    // (past the ring's wrap: marker 70000 in slot 70000 - 1 & 0xFFFF, a slot's older marker not taken for it)
    for (auto& x : words) x = 0;
    checkpoint_n = 70000;
    finish(70000 - 65536);   // (an old marker in the slot 70000 shares: not marker 70000)
    reach(70000);
    m = marker_scan();
    assert(m.done == 0 && m.pending == 1 && m.last_done == 0);

    // (when the watch first saw a marker reached: a look at 5000 ms stamps the ones reached then, and the report counts from it)
    for (auto& x : words) x = 0;
    checkpoint_n = 10;
    for (uint32_t s = 1; s <= 3; s++) reach(s);
    marker_scan(5000);
    reach(4);
    marker_scan(5300);                         // (4 first seen a look later)
    marker_scan(6000);                         // (a later look does not move a time already taken)
    assert(marker_seen_text(1, 8200) == "reached 3.2 s ago");
    assert(marker_seen_text(4, 8200) == "reached 2.9 s ago");
    assert(marker_seen_text(5, 8200) == "not seen reached");   // (never reached)
    assert(marker_seen_text(1 + 65536, 8200) == "not seen reached");   // (the slot holds marker 1, not its successor)
    assert(marker_seen_text(1, 5000 + 7) == "reached 0.0 s ago");
    {
        for (auto& c : reach_seen) c = 0;
        uint32_t wrapped = 0xFFFFFF00u;
        marker_scan(wrapped);
        assert(marker_seen_text(1, wrapped + 2500) == "reached 2.5 s ago");   // (across the 32-bit wrap)
    }

    // (what the work is, for the report)
    Checkpoint k{};
    assert(checkpoint_work_text(k).empty());   // (unknown: nothing printed)
    k.shape = 'x', k.a = 64, k.b = 2, k.c = 1;
    assert(checkpoint_work_text(k) == ", 64 x 2 x 1 groups");
    k.shape = 'n';
    assert(checkpoint_work_text(k) == ", groups read from GPU memory");
    k.shape = 'E', k.a = 36000, k.b = 3;
    assert(checkpoint_work_text(k) == ", 36000 indices x 3 instances");
    k.shape = 'V', k.a = 6, k.b = 1;
    assert(checkpoint_work_text(k) == ", 6 vertices x 1 instances");
    k.shape = 'M', k.a = 5, k.b = 1, k.c = 1;
    assert(checkpoint_work_text(k) == ", mesh 5 x 1 x 1 groups");
    k.shape = 'I', k.a = 12;
    assert(checkpoint_work_text(k) == ", indirect, up to 12 records");
    puts("ok");
}
'''
    with tempfile.TemporaryDirectory(prefix="marker-stall-") as tmp:
        work = Path(tmp)
        source, exe = work / "fixture.cpp", work / "fixture"
        source.write_text(fixture, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++17", str(source), "-o", str(exe)], check=True)
        out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        assert out.strip() == "ok", out
    print("PASS: the buffer markers' scan, a stall reported once after its time, again after progress, none with nothing "
          "under way, and the ring's wrap")


if __name__ == "__main__":
    main()
