# Copyright (C) 2026 Sacrappy

"""RX_VK_THREAD_PRIO: the roles' priorities (gpu/vk/thread_prio.h), the lift of a waited-for job's worker (vk_jobs.cpp), and the
call sites that carry the roles (no game/GPU).

thread_prio.h and vk_jobs.cpp are built beside stand-ins for the renderer's headers and run at the three modes (0 off, 1 on,
2 on with the in-play compile idle): the table, the processor mask, a worker lifted while a frame waits for its job and put
back after, nothing lifted for a job nobody waits for. The source is checked for the call sites: every compile thread of
vk_draw.cpp and vk_jobs.cpp goes through MKWVK_PRIO, no time-critical level, the start line, the hooks.
python -I -B tests/test_thread_prio.py [--cxx g++]
"""
import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STUB_INTERNAL = """#pragma once
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <thread>
using HANDLE = void*;
constexpr int THREAD_PRIORITY_BELOW_NORMAL = -1;
namespace stub { void note_level(int); }
inline HANDLE GetCurrentThread() { return nullptr; }
inline int SetThreadPriority(HANDLE, int l) { stub::note_level(l); return 1; }
inline long SetThreadDescription(HANDLE, const wchar_t*) { return 0; }
namespace mkwvk {
inline void logf(const char*, ...) {}
}
"""

STUB_DRAW = """#pragma once
namespace mkwvk {
inline void ub_thread_off() {}
inline void pipeline_cache_between_builds() {}
}
"""


def check_source():
    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    jobs = (ROOT / "gpu/vk/vk_jobs.cpp").read_text(encoding="utf-8")
    main = (ROOT / "gpu/vk/vk_main.cpp").read_text(encoding="utf-8")
    header = (ROOT / "gpu/vk/thread_prio.h").read_text(encoding="utf-8")
    for name in ("vk_draw.cpp", "vk_jobs.cpp", "vk_replay.cpp", "vk_main.cpp", "vk_memory.cpp"):
        if "THREAD_PRIORITY_TIME_CRITICAL" in (ROOT / "gpu/vk" / name).read_text(encoding="utf-8"):
            raise SystemExit("a renderer thread is time-critical: " + name)
    # (no bare idle call is left in the draw path outside the role calls)
    for m in re.finditer(r"SetThreadPriority\([^;]*THREAD_PRIORITY_IDLE[^;]*;", draw):
        if "prio::level(prio::Role::CompileSoft" not in m.group(0):
            raise SystemExit("an idle priority is set without its role: " + m.group(0))
    if draw.count("MKWVK_PRIO(prio::Role::CompileSoft, THREAD_PRIORITY_IDLE)") < 5:
        raise SystemExit("the in-play compile threads (state list x2, prepare, prepare_background, predict, the test's) lost their role")
    if draw.count("MKWVK_PRIO(prio::Role::Compile, THREAD_PRIORITY_BELOW_NORMAL)") < 2:
        raise SystemExit("the precompile's and the noted prediction's in-play workers lost their role")
    if jobs.count("MKWVK_PRIO(prio::Role::Compile, THREAD_PRIORITY_BELOW_NORMAL)") != 2:
        raise SystemExit("the jobs workers and the serial builds lost their role")
    if "prio::hooks().set_level(r.handle, prio::kNormal)" not in jobs or "r.flag == &flag" not in jobs:
        raise SystemExit("jobs_wait no longer lifts the worker running the job it waits for")
    if 'logf("vk: thread priorities: %s"' not in main or "thread_prio_init();" not in main:
        raise SystemExit("the start line for the thread priorities is gone")
    if "SetThreadAffinityMask(GetCurrentThread(), (DWORD_PTR)mask)" not in main or "host->reserved_cpus" not in main:
        raise SystemExit("the compile threads are no longer kept off the replay's core")
    if "RX_VK_THREAD_PRIO" not in header:
        raise SystemExit("the switch is not named in its header")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="thread-prio-") as tmp:
        tmp = Path(tmp)
        for name in ("vk_jobs.cpp", "vk_jobs.h", "thread_prio.h"):
            shutil.copy(ROOT / "gpu/vk" / name, tmp / name)
        (tmp / "vk_internal.h").write_text(STUB_INTERNAL, encoding="utf-8")
        (tmp / "vk_draw.h").write_text(STUB_DRAW, encoding="utf-8")
        exe = tmp / "thread-prio"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-pthread", "-I", str(tmp),
                        str(tmp / "vk_jobs.cpp"), str(ROOT / "tests/test_thread_prio.cpp"), "-o", str(exe)], check=True)
        for mode in ("0", "1", "2"):
            subprocess.run([str(exe), mode], check=True, timeout=60,
                           env={**os.environ, "RX_VK_THREAD_PRIO": mode, "RX_VK_WORKERS": "1", "RX_VK_STORM_WORKERS": "0",
                                "RX_VK_JOB_STEAL": "1"})


if __name__ == "__main__":
    main()
