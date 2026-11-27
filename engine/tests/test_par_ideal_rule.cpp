// Copyright (C) 2026 Sacrappy
// par_ideal_rule (gpu/vk/par_ideal_rule.h): the recording workers' ideal processors.
// tests/test_par_ideal_rule.py
#include "../gpu/vk/par_ideal_rule.h"

#include <cstdio>
#include <vector>

static int failures = 0;
static void expect(bool ok, const char* what) {
    if (!ok) {
        std::printf("FAIL: %s\n", what);
        failures++;
    }
}
using par_ideal_rule::Core;
using par_ideal_rule::ideal_cpus;
typedef std::vector<int> V;

/// n cores of one kind with `smt` hardware threads each
static std::vector<Core> plain(int n, int smt) {
    std::vector<Core> c;
    for (int i = 0; i < n; i++) c.push_back({i * smt, 0});
    return c;
}

int main() {
    // 6 cores / 12 threads (i5-10400F), the last core kept for the replay thread, 4 workers: the measured placing
    expect(ideal_cpus(plain(6, 2), 3ull << 10, 4, -1) == V({2, 4, 6, 8}), "6c/12t by default: 2 4 6 8");
    expect(ideal_cpus(plain(6, 2), 3ull << 10, 4, 1) == V({2, 4, 6, 8}), "6c/12t asked for: the same");
    expect(ideal_cpus(plain(6, 2), 3ull << 10, 4, 0).empty(), "0: off");
    // 8 cores / 16 threads (Ryzen 7 5700U, 7800X3D), the last kept, 5 workers
    expect(ideal_cpus(plain(8, 2), 3ull << 14, 5, -1) == V({2, 4, 6, 8, 10}), "8c/16t by default: 2 4 6 8 10");
    // 8 cores without hardware threads, 4 workers
    expect(ideal_cpus(plain(8, 1), 1ull << 7, 4, -1) == V({1, 2, 3, 4}), "8c/8t by default: 1 2 3 4");
    // 4 cores / 8 threads: the first is the game's, the last the replay's, two left for 4 workers: nothing by default
    expect(ideal_cpus(plain(4, 2), 3ull << 6, 4, -1).empty(), "4c/8t by default: no hint (two workers would share a core)");
    expect(ideal_cpus(plain(4, 2), 3ull << 6, 4, 1) == V({2, 4, 2, 4}), "4c/8t asked for: in turn");
    // no core kept (HOS_RESERVE_CORE=0): the last core is a worker's too
    expect(ideal_cpus(plain(4, 2), 0, 3, -1) == V({2, 4, 6}), "no reserved core: the last one counts");
    // a hybrid CPU: 6 fast cores with two threads (0-11) and 4 small ones (12-15), the last fast core kept, 5 workers:
    // four fast cores are free, so nothing by default, and the small cores are never asked for
    std::vector<Core> hybrid;
    for (int i = 0; i < 6; i++) hybrid.push_back({i * 2, 1});
    for (int i = 0; i < 4; i++) hybrid.push_back({12 + i, 0});
    expect(ideal_cpus(hybrid, 3ull << 10, 5, -1).empty(), "6P+4E, 5 workers, by default: no hint");
    expect(ideal_cpus(hybrid, 3ull << 10, 5, 1) == V({2, 4, 6, 8, 2}), "6P+4E asked for: fast cores only");
    expect(ideal_cpus(hybrid, 3ull << 10, 4, -1) == V({2, 4, 6, 8}), "6P+4E, 4 workers: a fast core each");
    // 2 fast cores and 8 small ones (i5-1235U): one fast core free at most
    std::vector<Core> u;
    u.push_back({0, 1});
    u.push_back({2, 1});
    for (int i = 0; i < 8; i++) u.push_back({4 + i, 0});
    expect(ideal_cpus(u, 0, 4, -1).empty(), "2P+8E by default: no hint");
    expect(ideal_cpus(u, 0, 4, 1) == V({2, 2, 2, 2}), "2P+8E asked for: the one free fast core");
    // the cores in any order; one core, no core, no worker
    std::vector<Core> rev = plain(6, 2);
    std::vector<Core> back(rev.rbegin(), rev.rend());
    expect(ideal_cpus(back, 3ull << 10, 4, -1) == V({2, 4, 6, 8}), "the cores' order does not matter");
    expect(ideal_cpus(plain(1, 2), 0, 4, 1).empty(), "one core: nothing");
    expect(ideal_cpus({}, 0, 4, 1).empty(), "no core read: nothing");
    expect(ideal_cpus(plain(8, 2), 0, 0, -1).empty(), "no worker: nothing");
    // a first logical processor past 63 (another group's numbering) is never taken for the reserved one
    std::vector<Core> wide = plain(4, 2);
    wide.push_back({64, 0});
    expect(ideal_cpus(wide, 0, 4, -1) == V({2, 4, 6, 64}), "a processor number past 63 does not shift out of range");
    if (failures) return 1;
    std::printf("PASS par ideal rule\n");
    return 0;
}
