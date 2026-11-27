// Copyright (C) 2026 Sacrappy
// The parallel replay's workers and the CPU's cores (vk_replay.cpp par_worker_ideal, RX_VK_PARALLEL_IDEAL): which logical
// processor each recording worker gets as its ideal processor (a hint to the scheduler, not an affinity).
// tests/test_par_ideal_rule.py
#pragma once
#include <algorithm>
#include <cstdint>
#include <vector>

namespace par_ideal_rule {

/// One physical core: its first logical processor and its efficiency class (Windows' EfficiencyClass: the higher, the faster
/// the core; all equal on a CPU with one kind of core)
struct Core {
    int first_cpu = 0;
    int efficiency = 0;
};

/// The workers' ideal processors, one a worker, or nothing (leave the scheduler alone).
/// Two recorders on one core's two hardware threads share its caches and units, so each worker is given a physical core of its
/// own: the fastest kind only (a hybrid CPU's small cores are not asked for), the first of them left to the game's main thread
/// and the one the host keeps for the replay thread (`reserved`: hos_reserved_cpus' mask, 0 for none) left to it.
/// `mode`: -1 the switch is not set (the default), 0 off, 1 asked for.
/// By default nothing is done unless every worker gets a core of its own: with fewer cores than workers two workers would be
/// sent to one core, which is worse than no hint. Asked for (1), the cores are shared out in turn as before.
inline std::vector<int> ideal_cpus(const std::vector<Core>& cores, uint64_t reserved, int workers, int mode) {
    if (mode == 0 || workers <= 0 || cores.empty()) return {};
    int top = cores[0].efficiency;
    for (const Core& c : cores) top = std::max(top, c.efficiency);
    std::vector<int> fast;
    for (const Core& c : cores)
        if (c.efficiency == top && !(c.first_cpu < 64 && (reserved >> c.first_cpu & 1))) fast.push_back(c.first_cpu);
    std::sort(fast.begin(), fast.end());
    if (fast.size() < 2) return {};
    const int spare = (int)fast.size() - 1;   // (the first fast core stays the game's)
    if (mode < 0 && spare < workers) return {};
    std::vector<int> out;
    for (int i = 0; i < workers; i++) out.push_back(fast[1 + i % spare]);
    return out;
}

}   // namespace par_ideal_rule
