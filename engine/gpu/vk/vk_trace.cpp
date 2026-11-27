// Copyright (C) 2026 Sacrappy

// (HeyListen, LAP2) HOS_VK_TRACE=<file>: every Vulkan call that returns an error is told (the function, the result, what was asked),
// and the memory and device calls (allocations, images, buffers, views, descriptor writes, submits, presents, waits) are written, entered
// and left, to a ring in <file> (a file mapping: what it holds when the process is killed by a driver's fast fail, 0xc0000409, which no
// handler sees, is the calls each thread was in). A sample of the memory (the video heaps' use and budget, the process' commit) goes
// into the ring twice a second. tools: kit/run/vk_trace_read.py. Off unless the switch is set: nothing is wrapped.
#include "vk_internal.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <string>
#include <thread>
#include <type_traits>
#ifdef _WIN32
#include <windows.h>
#endif

namespace mkwvk {
namespace {

struct Entry {   // (48 bytes)
    uint64_t seq;
    uint64_t t_us;
    uint32_t tid;
    uint16_t fn;
    uint8_t phase;   // 0 entered, 1 left, 2 a sample / note
    uint8_t pad;
    int32_t result;
    uint32_t pad2;
    uint64_t a, b;
};
static_assert(sizeof(Entry) == 48, "ring entry");
constexpr uint64_t kEntries = 1ull << 20;

Entry* ring = nullptr;
std::atomic<uint64_t> next_seq{1};
std::atomic<int> errors_told{0};
thread_local int32_t last_err = 0;

const char* kNames[96];
int n_names = 0;

uint64_t now_us() {
    static LARGE_INTEGER f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return x; }();
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (uint64_t)(c.QuadPart * 1000000ull / f.QuadPart);
}
void put(uint16_t fn, uint8_t phase, int32_t result, uint64_t a, uint64_t b) {
    if (!ring) return;
    const uint64_t s = next_seq.fetch_add(1, std::memory_order_relaxed);
    Entry& e = ring[s % kEntries];
    e.t_us = now_us();
    e.tid = GetCurrentThreadId();
    e.fn = fn;
    e.phase = phase;
    e.result = result;
    e.a = a;
    e.b = b;
    std::atomic_thread_fence(std::memory_order_release);
    e.seq = s;   // (written last: a reader skips an entry whose seq is not the one its slot should hold)
}

template <class T> uint64_t av(T x) {
    if constexpr (std::is_pointer_v<T>) return (uint64_t)(uintptr_t)x;
    else if constexpr (std::is_integral_v<T> || std::is_enum_v<T>) return (uint64_t)x;
    else if constexpr (sizeof(T) == 8 && std::is_trivially_copyable_v<T>) { uint64_t v; memcpy(&v, &x, 8); return v; }
    else return 0;
}

void tell_error(int id, VkResult r, uint64_t a, uint64_t b) {
    last_err = (int32_t)r;
    const int n = errors_told.fetch_add(1);
    if (n < 400 || n % 200 == 0)
        logf("vk: ERROR %s returned %d (#%d; first argument %#llx, second %#llx)", kNames[id], (int)r, n + 1, (unsigned long long)a,
             (unsigned long long)b);
}

// a hook per function: the real one kept in the template's own static
template <int Id, class F> struct Hook;
template <int Id, class R, class... A> struct Hook<Id, R(VKAPI_PTR*)(A...)> {
    static inline R(VKAPI_PTR* real)(A...) = nullptr;
    static R VKAPI_CALL call(A... a) {
        uint64_t v[2] = {0, 0};
        int k = 0;
        auto first_two = [&](auto q) { if (k < 2) v[k] = av(q); k++; };
        (first_two(a), ...);
        const uint64_t x = v[0], y = v[1];
        put((uint16_t)Id, 0, 0, x, y);
        if constexpr (std::is_void_v<R>) {
            real(a...);
            put((uint16_t)Id, 1, 0, 0, 0);
        } else {
            R r = real(a...);
            put((uint16_t)Id, 1, (int32_t)r, 0, 0);
            if constexpr (std::is_same_v<R, VkResult>)
                if (r < 0) tell_error(Id, r, x, y);
            return r;
        }
    }
};
enum { kBase = __COUNTER__ };
#define TRACE_ONE(f)                                                                                                      do {                                                                                                                      if (f) {                                                                                                                  constexpr int id = __COUNTER__ - kBase - 1;                                                                          using H = Hook<id, decltype(f)>;                                                                                      kNames[id] = #f;                                                                                                      H::real = f;                                                                                                          f = H::call;                                                                                                          n_names = id + 1;                                                                                                 }                                                                                                                 } while (0)

// the allocation and image calls say what was asked (the first two words of a call are the device and a pointer)
VkResult VKAPI_CALL alloc_hook(VkDevice d, const VkMemoryAllocateInfo* i, const VkAllocationCallbacks* cb, VkDeviceMemory* m);
VkResult VKAPI_CALL image_hook(VkDevice d, const VkImageCreateInfo* i, const VkAllocationCallbacks* cb, VkImage* m);
VkResult VKAPI_CALL buffer_hook(VkDevice d, const VkBufferCreateInfo* i, const VkAllocationCallbacks* cb, VkBuffer* m);
typedef BOOL(WINAPI* GetPmi)(HANDLE, void*, DWORD);
struct Pmc {   // PROCESS_MEMORY_COUNTERS_EX
    DWORD cb, PageFaultCount;
    SIZE_T Peak, Ws, QPP, QP, QNPP, QNP, Pagefile, PeakPagefile, Private;
};
uint64_t private_bytes() {
    static GetPmi get = (GetPmi)(void*)GetProcAddress(GetModuleHandleA("kernel32.dll"), "K32GetProcessMemoryInfo");
    Pmc pm{};
    pm.cb = sizeof pm;
    return get && get(GetCurrentProcess(), &pm, sizeof pm) ? (uint64_t)pm.Private : 0;
}
VkResult VKAPI_CALL pool_hook(VkDevice d, const VkDescriptorPoolCreateInfo* i, const VkAllocationCallbacks* cb, VkDescriptorPool* m);
PFN_vkCreateDescriptorPool real_pool;
int id_pool;
PFN_vkAllocateMemory real_alloc;
PFN_vkCreateImage real_image;
PFN_vkCreateBuffer real_buffer;
int id_alloc, id_image, id_buffer;
VkResult VKAPI_CALL alloc_hook(VkDevice d, const VkMemoryAllocateInfo* i, const VkAllocationCallbacks* cb, VkDeviceMemory* m) {
    const uint64_t size = i->allocationSize, type = i->memoryTypeIndex;
    put((uint16_t)id_alloc, 0, 0, size, type);
    const VkResult r = real_alloc(d, i, cb, m);
    put((uint16_t)id_alloc, 1, (int32_t)r, size, type);
    if (r < 0) tell_error(id_alloc, r, size, type);
    return r;
}
VkResult VKAPI_CALL image_hook(VkDevice d, const VkImageCreateInfo* i, const VkAllocationCallbacks* cb, VkImage* m) {
    const uint64_t wh = ((uint64_t)i->extent.width << 32) | i->extent.height, fmt = ((uint64_t)i->format << 32) | i->usage;
    put((uint16_t)id_image, 0, 0, wh, fmt);
    const VkResult r = real_image(d, i, cb, m);
    put((uint16_t)id_image, 1, (int32_t)r, wh, fmt);
    if (r < 0) tell_error(id_image, r, wh, fmt);
    return r;
}
// a descriptor pool: what it asked for, and what the process' private bytes grew by across the call (the driver's host memory for it)
VkResult VKAPI_CALL pool_hook(VkDevice d, const VkDescriptorPoolCreateInfo* i, const VkAllocationCallbacks* cb, VkDescriptorPool* m) {
    uint64_t descs = 0;
    for (uint32_t k = 0; k < i->poolSizeCount; k++) descs += i->pPoolSizes[k].descriptorCount;
    put((uint16_t)id_pool, 0, 0, i->maxSets, descs);
    const uint64_t before = private_bytes();
    uint64_t dev0 = 0, dev1 = 0, sys0 = 0, sys1 = 0, bud = 0;
    vram_usage_now(&dev0, &bud);
    system_heap_usage(&sys0, &bud);
    const uint64_t t0 = now_us();
    const VkResult r = real_pool(d, i, cb, m);
    const uint64_t grew = private_bytes() - std::min(private_bytes(), before);
    vram_usage_now(&dev1, &bud);
    system_heap_usage(&sys1, &bud);
    put((uint16_t)id_pool, 1, (int32_t)r, i->maxSets, descs);
    put(1510, 2, (int32_t)r, grew >> 10, now_us() - t0);   // (KB the process grew by, microseconds)
    static std::atomic<int> told{0};
    if (told++ < 40 || grew > (16ull << 20))
        logf("vk: descriptor pool of %u sets, %llu descriptors: %lld KB of private memory in %llu us (result %d); the driver's count of the "
             "device heaps %+lld KB, of the system heaps %+lld KB", i->maxSets, (unsigned long long)descs, (long long)(grew >> 10),
             (unsigned long long)(now_us() - t0), (int)r, (long long)((int64_t)(dev1 - dev0) >> 10), (long long)((int64_t)(sys1 - sys0) >> 10));
    if (r < 0) tell_error(id_pool, r, i->maxSets, descs);
    return r;
}
VkResult VKAPI_CALL buffer_hook(VkDevice d, const VkBufferCreateInfo* i, const VkAllocationCallbacks* cb, VkBuffer* m) {
    put((uint16_t)id_buffer, 0, 0, i->size, i->usage);
    const VkResult r = real_buffer(d, i, cb, m);
    put((uint16_t)id_buffer, 1, (int32_t)r, i->size, i->usage);
    if (r < 0) tell_error(id_buffer, r, i->size, i->usage);
    return r;
}

void sampler() {
    GetPmi get = (GetPmi)(void*)GetProcAddress(GetModuleHandleA("kernel32.dll"), "K32GetProcessMemoryInfo");
    for (;;) {
        Sleep(500);
        uint64_t used = 0, budget = 0, sused = 0, sbudget = 0;
        vram_usage_now(&used, &budget);
        system_heap_usage(&sused, &sbudget);
        Pmc pm{};
        pm.cb = sizeof pm;
        if (get) get(GetCurrentProcess(), &pm, sizeof pm);
        MEMORYSTATUSEX ms{};
        ms.dwLength = sizeof ms;
        GlobalMemoryStatusEx(&ms);
        // (a sample is three entries: the video heaps (MB used, MB allowed), the system heaps the GPU reaches, the process (MB private
        // commit, working set) and the machine (MB of commit left, MB of RAM free))
        put(1000, 2, 0, used >> 20, budget >> 20);
        put(1001, 2, 0, sused >> 20, sbudget >> 20);
        put(1002, 2, 0, (uint64_t)pm.Private >> 20, (uint64_t)pm.Ws >> 20);
        put(1003, 2, 0, ms.ullAvailPageFile >> 20, ms.ullAvailPhys >> 20);
    }
}

}  // namespace

