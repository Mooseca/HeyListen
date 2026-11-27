# Copyright (C) 2026 Sacrappy
"""Compile and run the recording workers' core rule (gpu/vk/par_ideal_rule.h; no game/GPU): RX_VK_PARALLEL_IDEAL is on by
default since 27 Nov 2026, each worker's ideal processor a fast physical core of its own, and only where there is one for
every worker; and by the text, that vk_replay.cpp asks the rule with the host's reserved core and the workers' count."""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check_source():
    src = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    i = src.index("void par_worker_ideal(int index, int workers) {")
    body = src[i:src.index("\nvoid par_worker_main(int index, int workers) {", i)]
    for needle in ['#include "par_ideal_rule.h"',
                   "std::thread(par_worker_main, i, threads).detach();",
                   "    par_worker_ideal(index, workers);\n"]:
        if needle not in src:
            raise SystemExit("gpu/vk/vk_replay.cpp no longer has: " + needle)
    for needle in ['const int mode = e ? (atoi(e) != 0 ? 1 : 0) : -1;',
                   "par_ideal_rule::ideal_cpus(cores, host && host->reserved_cpus ? host->reserved_cpus() : 0, workers, mode)",
                   "GetLogicalProcessorInformationEx(RelationProcessorCore",
                   "p->Processor.EfficiencyClass",
                   "SetThreadIdealProcessor(GetCurrentThread(), (DWORD)cpus[index])"]:
        if needle not in body:
            raise SystemExit("par_worker_ideal no longer has: " + needle)
    if "SetThreadAffinityMask" in body:
        raise SystemExit("par_worker_ideal must stay a hint (an ideal processor), never an affinity")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="par-ideal-rule-") as tmp:
        exe = Path(tmp) / "par-ideal-rule"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/test_par_ideal_rule.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
