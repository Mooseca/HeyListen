// Copyright (C) 2026 Sacrappy

// (CRASH3) The write-back of a guessed written range (vk_memory.cpp, RX_VK_WB_GUESS_CHECKED): a bare storage-table entry's
// first 64 bytes, which vk_draw.cpp marks written though the program may never write through that entry. It was copied whole
// from the mirror into guest memory; when the entry was a stale pointer into memory the game's heap had given to CPU objects,
// the copy put back the bytes the mirror's sync had read over the CPU's newer writes (the module jobs' destroy-path crashes of
// v0.4.3). Now it is staged and written by the CPU once its submission is done: nothing when the page was written by the CPU
// since the mirror's sync, else only the words that differ from guest memory (the GPU's: guest memory still holds what the
// sync read). tests/test_wb_guess.py
#pragma once
#include <cstdint>
#include <cstring>

namespace wb_guess {

/// Whether the CPU wrote the page since the mirror's sync: its write generation newer than the one the mirror holds.
inline bool page_written_since(uint32_t page_gen, uint32_t synced_gen) { return page_gen > synced_gen; }

/// The spans of [0, n) where src differs from guest, by 4-byte words (the GPU's unit; a tail of fewer bytes as one word),
/// in order and merged: emit(offset, bytes).
template <class F> void differing_spans(const uint8_t* guest, const uint8_t* src, uint64_t n, F&& emit) {
    for (uint64_t w = 0; w < n;) {
        uint64_t k = n - w < 4 ? n - w : 4;
        if (!std::memcmp(guest + w, src + w, (size_t)k)) {
            w += k;
            continue;
        }
        uint64_t x = w + k;
        while (x < n) {
            const uint64_t m = n - x < 4 ? n - x : 4;
            if (!std::memcmp(guest + x, src + x, (size_t)m)) break;
            x += m;
        }
        emit(w, x - w);
        w = x;
    }
}

}  // namespace wb_guess
