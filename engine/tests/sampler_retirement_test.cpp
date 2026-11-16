// The renderer's sampler cache (gpu/vk/vk_draw.cpp, "samplers" section) against a modeled driver that makes only 80 samplers and a
// modeled GPU timeline. The section's own code is cut out of the source by tests/test_sampler_retirement.py and placed below;
// nothing here is a copy of it.
//
// What each case holds:
//   limit        300 recordings; each draws with 10 samplers every recording uses and a window of 20 that moves 5 a recording
//                (1,525 samplers in all), the GPU 2 recordings behind. No draw is refused, every handle given out is alive, each
//                sampler is destroyed only once the GPU has passed the last recording that drew with it, at most the room
//                (80 - 20 = 60) are alive, and the table after a retirement never gives out a retired handle (sampler_for's
//                table, the thread's own `mine`, and the slot stamp a texture slot keeps).
//   limit-full   the GPU stopped: nothing is made past the room and nothing the GPU may still use is destroyed; once it goes on,
//                the retired are destroyed and the draw that waited is served
//   limit-reuse  keys apart only in what no sample reaches share one sampler; a comparison or a border colour that is reached does not
//   limit-threads  two threads recording at once (joined before the recording's signal, as the parallel replay's workers are)
//   below        under 3/4 of the room nothing is retired or destroyed
//   counts       sampler_counts' numbers follow made, retired and destroyed
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <set>
#include <string>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include <vulkan/vulkan.h>

/* PARAMS */
/* ENUMS */

#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "check failed: %s (line %d)\n", #c, __LINE__); std::abort(); } } while (0)

