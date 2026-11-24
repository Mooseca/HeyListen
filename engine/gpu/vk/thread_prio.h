// Copyright (C) 2026 Sacrappy

// Thread roles and their priorities (RX_VK_THREAD_PRIO). Header only; no Windows header needed beyond what the caller's
// SetThreadPriority / GetCurrentThread come from (vk_internal.h), so that tests/test_thread_prio.py builds it on its own.
//
//   Compile     background shader translation and pipeline builds in play (the jobs workers, the in-play precompile,
//               state list and prediction): below normal, and (Windows) off the logical processors the host keeps for the
//               replay thread (hos_reserved_cpus: one physical core, both its hardware threads). A compile thread on the
//               sibling hardware thread of the replay's core slowed the replay up to 1.7x, and priority does not help there:
//               a lower priority only matters when no processor is free, and the sibling is free.
//   CompileSoft a Compile thread that ran at idle before (the in-play ones, behind the game). Below normal now: idle starved
//               a thread inside the driver's compiler that held the lock a game thread's own build waits on (80 s on the
//               PC 3050, see DriverTurn in vk_draw.cpp). Mode 2 keeps the idle level (the A/B's middle arm).
//   (frame threads: not touched. The replay thread, its workers and the framegen display thread are above normal already, the
//   game's threads, the audio renderer (highest) and the present and completion threads at their own levels. Raising the capture's
//   copy helpers and the hold's thread was measured in TICK-054: +1.2 then -0.5 fps, left off (RX_VK_CAPTURE_PRIO). Nothing is
//   time-critical.)
//
// RX_VK_THREAD_PRIO: 1 (default) the above; 0 every call site keeps the level it had before this change (none set where none
// was); 2 as 1 but CompileSoft stays idle. A job a thread waits for that a below-normal worker is running lifts that worker to
// normal until the job ends (priority inversion, vk_jobs.cpp jobs_wait); not at 0.
// Linux: the same calls go through the Win32 shim, which only lowers (nice values): the raises are no-ops there and nothing
// needs a privilege; the affinity and the lift are Windows only.
#pragma once

#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>

namespace mkwvk::prio {

enum class Role { Compile, CompileSoft };

// (the Win32 levels, spelled here so the pure part below needs no windows.h)
constexpr int kIdle = -15, kLowest = -2, kBelowNormal = -1, kNormal = 0, kAboveNormal = 1;
constexpr int kKeep = 0x7fffffff;   // (a call site that set no priority before: left alone at mode 0)

inline int mode() {
    static const int m = [] {
        const char* e = getenv("RX_VK_THREAD_PRIO");
        return e && *e ? std::clamp(atoi(e), 0, 2) : 1;
    }();
    return m;
}

/// The level a thread of this role gets at this mode; legacy is the level its call site gave it before (kKeep: none)
inline int level(Role r, int m, int legacy) {
    if (m <= 0) return legacy;
    switch (r) {
        case Role::Compile: return kBelowNormal;
        case Role::CompileSoft: return m >= 2 && legacy != kKeep ? legacy : kBelowNormal;
    }
    return legacy;
}

/// The processors a compile thread may use: the process's, without the replay's core; all of them when that leaves none
inline uint64_t compile_mask(uint64_t process, uint64_t reserved) {
    const uint64_t m = process & ~reserved;
    return m ? m : process;
}

// (installed by the renderer's init, Windows: pins the calling thread with compile_mask; and the cross-thread calls the lift needs)
struct Hooks {
    void (*pin_compile)() = nullptr;          // (the calling thread, off the replay's core)
    void* (*self_handle)() = nullptr;         // (a handle to the calling thread other threads may use; null: none)
    void (*set_level)(void*, int) = nullptr;  // (that handle's thread to this level)
    void (*drop_handle)(void*) = nullptr;
    uint64_t pinned_off = 0;                  // (the mask kept free, for the start line)
};
inline Hooks& hooks() {
    static Hooks h;
    return h;
}

inline std::atomic<int>& count_of(Role r) {
    static std::atomic<int> n[2];
    return n[(int)r];
}
inline std::atomic<int>& lifted_total() {
    static std::atomic<int> n;
    return n;
}

/// Sets the calling thread's priority for its role (and, for compile threads, its processors). set(level): the call
/// site's own SetThreadPriority, so that this header needs no Win32 name of its own
template <class SetFn>
inline void apply(Role r, int legacy, SetFn set) {
    const int m = mode();
    const int l = level(r, m, legacy);
    if (l != kKeep) set(l);
    if (m > 0 && (r == Role::Compile || r == Role::CompileSoft) && hooks().pin_compile) hooks().pin_compile();
    count_of(r)++;
}

inline std::string describe() {
    const int m = mode();
    char b[512];
    if (m == 0) {
        std::snprintf(b, sizeof b, "off (RX_VK_THREAD_PRIO=0): every thread keeps the priority its code gave it before");
        return b;
    }
    char where[96] = "on every processor (no core kept for the replay)";
    if (hooks().pinned_off) std::snprintf(where, sizeof where, "kept off logical processors %#llx (the replay's core)", (unsigned long long)hooks().pinned_off);
    std::snprintf(b, sizeof b,
                  "RX_VK_THREAD_PRIO=%d: compile workers below normal (the in-play ones %s), %s; the replay's and game's threads "
                  "as they were; a job a frame waits for lifts its worker to normal",
                  m, m >= 2 ? "stay idle" : "were idle", where);
    return b;
}

} // namespace mkwvk::prio

/// The calling thread's role (a call site: MKWVK_PRIO(Role::Compile, THREAD_PRIORITY_BELOW_NORMAL) or kKeep for none before)
#define MKWVK_PRIO(role, legacy) ::mkwvk::prio::apply((role), (legacy), [](int l_) { SetThreadPriority(GetCurrentThread(), l_); })
