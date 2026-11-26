// Copyright (C) 2026 Sacrappy

/* (CRASH3) Which big guest heap blocks the game has freed, for the back end's bare storage entries (gpu/vk/vk_draw.cpp: a table entry
   that is a bare pointer the program writes through). OoT's culling tables keep the pointer of a GPU buffer the module system's
   destroy path freed (f_80a30a00 -> f_8093f... -> the heap's free); a loader then allocates small CPU objects over the freed memory,
   and every later pass that binds the stale entry wrote GPU words over their headers and fields: the v0.4.3 module-system crash
   family (issue 55). The heap's entry gates (host/hl_trace.c) tell this table each allocation of HL_STALE_BIG bytes or more and each
   free by the block's start; the back end asks before binding a bare written entry, and leaves unbound one whose pointer starts a
   block the game freed, until a block of HL_STALE_BIG bytes or more is allocated at that address again.
   A direct-mapped table of HL_STALE_SLOTS words (the block's start and its state packed; a start whose slot another took is told as
   live: as before the guard). Header only, so tests/stale_heads_test.c runs it with no game. */
#ifndef HL_STALE_HEADS_H
#define HL_STALE_HEADS_H
#include <stdatomic.h>
#include <stdint.h>

enum { HL_STALE_SLOTS = 1 << 17, HL_STALE_BIG = 0x1000 };
#define HL_STALE_FREED 1ull   /* (the low bit: block starts are 16-aligned) */

typedef struct {
    _Atomic uint64_t slot[HL_STALE_SLOTS];   /* the block's start | HL_STALE_FREED when it was freed (0: empty) */
    _Atomic uint64_t listed, freed, revived;   /* (for the log) slots filled, big blocks freed, freed starts allocated big again */
    _Atomic uint64_t unbound;                  /* (for the log) bindings the back end was told to leave unbound */
} HlStaleHeads;

static inline uint32_t hl_stale_index(uint64_t block) {
    return (uint32_t)(((block >> 4) * 0x9E3779B97F4A7C15ull) >> 40) & (HL_STALE_SLOTS - 1);
}

/* An allocation of `size` bytes at `block`: a big one is listed live (a freed one at the same start, live again) */
static inline void hl_stale_alloc(HlStaleHeads *t, uint64_t block, uint64_t size) {
    if (!block || (block & 15) || size < HL_STALE_BIG) return;
    const uint64_t was = atomic_exchange_explicit(&t->slot[hl_stale_index(block)], block, memory_order_acq_rel);
    if (!was) atomic_fetch_add_explicit(&t->listed, 1, memory_order_relaxed);
    else if (was == (block | HL_STALE_FREED)) atomic_fetch_add_explicit(&t->revived, 1, memory_order_relaxed);
}

/* A free of the block at `block`: a listed big block becomes freed (a small one, or one whose slot was taken: nothing) */
static inline void hl_stale_free(HlStaleHeads *t, uint64_t block) {
    if (!block || (block & 15)) return;
    _Atomic uint64_t *s = &t->slot[hl_stale_index(block)];
    uint64_t w = block;
    if (atomic_compare_exchange_strong_explicit(s, &w, block | HL_STALE_FREED, memory_order_acq_rel, memory_order_relaxed))
        atomic_fetch_add_explicit(&t->freed, 1, memory_order_relaxed);
}

/* 1 when `guest` is the start of a big block the game freed and no big block was allocated there since */
static inline int hl_stale_freed(HlStaleHeads *t, uint64_t guest) {
    if (!guest || (guest & 15)) return 0;
    if (atomic_load_explicit(&t->slot[hl_stale_index(guest)], memory_order_acquire) != (guest | HL_STALE_FREED)) return 0;
    atomic_fetch_add_explicit(&t->unbound, 1, memory_order_relaxed);
    return 1;
}

#endif
