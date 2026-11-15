"""RX_VK_TL's GPU side on Linux: the host time domain it calibrates against (gpu/vk/vk_tl_clock.h).

tl_gpu_dump (gpu/vk/vk_replay.cpp) maps the GPU's timestamps onto the timeline's clock (std::chrono::steady_clock) through
QueryPerformanceCounter. On Windows that is VK_TIME_DOMAIN_QUERY_PERFORMANCE_COUNTER_EXT; on Linux the shim's
QueryPerformanceCounter is CLOCK_MONOTONIC in ns at 1e9 (host/posix/windows.h), so the domain is CLOCK_MONOTONIC, and the QPC
domain (Windows-only: Mesa fails the whole vkGetCalibratedTimestampsEXT call for it) left the Linux timeline without its GPU
lines. Compiles the header with the Vulkan headers and runs it (the domain, the device's list checked as RADV and a driver
without the domain give it; the Windows branch is read, as the Vulkan headers do not take _WIN32 on Linux), checks that
steady_clock and CLOCK_MONOTONIC are one clock here, and reads the sources for the wiring: tl_gpu_dump asks for that domain,
and vk_main.cpp turns the GPU side off (Linux only) when the device lacks it.
No GPU.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu" / "vk"

FIXTURE = r'''
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan_core.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <string_view>
#include "vk_tl_clock.h"
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); std::exit(1); } } while (0)
using namespace mkwvk;
int main() {
#ifdef _WIN32
    CHECK(tl_host_time_domain() == VK_TIME_DOMAIN_QUERY_PERFORMANCE_COUNTER_EXT);
    std::puts("domain QUERY_PERFORMANCE_COUNTER");
#else
    CHECK(tl_host_time_domain() == VK_TIME_DOMAIN_CLOCK_MONOTONIC_EXT);
    const VkTimeDomainEXT radv[] = {VK_TIME_DOMAIN_DEVICE_EXT, VK_TIME_DOMAIN_CLOCK_MONOTONIC_EXT, VK_TIME_DOMAIN_CLOCK_MONOTONIC_RAW_EXT};
    CHECK(tl_time_domains_usable(radv, 3));
    const VkTimeDomainEXT raw_only[] = {VK_TIME_DOMAIN_DEVICE_EXT, VK_TIME_DOMAIN_CLOCK_MONOTONIC_RAW_EXT};
    CHECK(!tl_time_domains_usable(raw_only, 2));
    const VkTimeDomainEXT qpc[] = {VK_TIME_DOMAIN_DEVICE_EXT, VK_TIME_DOMAIN_QUERY_PERFORMANCE_COUNTER_EXT};
    CHECK(!tl_time_domains_usable(qpc, 2));
    const VkTimeDomainEXT host_only[] = {VK_TIME_DOMAIN_CLOCK_MONOTONIC_EXT};
    CHECK(!tl_time_domains_usable(host_only, 1));
    CHECK(!tl_time_domains_usable(nullptr, 0));
    // (tl_now is steady_clock in ns; the calibrated host stamp is CLOCK_MONOTONIC in ns: the same clock, or the mapping is off)
    timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    const long long mono = (long long)ts.tv_sec * 1000000000LL + ts.tv_nsec;
    const long long steady = (long long)std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
    CHECK(steady - mono >= 0 && steady - mono < 50000000LL);
    std::puts("domain CLOCK_MONOTONIC");
#endif
    CHECK(std::string_view(tl_time_domain_name(VK_TIME_DOMAIN_CLOCK_MONOTONIC_EXT)) == "CLOCK_MONOTONIC");
    return 0;
}
'''


def function(source, head):
    start = source.index(head)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def sources():
    replay = (VK / "vk_replay.cpp").read_text(encoding="utf-8")
    dump = function(replay, "void tl_gpu_dump(int64_t t0_ns) {")
    assert "tl_host_time_domain()" in dump, "tl_gpu_dump must ask for vk_tl_clock.h's host domain"
    assert "VK_TIME_DOMAIN_QUERY_PERFORMANCE_COUNTER_EXT" not in dump, "the QPC domain is Windows-only"
    main = (VK / "vk_main.cpp").read_text(encoding="utf-8")
    at = main.index("optional(VK_EXT_CALIBRATED_TIMESTAMPS_EXTENSION_NAME, dev.calibrated_ts)")
    block = main[at:main.index("#endif", at)]
    assert "#ifndef _WIN32" in block and "vkGetPhysicalDeviceCalibrateableTimeDomainsEXT" in block, "Linux: the device's domains read"
    assert "tl_time_domains_usable(" in block and "dev.calibrated_ts = false" in block, "Linux: no domain, no GPU side"
    assert "GPU side off" in block, "the GPU side turned off says so in the log"
    clock = (VK / "vk_tl_clock.h").read_text(encoding="utf-8")
    win = clock[clock.index("#ifdef _WIN32"):clock.index("#else", clock.index("#ifdef _WIN32"))]
    assert "return VK_TIME_DOMAIN_QUERY_PERFORMANCE_COUNTER_EXT;" in win, "Windows keeps the QPC domain"
    shim = (ROOT / "host" / "posix" / "windows.h").read_text(encoding="utf-8")
    qpf = re.search(r"QueryPerformanceFrequency\(LARGE_INTEGER \*f\) \{ f->QuadPart = (\d+)LL;", shim)
    assert qpf and int(qpf.group(1)) == 1000000000, "the shim's counter frequency is 1e9 (ns)"
    qpc = function(shim, "static inline BOOL QueryPerformanceCounter(LARGE_INTEGER *c) {")
    assert "clock_gettime(CLOCK_MONOTONIC," in qpc, "the shim's counter is CLOCK_MONOTONIC, the domain asked for"


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cxx", default="g++")
    p.add_argument("--headers", required=True, type=Path)
    a = p.parse_args()
    sources()
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "t.cpp")
        exe = os.path.join(tmp, "t.exe")
        Path(src).write_text(FIXTURE, encoding="utf-8")
        flags = ["-std=c++20", "-Wall", "-Wextra", "-Werror", "-I" + str(a.headers), "-I" + str(VK)]
        r = subprocess.run([a.cxx] + flags + [src, "-o", exe], capture_output=True, text=True)
        if r.returncode:
            sys.exit("compile failed:\n" + r.stdout + r.stderr)
        r = subprocess.run([exe], capture_output=True, text=True)
        if r.returncode:
            sys.exit("run failed:\n" + r.stdout + r.stderr)
        print(r.stdout.strip())
    print("ok")


if __name__ == "__main__":
    main()
