// Copyright (C) 2026 Sacrappy
// RX_VK_RB_EARLY (ORDER2, docs/research/order-readback-decouple.md): a readback range staged right behind each program that writes it,
// not at the end of its submission. The pure rules, with no Vulkan in them, so a small program can test them (tests/test_rb_early.py):
// - a range is served when the CPU reads it and its size is one of the served sizes (the 0x3980 culling / camera results, R4);
// - every written binding of a served range, in the job the order thread is replaying, takes the next slot of that range's ring; the slot
//   is final when the job's bindings of the range reach the number learned from the jobs before (the most of the last kHist writer jobs);
// - a read needs the job the game handed over last before its present (the order thread's `ot_present_sub`): it is answered with the
//   newest final slot of that job or a later one; if there is none yet, it waits while the order thread has not finished that job and the
//   job has not finished writing some other served range (then the range is not this job's: its newest slot is the answer);
// - the slot's bytes are taken once the GPU has stamped it (the copy is on the GPU right behind the dispatch, not at the submission's end).
#pragma once
#include <cstdint>
#include <cstdlib>

namespace rb_early {

constexpr unsigned kRanges = 8;              // ranges served at most
constexpr unsigned kSlots = 32;              // slots a range (each written binding takes one)
constexpr uint64_t kMaxBytes = 0x4000;       // the largest range served
constexpr uint64_t kStampOffset = kMaxBytes; // the slot's stamp (the binding's sequence number), written by the GPU after the copy
constexpr uint64_t kSlotBytes = kMaxBytes + 256;
constexpr unsigned kHist = 8;

/// RX_VK_RB_EARLY=<0|1|2> (1 with the order thread: served; 0 off; 2 a check: the old path runs and each read is compared with the slot
/// the rule would have handed out), RX_VK_RB_EARLY_WAIT_MS (30): how long a read waits for its slot before it takes the old path.
/// Off without the order thread (inline, the reads find the submission replayed already)
struct Config {
    int mode = 0;
    double wait_ms = 30.0;
};
inline Config parse(const char* mode, const char* wait, bool order_thread) {
    Config c;
    c.mode = order_thread ? 1 : 0;
    if (mode && *mode) {
        const int m = atoi(mode);
        c.mode = m < 0 ? 0 : (m > 2 ? 2 : m);
    }
    if (!order_thread) c.mode = 0;
    if (wait && *wait) {
        const double w = atof(wait);
        if (w >= 0) c.wait_ms = w;
    }
    return c;
}
inline bool served_size(uint64_t size) { return size == 0x3980; }

struct Slot {
    uint32_t seq = 0;    // 1, 2, ... (0: empty)
    uint64_t job = 0;    // the order thread's job (its sequence number) the binding was recorded in
    bool final = false;  // the job's last binding of the range, as learned
};
struct Range {
    uint64_t guest = 0, size = 0;
    uint32_t next_seq = 0;
    uint64_t cur_job = 0;      // the job binding it now, and how many times so far
    unsigned cur_count = 0;
    unsigned hist[kHist] = {};  // bindings a writer job, the last jobs
    unsigned nhist = 0;
    Slot slots[kSlots];
};
/// The bindings a writer job makes of the range, as learned (0: none learned yet)
inline unsigned learned(const Range& r) {
    unsigned n = 0;
    for (unsigned i = 0; i < r.nhist && i < kHist; i++) n = r.hist[i] > n ? r.hist[i] : n;
    return n;
}
struct Issue {
    uint32_t seq;
    unsigned slot;
    bool final;
};
/// A written binding of the range in job `job` (jobs come in increasing order)
inline Issue issue(Range& r, uint64_t job) {
    if (job != r.cur_job) {
        if (r.cur_count) r.hist[r.nhist++ % kHist] = r.cur_count;
        r.cur_job = job, r.cur_count = 0;
    }
    r.cur_count++;
    const uint32_t seq = ++r.next_seq;
    const unsigned slot = seq % kSlots;
    const unsigned n = learned(r);
    const bool fin = n && r.cur_count >= n;
    r.slots[slot] = Slot{seq, job, fin};
    return Issue{seq, slot, fin};
}
enum Kind { kWait = 0, kSlotFinal = 1, kSlotNewest = 2, kNone = 3 };
struct Pick {
    int kind = kNone;
    unsigned slot = 0;
    uint32_t seq = 0;
};
/// What a read that needs job `target` gets: the newest final slot of a job >= target; else, once the order thread is done with the target
/// (done >= target) or the target (or a later job) has finished writing another served range (other_final_job >= target), the range's newest
/// slot whatever its job; else wait. No slot at all: none (the old path)
inline Pick pick(const Range& r, uint64_t target, uint64_t done, uint64_t other_final_job) {
    Pick p;
    int best = -1, newest = -1;
    for (unsigned i = 0; i < kSlots; i++) {
        const Slot& s = r.slots[i];
        if (!s.seq) continue;
        if (newest < 0 || s.seq > r.slots[newest].seq) newest = (int)i;
        if (s.final && s.job >= target && (best < 0 || s.seq > r.slots[best].seq)) best = (int)i;
    }
    if (best >= 0) return Pick{kSlotFinal, (unsigned)best, r.slots[best].seq};
    if (done >= target || other_final_job >= target) {
        if (newest < 0) return p;
        return Pick{kSlotNewest, (unsigned)newest, r.slots[newest].seq};
    }
    p.kind = kWait;
    return p;
}

}   // namespace rb_early
