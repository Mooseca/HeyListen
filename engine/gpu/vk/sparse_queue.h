#pragma once
// (Linux, issue 14) A pool larger than udmabuf's size limit is several dma-bufs bound into one sparse buffer
// (vk_memory.cpp import_dma_buf_pieces). Bound on the replay's queue, the bind's fence signals only once everything sent to
// that queue before it has finished on the GPU: the import waited for the queued frames, ~1 s on a Steam Deck, on the
// recording thread (`slow submit: ... dispatch 1083.1`). Measured on an RX 9070 XT (RADV): 112 MB in two 64 MB pieces took
// 3-5 ms with the queue idle and 540 ms behind 540 ms of queued GPU work, all of it in the fence wait; on a queue of
// another family it took 2-4 ms either way. Nothing sent before can reach the new buffer, so it need not wait for it.
// RX_VK_SPARSE_QUEUE=1 binds on such a queue (default off until it has been run in the game).
#include <cstdint>

namespace sparse_queue {

constexpr uint32_t kNone = UINT32_MAX;
constexpr uint32_t kGraphics = 0x1, kSparseBinding = 0x8;   // (VkQueueFlagBits: VK_QUEUE_GRAPHICS_BIT, VK_QUEUE_SPARSE_BINDING_BIT)

/// The family for the pools' sparse binds, given each family's queueFlags: one with sparse binding that is neither the
/// replay's family nor the presents' (kNone for none). A family with nothing else first (RADV's sparse queue, whose binds
/// the CPU makes), then one without graphics (a compute or transfer family); kNone when there is neither.
inline uint32_t pick_family(const uint32_t* flags, uint32_t n, uint32_t replay, uint32_t present) {
    for (int pass = 0; pass < 2; pass++)
        for (uint32_t i = 0; i < n; i++) {
            if (i == replay || i == present || !(flags[i] & kSparseBinding)) continue;
            if (pass == 0 ? flags[i] == kSparseBinding : !(flags[i] & kGraphics)) return i;
        }
    return kNone;
}

/// Whether the start-up log suggests raising udmabuf's size limit: a pool is imported up to 1 GB at once, and one larger
/// than the limit is made of pieces in a sparse buffer
inline bool limit_hint(uint64_t limit_bytes) { return limit_bytes < (1ull << 30); }

} // namespace sparse_queue
