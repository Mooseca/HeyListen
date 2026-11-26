// Copyright (C) 2026 Sacrappy

/* (STUT3, 26 Nov 2026) When the cold-pages pass (host/hl_mem.c) may take pages out of the working set: only while the PC is short
   of RAM. On the PC 3050 (32 GB, 4.4 GB free at the least in play) the pass took 5-6 GB of GPU-pool pages and ~3 GB of heap pages
   out in a six-zone warp tour and 4-5 GB came back, faulted in by the game's texture compaction, its loaders and the replay; with
   the pass off the frames over 100 ms fell by 31 percent in one series. Gating the pools alone moved the churn to the heaps (their
   quiet rule had been kept on by the pools' come-backs): the whole pass is gated (docs/research/stut3-stutters-3050.md).
   The rule, checked before each pass, with hysteresis: the pass starts when the available physical RAM falls under `low_mb` and
   stops once it is back at `high_mb` or more; in between it keeps its state. low_mb 0: always on (the pass as before the rule).
   HL_MEM_COLD_LOW_MB (default 4096) and HL_MEM_COLD_HIGH_MB (default 6144; never under low_mb). Plain C: host/hl_mem.c and
   tests/test_cold_gate.py include it. */
#ifndef HL_MEM_COLDGATE_H
#define HL_MEM_COLDGATE_H
#include <stdint.h>

#define HL_COLDGATE_LOW_DEFAULT_MB 4096u   /* (host/hl_mem.c reads the switches: these are its defaults) */
#define HL_COLDGATE_HIGH_DEFAULT_MB 6144u

/* the stop line actually used: never under the start line (a stop under the start would turn the part on and off every pass) */
static inline uint64_t hl_coldgate_high(uint64_t low_mb, uint64_t high_mb) { return high_mb < low_mb ? low_mb : high_mb; }

/* the pass's state after a look at the free RAM: on = taking pages out */
static inline int hl_coldgate_next(int on, uint64_t avail_mb, uint64_t low_mb, uint64_t high_mb) {
    if (!low_mb) return 1;
    high_mb = hl_coldgate_high(low_mb, high_mb);
    if (!on && avail_mb < low_mb) return 1;
    if (on && avail_mb >= high_mb) return 0;
    return on;
}
#endif