namespace mkwvk {

// ---- the modeled driver and timeline ----
struct { VkDevice device = (VkDevice)(uintptr_t)1; VkPhysicalDeviceProperties props{}; VkPhysicalDeviceFeatures features{};
         bool custom_border_color = true; } dev;
std::mutex model_mu;
std::unordered_map<uint64_t, uint64_t> live;   // (handle -> the newest recording that drew with it; 0: none yet)
uint64_t next_handle = 0x1000, creates = 0, destroys = 0, signaled = 0, completed = 0, frame = 1, gen = 1, lag = 2;
bool gpu_stopped = false;
size_t max_alive = 0;
std::vector<std::string> lines;

void logf(const char* f, ...) __attribute__((format(printf, 1, 2)));
void logf(const char* f, ...) {
    va_list a;
    va_start(a, f);
    char buf[512];
    std::vsnprintf(buf, sizeof buf, f, a);
    va_end(a);
    lines.push_back(buf);
}
struct ParLock {
    std::unique_lock<std::recursive_mutex> l;
    explicit ParLock(bool = true) : l(mu()) {}
    static std::recursive_mutex& mu() { static std::recursive_mutex m; return m; }
};
uint64_t texture_frame_no() { return frame; }
uint64_t vk_retirement_value() { return signaled + 1; }
uint64_t vk_timeline_reached() { return completed; }
uint64_t sampler_registrations_generation() { return gen; }
void samplers_changed() { gen++; }
bool sampler_cache_on() { return false; }
uint32_t sampler_slot_version(int) { return 0; }
std::vector<nvn_samp_par> regs(4096);
bool sampler_of(int id, nvn_samp_par* p) { *p = regs[(size_t)id]; return true; }

VkResult vkCreateSampler(VkDevice, const VkSamplerCreateInfo*, const VkAllocationCallbacks*, VkSampler* out) {
    std::lock_guard g(model_mu);
    if (live.size() >= dev.props.limits.maxSamplerAllocationCount) return VK_ERROR_TOO_MANY_OBJECTS;
    const uint64_t h = next_handle++;
    live[h] = 0;
    creates++;
    max_alive = std::max(max_alive, live.size());
    *out = (VkSampler)(uintptr_t)h;
    return VK_SUCCESS;
}
void vkDestroySampler(VkDevice, VkSampler s, const VkAllocationCallbacks*) {
    std::lock_guard g(model_mu);
    auto it = live.find((uint64_t)(uintptr_t)s);
    CHECK(it != live.end());                // (a handle destroyed twice, or never made)
    CHECK(it->second <= completed);         // (the GPU has passed the last recording that drew with it)
    live.erase(it);
    destroys++;
}

inline uint64_t mix(uint64_t h, uint64_t v) {
    h ^= v + 0x9e3779b97f4a7c15ull + (h << 6) + (h >> 2);
    return h * 0xff51afd7ed558ccdull;
}

namespace {
VkSampler sampler_make(int id, bool compare);
/* ACTUAL */
}

// ---- the cases ----
uint64_t recording = 0;   // (the recording being made: its value is recording, the signal after it)

/// A draw's sampler for id, as a texture slot would take it: through sampler_for (or sampler_make), the handle checked alive and
/// marked as drawn with in this recording
bool route_make = false;
VkSampler draw_with(int id, bool compare = false) {
    const VkSampler s = route_make ? sampler_make(id, compare) : sampler_for(id, compare);
    if (!s) return s;
    std::lock_guard g(model_mu);
    auto it = live.find((uint64_t)(uintptr_t)s);
    CHECK(it != live.end());   // (a destroyed handle given out)
    it->second = recording;
    return s;
}
void register_id(int id, int variant) {
    nvn_samp_par p{};
    p.minf = NVN_MIN_FILTER_LINEAR, p.magf = NVN_MAG_FILTER_LINEAR;
    p.ws = p.wt = p.wr = NVN_WRAP_MODE_REPEAT;
    p.lod_max = 1000.0f;
    p.lod_bias = (float)variant * 0.015625f;   // (a bias apart: a sampler of its own)
    regs[(size_t)id] = p;
    gen++;
}
void begin_recording() { recording++; }
void end_recording() {   // (the signal after the recording; the GPU reaches it `lag` recordings later)
    signaled = recording;
    if (!gpu_stopped) completed = recording > lag ? recording - lag : 0;
    frame++;
}
size_t room() { return dev.props.limits.maxSamplerAllocationCount - std::min<uint64_t>(64, dev.props.limits.maxSamplerAllocationCount / 4); }

int run(const std::string& route, const std::string& name) {
    route_make = route == "make";
    dev.props.limits.maxSamplerAllocationCount = 80;
    dev.props.limits.maxSamplerLodBias = 100.0f;
    dev.props.limits.maxSamplerAnisotropy = 16.0f;
    dev.features.samplerAnisotropy = VK_FALSE;
    lag = 2;
    if (name == "limit") {
        std::set<uint64_t> handles;
        for (int rec = 0; rec < 300; rec++) {
            begin_recording();
            std::vector<int> ids;
            for (int k = 0; k < 10; k++) ids.push_back(k);                          // (every recording's)
            for (int k = 0; k < 20; k++) ids.push_back(100 + rec * 5 + k);          // (the window that moves)
            for (const int id : ids) {
                if (regs[(size_t)id].lod_max == 0.0f) register_id(id, id);
            }
            for (const int id : ids) {
                const VkSampler s = draw_with(id);
                CHECK(s != VK_NULL_HANDLE);   // (no draw refused)
                handles.insert((uint64_t)(uintptr_t)s);
            }
            end_recording();
            CHECK(live.size() <= room());
        }
        CHECK(creates == 10 + 20 + 299 * 5);   // (each made once: 1,525)
        CHECK(max_alive <= room());
        CHECK(destroys > 1000);
        CHECK(creates - destroys == live.size());
        // the first retirement and the periodic ones are said
        bool said = false;
        for (const auto& l : lines) said |= l.find("vk: samplers:") == 0 && l.find("retired") != std::string::npos;
        CHECK(said);
        return 0;
    }
    if (name == "limit-full") {
        gpu_stopped = true;
        const size_t r = room();
        begin_recording();
        for (size_t k = 0; k < r; k++) {
            register_id((int)k, (int)k);
            CHECK(draw_with((int)k) != VK_NULL_HANDLE);
        }
        end_recording();
        // 3/4 of the room kept: the rest were retired as more were made; the GPU is stopped, so none of those may go
        const size_t before = creates;
        uint64_t refused_at = 0;
        for (int rec = 0; rec < 5; rec++) {
            begin_recording();
            for (size_t k = r; k < r + 40; k++) {
                register_id((int)k, (int)k);
                if (!draw_with((int)k) && !refused_at) refused_at = k;
            }
            end_recording();
        }
        CHECK(destroys == 0);                      // (nothing the GPU may still use is destroyed)
        CHECK(live.size() <= dev.props.limits.maxSamplerAllocationCount);
        CHECK(creates - before <= (uint64_t)(room() - 0));
        CHECK(refused_at != 0);                    // (the room filled: a draw waited for a later present, not an overrun)
        CHECK(live.size() == room());              // (none made past the room)
        // the GPU goes on: the retired are destroyed, and the key that waited is served at a later present
        gpu_stopped = false;
        completed = signaled;
        begin_recording();
        const int waiting = (int)refused_at;
        CHECK(draw_with(waiting) != VK_NULL_HANDLE);
        end_recording();
        CHECK(destroys > 0);
        CHECK(live.size() <= room());
        return 0;
    }
    if (name == "limit-reuse") {
        // keys apart only in what no sample reaches: the anisotropy of a sampler that filters without it (the feature is off here),
        // so these share one sampler
        register_id(1, 0);
        register_id(2, 0);
        register_id(3, 0);
        regs[2].aniso = 8.0f;
        regs[3].aniso = 16.0f;
        begin_recording();
        const VkSampler a = draw_with(1), b = draw_with(2), c = draw_with(3);
        CHECK(a && a == b && b == c);
        CHECK(creates == 1);
        // a comparison the shader asks for is reached: its sampler is its own
        const VkSampler d = draw_with(1, true);
        CHECK(d && d != a);
        CHECK(creates == 2);
        // a border colour that is clamped to is reached, one that is not, is not
        register_id(4, 0);
        regs[4].border[3] = 1.0f;                  // (opaque black: no address mode clamps to the border here)
        CHECK(draw_with(4) == a);
        register_id(5, 0);
        regs[5].ws = NVN_WRAP_MODE_CLAMP_TO_BORDER;
        const VkSampler e = draw_with(5);
        CHECK(e && e != a);
        regs[5].border[3] = 1.0f, gen++;
        const VkSampler f = draw_with(5);
        CHECK(f && f != e);
        end_recording();
        return 0;
    }
    if (name == "below") {
        for (int rec = 0; rec < 10; rec++) {
            begin_recording();
            for (int k = 0; k < 4; k++) {
                register_id(rec * 4 + k, rec * 4 + k);
                CHECK(draw_with(rec * 4 + k));
            }
            end_recording();
        }
        CHECK(creates == 40);       // (40 of the room 60: 3/4 of it is 45)
        CHECK(destroys == 0);
        for (const auto& l : lines) CHECK(l.find("vk: samplers:") != 0);
        return 0;
    }
    if (name == "counts") {
        for (int rec = 0; rec < 60; rec++) {
            begin_recording();
            for (int k = 0; k < 5; k++) {
                register_id(rec * 5 + k, rec * 5 + k);
                CHECK(draw_with(rec * 5 + k));
            }
            end_recording();
        }
        uint32_t made = 0, waiting = 0, limit = 0;
        uint64_t retired = 0, destroyed = 0;
        sampler_counts_read(&made, &waiting, &retired, &destroyed, &limit);
        CHECK(limit == 80);
        CHECK(retired > 0 && destroyed > 0 && destroyed <= retired);
        {
            std::lock_guard g(model_mu);
            CHECK(made + waiting == live.size());
            CHECK(destroyed == destroys);
        }
        return 0;
    }
    if (name == "limit-threads") {
        // two threads draw in each recording and are joined before its signal; a retirement by one is seen by the other's tables
        for (int rec = 0; rec < 200; rec++) {
            begin_recording();
            for (int k = 0; k < 40; k++)
                if (regs[(size_t)(rec * 3 + k)].lod_max == 0.0f) register_id(rec * 3 + k, rec * 3 + k);
            std::atomic<int> refused{0};
            auto work = [&](int offset) {
                for (int k = offset; k < 40; k += 2) {
                    const VkSampler s = draw_with(rec * 3 + k);
                    if (!s) refused++;
                }
                for (int k = 0; k < 8; k++) if (!draw_with(k * 400 / 8 + 3000 + rec % 2)) refused++;   // (the tables' hits)
            };
            std::thread t1(work, 0), t2(work, 1);
            t1.join(), t2.join();
            CHECK(refused == 0);
            end_recording();
            CHECK(live.size() <= room());
        }
        CHECK(destroys > 100);
        return 0;
    }
    std::fprintf(stderr, "unknown case %s\n", name.c_str());
    return 2;
}
}   // namespace mkwvk

int main(int argc, char** argv) {
    if (argc != 3) return 2;
    return mkwvk::run(argv[1], argv[2]);
}
