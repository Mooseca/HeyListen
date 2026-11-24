// Copyright (C) 2026 Sacrappy

// thread_prio.h (RX_VK_THREAD_PRIO) and the jobs queue's lift of a waited-for job's worker (gpu/vk/vk_jobs.cpp jobs_wait).
// Built beside stand-ins for the renderer's headers (tests/test_thread_prio.py). Run with RX_VK_WORKERS=1 RX_VK_STORM_WORKERS=0
// RX_VK_JOB_STEAL=1 and the mode in RX_VK_THREAD_PRIO (argv[1] is the mode the run expects: 0, 1 or 2).
#include "vk_jobs.h"
#include "thread_prio.h"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>

using namespace mkwvk;

namespace {
int failures = 0;
void expect(bool ok, const char* what) {
    if (!ok) std::printf("FAIL: %s\n", what), failures++;
}
std::mutex mu;
std::condition_variable cv;
bool gate_open = false, gate_held = false;
std::vector<int> levels_set;   // (SetThreadPriority's calls, noted by the stand-in)
std::vector<int> lifted_to;    // (the hook's set_level calls)
std::atomic<int> pins{0};
}  // namespace

namespace stub {
void note_level(int l) {
    std::lock_guard lk(mu);
    levels_set.push_back(l);
}
}  // namespace stub

int main(int argc, char** argv) {
    const int m = argc > 1 ? std::atoi(argv[1]) : 1;
    expect(prio::mode() == m, "mode() reads RX_VK_THREAD_PRIO");
    using R = prio::Role;
    expect(prio::level(R::Compile, 0, prio::kKeep) == prio::kKeep, "off: a site that set nothing sets nothing");
    expect(prio::level(R::CompileSoft, 0, prio::kIdle) == prio::kIdle, "off: the in-play compile stays idle");
    expect(prio::level(R::Compile, 1, prio::kBelowNormal) == prio::kBelowNormal, "on: compile below normal");
    expect(prio::level(R::CompileSoft, 1, prio::kIdle) == prio::kBelowNormal, "on: the in-play compile below normal, not idle");
    expect(prio::level(R::CompileSoft, 2, prio::kIdle) == prio::kIdle, "mode 2: the in-play compile stays idle");
    for (int mm = 0; mm <= 2; mm++)
        for (R r : {R::Compile, R::CompileSoft}) {
            const int l = prio::level(r, mm, prio::kIdle);
            expect(l != 15 && l <= prio::kNormal, "nothing is raised above normal or to time-critical");
        }
    expect(prio::compile_mask(0xFFF, 0xC00) == 0x3FF, "compile threads leave the replay's core out");
    expect(prio::compile_mask(0xC00, 0xC00) == 0xC00, "all of them when that leaves none");
    expect(prio::compile_mask(0xFF, 0) == 0xFF, "no core kept: all of them");
    prio::Hooks& hk = prio::hooks();
    hk.pin_compile = [] { pins++; };
    hk.self_handle = []() -> void* { return (void*)0x1234; };
    hk.set_level = [](void* h, int l) {
        std::lock_guard lk(mu);
        if (h == (void*)0x1234) lifted_to.push_back(l);
    };
    std::atomic<bool> a_done{false};
    // job A holds the one worker; a thread waits for it: the worker is lifted to normal, and goes back after the job
    jobs_push([&] {
        std::unique_lock lk(mu);
        gate_held = true;
        cv.notify_all();
        cv.wait(lk, [] { return gate_open; });
        a_done.store(true, std::memory_order_release);
        jobs_notify();
    }, false, &a_done);
    {
        std::unique_lock lk(mu);
        cv.wait_for(lk, std::chrono::seconds(5), [] { return gate_held; });
        expect(gate_held, "the worker took job A");
    }
    std::thread waiter([&] { jobs_wait(a_done); });
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    {
        std::lock_guard lk(mu);
        if (m > 0) expect(lifted_to.size() == 1 && lifted_to[0] == prio::kNormal, "a waited-for running job lifts its worker to normal");
        else expect(lifted_to.empty(), "off: nothing is lifted");
        gate_open = true;
    }
    cv.notify_all();
    waiter.join();
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    {
        std::lock_guard lk(mu);
        if (m > 0) {
            expect(levels_set.size() >= 2 && levels_set.back() == prio::kBelowNormal, "the worker goes back below normal after the job");
            expect(pins.load() >= 1, "a compile worker is pinned off the replay's core");
        } else {
            expect(levels_set.size() == 1 && levels_set[0] == prio::kBelowNormal, "off: the worker's one call is the old one");
            expect(pins.load() == 0, "off: no pin");
        }
    }
    // a job nobody waits for lifts nothing
    std::atomic<bool> c_done{false};
    size_t before;
    {
        std::lock_guard lk(mu);
        before = lifted_to.size();
    }
    jobs_push([&] { c_done.store(true, std::memory_order_release); jobs_notify(); }, false, &c_done);
    for (int i = 0; i < 100 && !c_done.load(); i++) std::this_thread::sleep_for(std::chrono::milliseconds(20));
    {
        std::lock_guard lk(mu);
        expect(c_done.load() && lifted_to.size() == before, "an unwaited job does not lift");
    }
    expect(prio::describe().find("RX_VK_THREAD_PRIO") != std::string::npos, "the start line names the switch");
    if (!failures) std::printf("ok\n");
    return failures != 0;
}
