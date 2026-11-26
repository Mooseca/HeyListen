// Copyright (C) 2026 Sacrappy

/* Game-free test of the big heap blocks' table (host/hl_stale_heads.h; tests/test_stale_heads.py builds it): the case of the
   v0.4.3 module-system crash (a 0x8000 culling buffer freed, a 0x90 CPU object allocated over it, the stale pointer judged), a
   buffer allocated again at the same start, small blocks, collisions. Exits non-zero on a failure. */
#include <stdio.h>
#include <stdlib.h>
#include "hl_stale_heads.h"

static int failures;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); putchar('\n'); } } while (0)

static HlStaleHeads t;

int main(void) {
    const uint64_t buf = 0x117e70a000;
    CHECK(!hl_stale_freed(&t, buf), "an unknown start is live");
    hl_stale_alloc(&t, buf, 0x8000);
    CHECK(!hl_stale_freed(&t, buf), "a live buffer");
    hl_stale_free(&t, buf);
    CHECK(hl_stale_freed(&t, buf), "the buffer freed by the destroy path");
    hl_stale_alloc(&t, buf + 0x10, 0x90);   /* (the loader's object over it, its header at the buffer's start) */
    CHECK(hl_stale_freed(&t, buf), "a small block over it leaves it freed");
    hl_stale_alloc(&t, buf, 0x90);
    CHECK(hl_stale_freed(&t, buf), "a small block at the same start leaves it freed");
    CHECK(t.unbound == 3, "three bindings refused: %llu", (unsigned long long)t.unbound);
    hl_stale_alloc(&t, buf, 0x8000);
    CHECK(!hl_stale_freed(&t, buf) && t.revived == 1, "a buffer allocated again at the start revives it");
    /* a small block freed: nothing listed; an unaligned pointer: never judged */
    hl_stale_alloc(&t, 0x2000, 0x100);
    hl_stale_free(&t, 0x2000);
    CHECK(!hl_stale_freed(&t, 0x2000), "a small block is not listed");
    CHECK(!hl_stale_freed(&t, buf + 8), "an unaligned pointer");
    /* a pointer inside a freed block (not its start): not judged (the guard's known limit) */
    hl_stale_alloc(&t, 0x5000000, 0x10000);
    hl_stale_free(&t, 0x5000000);
    CHECK(hl_stale_freed(&t, 0x5000000) && !hl_stale_freed(&t, 0x5000100), "only the start");
    /* another block taking the slot: the freed start is then told live (as before the guard), never another's state */
    uint64_t other = 0;
    for (uint64_t a = 0x5000010; a < 0x5000010 + (1ull << 30) && !other; a += 16)
        if (hl_stale_index(a) == hl_stale_index(0x5000000)) other = a;
    CHECK(other, "a colliding start");
    hl_stale_alloc(&t, other, 0x1000);
    CHECK(!hl_stale_freed(&t, 0x5000000) && !hl_stale_freed(&t, other), "the slot taken");
    hl_stale_free(&t, 0x5000000);
    CHECK(!hl_stale_freed(&t, other), "a free of the old start does not touch the new one");
    CHECK(t.freed == 2 && t.listed == 2, "counts: %llu freed, %llu listed", (unsigned long long)t.freed, (unsigned long long)t.listed);
    if (failures) {
        printf("stale_heads_test: %d failures\n", failures);
        return 1;
    }
    puts("stale heads: ok");
    return 0;
}
