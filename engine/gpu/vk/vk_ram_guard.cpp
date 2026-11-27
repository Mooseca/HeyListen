// Copyright (C) 2026 Sacrappy

// (HeyListen, LAP2) RX_VK_MEM_GUARD (on by default for an integrated AMD GPU on Windows, the pools only: mem_guard_rule.h): on an integrated GPU the memory is the PC's, and AMD's Windows driver (amdvlk64.dll 31.0.21925.1001)
// stops the process with a fast fail (0xc0000409, fast-fail code 7: abort()) when the memory it needs for itself is not there. The crashes
// of a load (Kokiri Forest after a teleport) were all inside vkCreateDescriptorPool, with the heaps the GPU reaches at their ceiling:
// the device-local heaps' use (2.4-2.8 GB, over their 486 MB allowance: the driver puts the rest in system memory) plus the system heaps'
// (4.2-4.8 GB of 7238 MB) at 7.0 GB and more, and the PC's RAM down to a few hundred MB at the worst. This renderer filled both to the
// driver's own budget, leaving the driver nothing for its pools, command buffers and pipelines.
// With the guard on, a memory block (not the guest memory's imports, which take nothing new) and a descriptor pool are not asked of the
// driver when it would leave less than the headroom: the call is answered VK_ERROR_OUT_OF_DEVICE_MEMORY at once (a pool: none made, the
// draw left out), the allocator and the callers' paths follow (an image not made, a smaller block), the textures' budget comes down.
//   RX_VK_MEM_GUARD_GTT_MB=<MB>  headroom under the system heaps' size, counting the device heaps' use too (default 1024; 0: not checked)
//   RX_VK_MEM_GUARD_BLOCKS / RX_VK_MEM_GUARD_POOLS  1 / 0: that part on / off (the textures' budget is cut with the blocks')
//   RX_VK_MEM_GUARD_RAM_MB=<MB>  available physical RAM kept (default 512; 0: not checked); a descriptor pool needs twice it
#include "vk_internal.h"
#include "mem_guard_rule.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#ifdef _WIN32
#include <windows.h>
#endif