int32_t trace_last_error() { return last_err; }
void trace_note(uint16_t what, uint64_t a, uint64_t b) { put(what, 2, 0, a, b); }

/// installed once the device functions are loaded (vk_main.cpp load_device); the VMA's functions are the wrapped ones too (vk_vma.cpp)
void vk_trace_install() {
    const char* path = getenv("HOS_VK_TRACE");
    if (!path || !*path || ring) return;
#ifdef _WIN32
    HANDLE f = CreateFileA(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) { logf("vk trace: %s could not be made", path); return; }
    const uint64_t bytes = kEntries * sizeof(Entry);
    HANDLE m = CreateFileMappingA(f, nullptr, PAGE_READWRITE, (DWORD)(bytes >> 32), (DWORD)bytes, nullptr);
    void* v = m ? MapViewOfFile(m, FILE_MAP_ALL_ACCESS, 0, 0, 0) : nullptr;
    if (!v) { logf("vk trace: %s could not be mapped", path); return; }
#else   // (the ring is a Windows file mapping, and the crash it is for is AMD's Windows driver's: the Linux build's Windows layer has no
        // file mappings, so there the switch only says so)
    logf("vk trace: HOS_VK_TRACE is for Windows builds; nothing is wrapped here");
    return;
    void* v = nullptr;
    const uint64_t bytes = 0;
#endif
    ring = (Entry*)v;
    memset(ring, 0, bytes);
    using namespace vkx;
    {
        constexpr int id = __COUNTER__ - kBase - 1;
        real_alloc = vkAllocateMemory, id_alloc = id, kNames[id] = "vkAllocateMemory", vkAllocateMemory = alloc_hook, n_names = id + 1;
    }
    {
        constexpr int id = __COUNTER__ - kBase - 1;
        real_image = vkCreateImage, id_image = id, kNames[id] = "vkCreateImage", vkCreateImage = image_hook, n_names = id + 1;
    }
    {
        constexpr int id = __COUNTER__ - kBase - 1;
        real_buffer = vkCreateBuffer, id_buffer = id, kNames[id] = "vkCreateBuffer", vkCreateBuffer = buffer_hook, n_names = id + 1;
    }
    {
        constexpr int id = __COUNTER__ - kBase - 1;
        real_pool = vkCreateDescriptorPool, id_pool = id, kNames[id] = "vkCreateDescriptorPool", vkCreateDescriptorPool = pool_hook, n_names = id + 1;
    }
    TRACE_ONE(vkFreeMemory);
    TRACE_ONE(vkDestroyImage);
    TRACE_ONE(vkDestroyBuffer);
    TRACE_ONE(vkBindImageMemory);
    TRACE_ONE(vkBindBufferMemory);
    TRACE_ONE(vkMapMemory);
    TRACE_ONE(vkCreateImageView);
    TRACE_ONE(vkDestroyImageView);
    TRACE_ONE(vkCreateBufferView);
    TRACE_ONE(vkQueueSubmit2);
    TRACE_ONE(vkQueueBindSparse);
    TRACE_ONE(vkQueuePresentKHR);
    TRACE_ONE(vkAcquireNextImageKHR);
    TRACE_ONE(vkAllocateDescriptorSets);
    TRACE_ONE(vkUpdateDescriptorSets);
    TRACE_ONE(vkResetDescriptorPool);
    TRACE_ONE(vkCreateGraphicsPipelines);
    TRACE_ONE(vkCreateComputePipelines);
    TRACE_ONE(vkCreateSampler);
    TRACE_ONE(vkBeginCommandBuffer);
    TRACE_ONE(vkEndCommandBuffer);
    TRACE_ONE(vkResetCommandPool);
    TRACE_ONE(vkWaitSemaphores);
    TRACE_ONE(vkWaitForFences);
    TRACE_ONE(vkQueueWaitIdle);
    TRACE_ONE(vkDeviceWaitIdle);
    TRACE_ONE(vkCreateSwapchainKHR);
    logf("vk trace: %d Vulkan functions wrapped, the ring (%llu entries) in %s; errors are told as \"vk: ERROR ...\"", n_names,
         (unsigned long long)kEntries, path);
    {   // (the names, for the reader: <file>.names, one a line, the ring's function numbers)
        std::string names = std::string(path) + ".names";
        if (FILE* nf = fopen(names.c_str(), "w")) {
            for (int i = 0; i < n_names; i++) fprintf(nf, "%d %s\n", i, kNames[i] ? kNames[i] : "?");
            fclose(nf);
        }
    }
}

/// the memory sampler, once the allocator exists (vk_vma.cpp vma_init)
void vk_trace_sampler() {
    static bool once = false;
    if (!ring || once) return;
    once = true;
    std::thread(sampler).detach();
}

}  // namespace mkwvk
