# Copyright (C) 2026 Sacrappy
"""RX_VK_RB_EARLY (ORDER2, gpu/vk/rb_early.h): the readback copied right behind the programs that write it.

A small program checks, with no GPU: the switch parse (on only with the order thread; 2 the check); the served size; that each written
binding takes the next slot, that a job's last binding is final only once the bindings a writer job makes are learned (the most of the
last jobs), and more than learned stays final; and what a read that needs job T gets: the newest final slot of T or later; to wait while
the order thread has not finished T and T has not finished another served range; the newest slot once one of those holds; none with no
slot. And, by the text, that invalidate() answers a served read before the old waits and skips them only when it was answered, that the
binding asks for its copy before the write-back decision, and that the copy is recorded right behind the dispatch.

python -I -B tests/test_rb_early.py --cxx <compiler>
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CPP = r'''
#include "rb_early.h"
#include <cstdio>
static int fails;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
int main() {
    using namespace rb_early;
    CHECK(parse(nullptr, nullptr, true).mode == 1 && parse(nullptr, nullptr, false).mode == 0);   // (on with the order thread only)
    CHECK(parse("0", nullptr, true).mode == 0 && parse("2", nullptr, true).mode == 2 && parse("7", nullptr, true).mode == 2);
    CHECK(parse("1", nullptr, false).mode == 0 && parse("2", nullptr, false).mode == 2);           // (inline: nothing to serve early; the check runs)
    CHECK(parse(nullptr, "5", true).wait_ms == 5.0 && parse(nullptr, nullptr, true).wait_ms == 30.0 && parse(nullptr, "-1", true).wait_ms == 30.0);
    CHECK(served_size(0x3980) && !served_size(0x40) && !served_size(0x9b040));
    Range r;
    // job 10 binds it 3 times: nothing learned yet, no slot is final
    Issue a = issue(r, 10), b = issue(r, 10), c = issue(r, 10);
    CHECK(a.seq == 1 && b.seq == 2 && c.seq == 3 && !a.final && !b.final && !c.final && learned(r) == 0);
    CHECK(a.slot == 1 % kSlots && c.slot == 3 % kSlots);
    // a read that needs job 10: no final slot; the order thread not done with 10, no other range finished: wait
    CHECK(pick(r, 10, 9, 0).kind == kWait);
    // done with 10: the newest slot (seq 3)
    Pick p = pick(r, 10, 10, 0);
    CHECK(p.kind == kSlotNewest && p.seq == 3);
    // job 12: learned 3 now (job 10's count): the third binding is final
    Issue d = issue(r, 12), e = issue(r, 12);
    CHECK(learned(r) == 3 && !d.final && !e.final);
    CHECK(pick(r, 12, 11, 0).kind == kWait);                     // job 12 not done, not final yet
    CHECK(pick(r, 12, 11, 12).kind == kSlotNewest);              // another range finished in job 12: this one is not job 12's to wait for
    Issue f = issue(r, 12);
    CHECK(f.final);
    p = pick(r, 12, 11, 0);
    CHECK(p.kind == kSlotFinal && p.seq == f.seq && p.slot == f.slot);
    Issue g = issue(r, 12);                                      // one more than learned: final too, and newer
    CHECK(g.final && pick(r, 12, 11, 0).seq == g.seq);
    CHECK(pick(r, 11, 11, 0).kind == kSlotFinal);                // an older target takes a later job's final slot
    CHECK(pick(r, 13, 12, 0).kind == kWait && pick(r, 13, 13, 0).seq == g.seq);
    // the history keeps the most of the last kHist jobs
    Range h;
    for (unsigned k = 0; k < 3; k++) issue(h, 1);
    issue(h, 2);
    CHECK(learned(h) == 3);
    for (uint64_t j = 3; j < 3 + kHist; j++) issue(h, j);       // kHist jobs of one binding each push the 3 out
    CHECK(learned(h) == 1);
    // a slot is written into guest memory once; a read with nothing newer leaves the game's own writes alone
    CHECK(fresh(r, g.seq) && !fresh(r, 0));
    r.applied = g.seq;
    CHECK(!fresh(r, g.seq) && !fresh(r, f.seq));
    // an overlapping written binding that is not the range taints it; the range itself does not
    Range t;
    t.guest = 0x1000, t.size = 0x3980;
    note_written(t, 0x1000, 0x3980);
    CHECK(!t.tainted);
    note_written(t, 0x4980, 0x100);   // (just past its end)
    CHECK(!t.tainted);
    note_written(t, 0x0, 0x100000);   // (a bare entry's 1 MB guess over it)
    CHECK(t.tainted);
    // the previous copy: the newest final slot of a job before the target (never a wait)
    Range q;
    for (int k = 0; k < 2; k++) issue(q, 20);   // job 20: 2 bindings (nothing learned: not final)
    issue(q, 22), issue(q, 22);                 // job 22 learns 2: its second is final
    issue(q, 24), issue(q, 24);                 // job 24: final at its second
    CHECK(pick_prev(q, 24).kind == kSlotFinal && pick_prev(q, 24).seq == 4);   // (job 22's last)
    CHECK(pick_prev(q, 25).seq == 6 && pick_prev(q, 22).kind == kNone);
    Range empty;
    CHECK(pick(empty, 5, 9, 0).kind == kNone && pick(empty, 5, 0, 0).kind == kWait);
    // the slots go round: a slot holds the newest binding that took it
    Range w;
    for (unsigned k = 0; k < kSlots + 2; k++) issue(w, 100 + k);
    CHECK(w.slots[1].seq == kSlots + 1 && w.slots[2].seq == kSlots + 2);
    if (fails) return 1;
    std::printf("PASS rb_early rules\n");
    return 0;
}
'''


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
    inv = rp[rp.index("void invalidate(uint64_t gpu, uint64_t size) {"):]
    ans = inv.index("const bool early_served = size && !ring_serve && order_thread_on() && rbearly_answer(gpu, size);")
    assert ans < inv.index("ot_join_readback(gpu, size);"), "the early answer comes after the order thread's wait"
    assert ans < inv.index("if (size && !expo_skip && !skip_old) {"), "the early answer comes after the old waits"
    assert "const bool skip_old = ring_serve || early_served;" in inv, "the old waits are skipped for a read that was not answered"
    assert "if (size && !skip_old && !rb_late && order_thread_on()" in inv, "an answered read still waits for the order thread"
    assert "if (size && !skip_old) rbearly_check(gpu, size);" in inv, "the check is not called after the old path"
    mem = (ROOT / "gpu/vk/vk_memory.cpp").read_text(encoding="utf-8")
    assert "const bool early = rbearly_bind(guest, size, p->mirror, off);\n        if (!early && (!wb_max || size <= wb_max) && !rbring_stage_bind(" in mem, \
        "a served range's binding still queues its write-back, or the copy is asked for after the write-back decision"
    assert "if (written) rbearly_note_written(" in mem, "an overlapping written binding does not taint a served range"
    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    d = draw.index("vkCmdDispatch(cmd, x, y, z);")
    assert draw.index("rbearly_after_dispatch(cmd);", d) - d < 300, "the copy is not recorded right behind the dispatch"
    early = (ROOT / "gpu/vk/vk_rbearly.cpp").read_text(encoding="utf-8")
    an = early[early.index("bool rbearly_answer("):early.index("void rbearly_check(")]
    assert "if (rb_early::fresh(ranges[ri], seq)) ranges[ri].applied = seq, write = true;" in an and "if (write) host->gpu_write(" in an, \
        "a read with nothing newer writes over the game's own writes"
    ad = early[early.index("void rbearly_after_dispatch("):early.index("bool rbearly_answer(")]
    assert ad.index("vkCmdCopyBuffer") < ad.index("vkCmdFillBuffer"), "the stamp is written before the copy"
    assert "VK_PIPELINE_STAGE_2_HOST_BIT" in ad, "the host's read of the slot is not ordered after the stamp"
    assert "rb_early::issue(ranges[ri], ot_current_job())" in early, "the slots are not tagged with the order thread's job"
    print("PASS the wiring")


if __name__ == "__main__":
    main()
