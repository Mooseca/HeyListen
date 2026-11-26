// Copyright (C) 2026 Sacrappy

/* (CRASH3) The last GPU write-back by guest page, always on, for the crash record (host/mkw_glue.c report_crash): the back
   end tells each range it writes back into guest memory (gpu/vk/vk_api.h gpu_wrote, the write-backs and the lazy release's
   writes trace_gpu names), and a crash prints, for the faulting address and every register that points into guest memory,
   how long ago the GPU's copy last went over that page and in which submission. The v0.4.3 module-system crashes (issue 55)
   read objects a stale write-back overwrote: this line names that culprit at the players', where no trace runs.
   A direct-mapped table of HOS_WBS_SLOTS words (page and milliseconds packed, plus the submission's low 32 bits): a page
   whose slot another page took since is told as not known, never as another page's. 768 KB; per write-back, two relaxed
   stores a page (at most HOS_WBS_MAX_PAGES pages: the first ones of a larger range). Header only, so that
   tests/wb_stamp_test.c runs it with no game. */
#ifndef HOS_WB_STAMP_H
#define HOS_WB_STAMP_H
#include <stdatomic.h>
#include <stdint.h>

enum { HOS_WBS_SLOTS = 1 << 16, HOS_WBS_MAX_PAGES = 4096 };
#define HOS_WBS_PAGE_BITS 28   /* (guest pages below 2^28: the guest window's 1 TB and more) */

typedef struct {
    _Atomic uint64_t key[HOS_WBS_SLOTS];     /* page + 1 in the low HOS_WBS_PAGE_BITS bits, the milliseconds above (0: empty) */
    _Atomic uint32_t value[HOS_WBS_SLOTS];   /* the submission's timeline value, low 32 bits */
} HosWbStamps;

static inline uint32_t hos_wbs_slot(uint64_t page) {
    return (uint32_t)((page * 0x9E3779B97F4A7C15ull) >> 48) & (HOS_WBS_SLOTS - 1);
}

/* A write-back of [guest, guest + size) in submission `value`, `now_ms` after the start */
static inline void hos_wbs_note(HosWbStamps *s, uint64_t guest, uint64_t size, uint64_t value, uint64_t now_ms) {
    if (!size) return;
    const uint64_t first = guest >> 12, last = (guest + size - 1) >> 12;
    const uint64_t end = last - first >= HOS_WBS_MAX_PAGES ? first + HOS_WBS_MAX_PAGES - 1 : last;
    for (uint64_t page = first; page <= end; page++) {
        if (page + 1 >= (1ull << HOS_WBS_PAGE_BITS)) break;
        const uint32_t k = hos_wbs_slot(page);
        atomic_store_explicit(&s->value[k], (uint32_t)value, memory_order_relaxed);
        atomic_store_explicit(&s->key[k], (now_ms << HOS_WBS_PAGE_BITS) | (page + 1), memory_order_relaxed);
    }
}

/* The page of guest address `guest`: 1 with its last write-back's age in ms and submission when the table has it, else 0 */
static inline int hos_wbs_find(HosWbStamps *s, uint64_t guest, uint64_t now_ms, uint64_t *age_ms, uint32_t *value) {
    const uint64_t page = guest >> 12;
    if (page + 1 >= (1ull << HOS_WBS_PAGE_BITS)) return 0;
    const uint32_t k = hos_wbs_slot(page);
    const uint64_t w = atomic_load_explicit(&s->key[k], memory_order_relaxed);
    if ((w & ((1ull << HOS_WBS_PAGE_BITS) - 1)) != page + 1) return 0;
    const uint64_t at = w >> HOS_WBS_PAGE_BITS;
    *age_ms = now_ms >= at ? now_ms - at : 0;
    *value = atomic_load_explicit(&s->value[k], memory_order_relaxed);
    return 1;
}

#endif
