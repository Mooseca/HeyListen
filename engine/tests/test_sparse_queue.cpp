// gpu/vk/sparse_queue.h: which family binds the pools made of several dma-bufs (RX_VK_SPARSE_QUEUE, issue 14), and when the
// start-up log suggests raising udmabuf's limit. No GPU: the families are real drivers' lists, written out.
#include "../gpu/vk/sparse_queue.h"

#include <cstdio>

#define CHECK(name, condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s at line %d\n", name, __LINE__); return 1; } } while (0)

int main() {
    using sparse_queue::kNone;
    using sparse_queue::pick_family;
    using sparse_queue::limit_hint;
    // (VkQueueFlagBits: 1 graphics, 2 compute, 4 transfer, 8 sparse binding, 0x20 video decode, 0x40 video encode)

    {   // RADV on an RX 9070 XT (Mesa 26.2, vulkaninfo): graphics, compute x4, decode, encode, and a sparse-only family
        const uint32_t f[] = {0xF, 0xE, 0x20, 0x40, 0x8};
        CHECK("radv: the sparse-only family", pick_family(f, 5, 0, kNone) == 4);
        CHECK("radv: the sparse-only family beside a present queue", pick_family(f, 5, 0, 1) == 4);
    }
    {   // an older RADV without the sparse-only family: its compute family, unless the presents have it
        const uint32_t f[] = {0xF, 0xE, 0x20};
        CHECK("old radv: compute", pick_family(f, 3, 0, kNone) == 1);
        CHECK("old radv: compute taken by the presents", pick_family(f, 3, 0, 1) == kNone);
    }
    {   // NVIDIA-like: graphics x16, transfer with sparse binding, compute with sparse binding
        const uint32_t f[] = {0xF, 0xC, 0xE};
        CHECK("nvidia: the first without graphics", pick_family(f, 3, 0, kNone) == 1);
        CHECK("nvidia: the other one when the first presents", pick_family(f, 3, 0, 1) == 2);
    }
    {   // the replay's family is never taken, nor another graphics family, nor one without sparse binding
        const uint32_t f[] = {0xF, 0xF, 0x6};
        CHECK("no other family", pick_family(f, 3, 0, kNone) == kNone);
        const uint32_t g[] = {0x8};
        CHECK("the replay's own family", pick_family(g, 1, 0, kNone) == kNone);
        CHECK("no families", pick_family(g, 0, 0, kNone) == kNone);
    }
    {   // the hint: below 1 GB (the largest import), not from 1 GB on; this PC's limit (2147483647 MB) does not overflow
        CHECK("64 MB", limit_hint(64ull << 20));
        CHECK("1023 MB", limit_hint(1023ull << 20));
        CHECK("1024 MB", !limit_hint(1024ull << 20));
        CHECK("raised far", !limit_hint(2147483647ull << 20));
    }
    std::printf("sparse_queue: ok\n");
    return 0;
}
