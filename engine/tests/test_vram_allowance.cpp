// Copyright (C) 2026 Sacrappy

#include "../gpu/vk/vram_allowance.h"
#include <cstdio>
using vram_allowance::past_allowance;
static int bad;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL: %s\n", #x); bad++; } } while (0)
int main() {
    const uint64_t MB = 1ull << 20;
    CHECK(past_allowance(5940 * MB, 5940 * MB) == 5940 * MB - 5940 * MB / 10);
    CHECK(past_allowance(6600 * MB, 6600 * MB + 8 * MB) < 6600 * MB);
    CHECK(past_allowance(6600 * MB + 8 * MB, 6600 * MB) < 6600 * MB);
    CHECK(past_allowance(5300 * MB, 6500 * MB) == 6500 * MB);
    CHECK(past_allowance(7602 * MB, 6982 * MB) == 6982 * MB);
    CHECK(past_allowance(5000 * MB, 0) == 0);
    CHECK(past_allowance(0, 0) == 0);
    {   // (Longshot 8941d01b4, #2082) past the allowance no floor holds the textures (a GTX 1060 6 GB at 6128 MB of the 5231 it allowed,
        // 1606 MB of textures: no rule could take one while the driver paged); within it the floor holds as before
        using vram_allowance::floor_within;
        using vram_allowance::target_floor;
        const uint64_t a = 5231 * MB;
        CHECK(vram_allowance::kTargetFloor == 1024 * MB);
        CHECK(floor_within(1800 * MB, 6128 * MB, a) == 0);                  // (past it: none)
        CHECK(floor_within(2600 * MB, 6128 * MB, a) == 0);                  // (a larger, dynamic floor gives way too)
        CHECK(floor_within(1800 * MB, a + 1, a) == 0);                      // (one byte past)
        CHECK(floor_within(1800 * MB, a, a) == 1800 * MB);                  // (at it, not past)
        CHECK(floor_within(1800 * MB, 5100 * MB, a) == 1800 * MB);          // (within it: as it was)
        CHECK(floor_within(1800 * MB, 6128 * MB, 0) == 1800 * MB);          // (no allowance known: as it was)
        CHECK(target_floor(6128 * MB, a) == 0);
        CHECK(target_floor(5100 * MB, a) == 1024 * MB);
        CHECK(target_floor(a, a) == 1024 * MB);
        CHECK(target_floor(6128 * MB, 0) == 1024 * MB);
        // (an allowance the driver gave as the count, past_allowance: the floor gives way, so the rules give back)
        CHECK(target_floor(5940 * MB, past_allowance(5940 * MB, 5940 * MB)) == 0);
    }
    if (bad) return 1;
    std::printf("PASS: the allowance rule\n");
    return 0;
}