namespace mkwvk {
extern std::atomic<int> vram_alloc_failures;   // (vk_vma.cpp: read by the texture budget)

static uint64_t env_mb(const char* name, uint64_t def) {
    const char* e = getenv(name);
    return e && *e ? (uint64_t)std::max(0, atoi(e)) : def;
}
uint64_t ram_guard_reserve_mb() {
    static const uint64_t v = env_mb("RX_VK_MEM_GUARD_RAM_MB", 512);
    return v;
}
static uint64_t gtt_headroom_mb() {
    static const uint64_t v = env_mb("RX_VK_MEM_GUARD_GTT_MB", 1024);
    return v;
}
/// where the guard is on (mem_guard_rule.h: an integrated AMD GPU on Windows has the pools by default; the switches force each part)
static const mem_guard::Rule& rule() {
    static const mem_guard::Rule r = [] {
#ifdef _WIN32
        const bool windows = true;
#else
        const bool windows = false;
#endif
        const mem_guard::Rule x = mem_guard::decide(dev.props.vendorID, dev.props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU, windows,
                                                     mem_guard::env_switch(getenv("RX_VK_MEM_GUARD")),
                                                     mem_guard::env_switch(getenv("RX_VK_MEM_GUARD_POOLS")),
                                                     mem_guard::env_switch(getenv("RX_VK_MEM_GUARD_BLOCKS")));
        if (x.on())
            logf("vk: memory guard on (%s): %s not asked of the driver when the heaps the GPU reaches (the device heaps' use counted too) would keep "
                 "less than %llu MB free (half of it for a pool), or the PC less than %llu MB of RAM (twice for a pool)",
                 x.automatic ? "by default, an integrated AMD GPU on Windows" : "by a switch",
                 x.pools && x.blocks ? "a descriptor pool or a memory block" : x.pools ? "a descriptor pool" : "a memory block",
                 (unsigned long long)gtt_headroom_mb(), (unsigned long long)ram_guard_reserve_mb());
        else
            logf("vk: memory guard off (vendor %#x, %s, RX_VK_MEM_GUARD=1 turns it on)", dev.props.vendorID,
                 dev.props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU ? "integrated" : "not integrated");
        return x;
    }();
    return r;
}
bool ram_guard_on() { return rule().on(); }
bool ram_guard_blocks() { return rule().blocks; }
static std::atomic<int64_t> st_draws_left_out{0};
/// a draw left out for want of a descriptor pool the guard refused (vk_draw.cpp)
void ram_guard_draw_left_out() { st_draws_left_out.fetch_add(1, std::memory_order_relaxed); }
/// MB of physical RAM available (free and standby), read at most every 20 ms; UINT64_MAX when unknown
uint64_t ram_avail_mb() {
#ifdef _WIN32
    static std::atomic<uint64_t> at_ms{0}, value{UINT64_MAX};
    const uint64_t now = GetTickCount64();
    if (now - at_ms.load(std::memory_order_relaxed) >= 20) {
        MEMORYSTATUSEX m{};
        m.dwLength = sizeof m;
        if (GlobalMemoryStatusEx(&m)) value.store(m.ullAvailPhys >> 20, std::memory_order_relaxed);
        at_ms.store(now, std::memory_order_relaxed);
    }
    return value.load(std::memory_order_relaxed);
#else
    return UINT64_MAX;
#endif
}
/// the heaps the GPU reaches, MB: the device heaps' use plus the system heaps' use, and the system heaps' budget; read from the driver's
/// count at most every 50 ms (what was allowed since is added by the caller)
static bool heaps_mb(uint64_t* used, uint64_t* limit) {
    static std::atomic<uint64_t> at_ms{0}, u{0}, l{0};
    static std::atomic<bool> ok{false};
    if (!vma_up()) return false;   // (the device's first blocks come before the allocator)
    const uint64_t now = GetTickCount64();
    if (now - at_ms.load(std::memory_order_relaxed) >= 50) {
        at_ms.store(now, std::memory_order_relaxed);
        uint64_t du = 0, db = 0, su = 0, sb = 0;
        const bool a = vram_usage_now(&du, &db), b = system_heap_usage(&su, &sb);
        ok.store(a && b && sb, std::memory_order_relaxed);
        u.store((du + su) >> 20, std::memory_order_relaxed), l.store(sb >> 20, std::memory_order_relaxed);
    }
    *used = u.load(std::memory_order_relaxed), *limit = l.load(std::memory_order_relaxed);
    return ok.load(std::memory_order_relaxed);
}
static std::atomic<int64_t> st_refused_blocks{0}, st_refused_pools{0};
static std::atomic<int64_t> allowed_since{0};   // (MB let through since the heaps' use was read: reset when it is read again)
/// true when asking the driver for need_mb of memory (0: a descriptor pool) would leave it too little
static bool short_of_memory(uint64_t need_mb, bool pool, const char** why) {
    if (const uint64_t r = ram_guard_reserve_mb()) {
        const uint64_t a = ram_avail_mb();
        if (a != UINT64_MAX && a < need_mb + (pool ? 2 * r : r)) return *why = "RAM", true;
    }
    if (const uint64_t h = gtt_headroom_mb()) {
        uint64_t used = 0, limit = 0;
        if (heaps_mb(&used, &limit) && limit) {
            if (used + need_mb + (pool ? h / 2 : h) > limit) return *why = "heaps", true;
        }
    }
    return false;
}
/// a descriptor pool may be made (false: the memory is short: the caller leaves its draw out)
bool ram_guard_pool_ok() {
    const char* why = "";
    if (!rule().pools || !short_of_memory(0, true, &why)) return true;
    const int64_t n = ++st_refused_pools;
    if (n <= 12 || n % 100 == 0)
        logf("vk: memory guard: a descriptor pool not made (%s short; %llu MB of RAM available) (%lld refused, %lld draws left out so far)", why,
             (unsigned long long)ram_avail_mb(), (long long)n, (long long)st_draws_left_out.load());
    vram_alloc_failures.fetch_add(1, std::memory_order_relaxed);
    return false;
}
bool ram_guard_low(uint64_t need_mb, uint64_t reserve_mb) {
    const uint64_t a = ram_avail_mb();
    return a != UINT64_MAX && a < need_mb + reserve_mb;
}
namespace {
PFN_vkAllocateMemory real_alloc;
VkResult VKAPI_CALL guarded_alloc(VkDevice d, const VkMemoryAllocateInfo* i, const VkAllocationCallbacks* cb, VkDeviceMemory* m) {
    bool imported = false;   // (the guest's own memory pinned: nothing new is taken)
    for (const VkBaseInStructure* s = (const VkBaseInStructure*)i->pNext; s; s = s->pNext)
        if (s->sType == VK_STRUCTURE_TYPE_IMPORT_MEMORY_HOST_POINTER_INFO_EXT) imported = true;
    const char* why = "";
    if (rule().blocks && !imported && short_of_memory(i->allocationSize >> 20, false, &why)) {
        const int64_t n = ++st_refused_blocks;
        if (n <= 12 || n % 100 == 0)
            logf("vk: memory guard: a block of %llu MB (type %u) not asked of the driver (%s short; %llu MB of RAM available) (%lld refused)",
                 (unsigned long long)(i->allocationSize >> 20), i->memoryTypeIndex, why, (unsigned long long)ram_avail_mb(), (long long)n);
        vram_alloc_failures.fetch_add(1, std::memory_order_relaxed);
        return VK_ERROR_OUT_OF_DEVICE_MEMORY;
    }
    return real_alloc(d, i, cb, m);
}
}  // namespace
/// the counts, for the periodic report (vk_texture.cpp); false when the guard is off
bool ram_guard_counts(int64_t* pools, int64_t* draws, int64_t* blocks) {
    if (!rule().on()) return false;
    *pools = st_refused_pools.load(), *draws = st_draws_left_out.load(), *blocks = st_refused_blocks.load();
    return true;
}
/// after the device's functions are loaded and the trace's wrappers are in (vk_main.cpp load_device)
void ram_guard_install() {
    if (!rule().blocks || !vkx::vkAllocateMemory) return;
    ram_guard_on();   // (says it)
    real_alloc = vkx::vkAllocateMemory;
    vkx::vkAllocateMemory = guarded_alloc;
}
}  // namespace mkwvk
