// Copyright (C) 2026 Sacrappy

// (CRASH3) gpu/vk/wb_guess.h: the checked write-back of a guessed range (a bare storage entry's 64-byte head) never goes over
// the CPU's writes. Built and run by test_wb_guess.py.
#include "../gpu/vk/wb_guess.h"
#include <cstdio>
#include <cstring>
#include <utility>
#include <vector>

static int fails = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)

using Spans = std::vector<std::pair<uint64_t, uint64_t>>;
static Spans spans_of(const uint8_t* guest, const uint8_t* src, uint64_t n) {
    Spans s;
    wb_guess::differing_spans(guest, src, n, [&](uint64_t at, uint64_t len) { s.push_back({at, len}); });
    return s;
}

/// What a write-back of the head leaves in guest memory: whole (as before), or checked (gen: the page's write generation then,
/// synced: the mirror's)
static void write_back(uint8_t* guest, const uint8_t* mirror, uint64_t n, bool checked, uint32_t gen, uint32_t synced) {
    if (!checked) {
        std::memcpy(guest, mirror, n);
        return;
    }
    if (wb_guess::page_written_since(gen, synced)) return;
    wb_guess::differing_spans(guest, mirror, n, [&](uint64_t at, uint64_t len) { std::memcpy(guest + at, mirror + at, len); });
}

int main() {
    using wb_guess::page_written_since;
    CHECK(page_written_since(8, 7));    // (a CPU write collected after the mirror's sync)
    CHECK(!page_written_since(7, 7));   // (the page as the mirror has it)
    CHECK(!page_written_since(3, 7));

    uint8_t g[64], m[64];
    for (int k = 0; k < 64; k++) g[k] = m[k] = (uint8_t)k;
    CHECK(spans_of(g, m, 64).empty());   // (nothing the GPU wrote: nothing written)
    m[8] = 0xaa, m[13] = 0xbb, m[40] = 0xcc;   // (the GPU's words: 8..11, 12..15, 40..43)
    CHECK((spans_of(g, m, 64) == Spans{{8, 8}, {40, 4}}));
    m[63] = 0xdd;
    CHECK((spans_of(g, m, 64) == Spans{{8, 8}, {40, 4}, {60, 4}}));
    CHECK((spans_of(g + 60, m + 60, 3) == Spans{}));     // (a tail of 3 bytes, the same)
    CHECK((spans_of(g + 60, m + 60, 4) == Spans{{0, 4}}));
    uint8_t t1[6] = {1, 2, 3, 4, 5, 6}, t2[6] = {1, 2, 3, 4, 5, 9};
    CHECK((spans_of(t1, t2, 6) == Spans{{4, 2}}));       // (a tail shorter than a word, as one)

    // The crash: a stale table entry points into the game's heap. The mirror's sync read the 64 bytes (a 0x28-byte block
    // straddling them, then the next block's header); the program does not write through the entry; the CPU frees the
    // block and allocates another there before the write-back lands (its new header at +0x20).
    uint8_t heap[64], mirror[64];
    for (int k = 0; k < 64; k++) heap[k] = (uint8_t)(0x40 + k);
    std::memcpy(mirror, heap, 64);   // (the sync)
    const uint8_t header[8] = {0x28, 0, 0, 0, 0x11, 0x22, 0x33, 0x44};
    std::memcpy(heap + 0x20, header, 8);   // (the CPU's write after the sync, page generation 9 > the mirror's 8)
    uint8_t before[64], old_way[64];
    std::memcpy(before, heap, 64);
    std::memcpy(old_way, heap, 64);
    write_back(old_way, mirror, 64, false, 9, 8);
    CHECK(std::memcmp(old_way + 0x20, header, 8) != 0);   // (as before: the header reverted, the heap corrupt)
    write_back(heap, mirror, 64, true, 9, 8);
    CHECK(!std::memcmp(heap, before, 64));                // (checked: the page written since the sync, nothing written)

    // A real result: the GPU wrote a count, the CPU did not touch the page since the sync: the count reaches guest memory
    // and nothing else changes
    uint8_t g2[64], m2[64];
    for (int k = 0; k < 64; k++) g2[k] = m2[k] = (uint8_t)(0x80 + k);
    m2[4] = 7;
    write_back(g2, m2, 64, true, 8, 8);
    CHECK(!std::memcmp(g2, m2, 64));

    if (fails) std::printf("%d checks failed\n", fails);
    else std::printf("wb guess: all cases right\n");
    return fails ? 1 : 0;
}
