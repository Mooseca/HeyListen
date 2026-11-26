# Copyright (C) 2026 Sacrappy

"""The crash record's last GPU write-back by page (host/hos_wb_stamp.h, tests/wb_stamp_test.c) and its wiring: the back end
tells every write-back through the host table's gpu_wrote (gpu/vk/vk_internal.h trace_gpu, always, with no GPU query), the
executable fills it (host/rx_backend.c, host/mkw_glue.c hos_gpu_wrote) and the crash report prints the registers and the
write-backs over the fault's and the registers' pages (mkw_glue.c crash_regs, for a guest thread and a host one)."""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    fails = []
    api = (ROOT / "gpu/vk/vk_api.h").read_text(encoding="utf-8")
    if "void (*gpu_wrote)(uint64_t guest, uint64_t size, uint64_t value);\n} MkwVkHost;" not in api:
        fails.append("vk_api.h: gpu_wrote is the host table's last member")
    internal = (ROOT / "gpu/vk/vk_internal.h").read_text(encoding="utf-8")
    body = internal[internal.index("inline void trace_gpu("):]
    body = body[:body.index("\n}\n")]
    first = body.index("host->gpu_wrote(")
    if first > body.index("vk_timeline_completed()") or "MKWVK_TRACE_WRITEBACK" not in body[:first] or "MKWVK_TRACE_LAZY" not in body[:first]:
        fails.append("vk_internal.h trace_gpu: the write-backs go to gpu_wrote before (and without) the trace's GPU query")
    rx = (ROOT / "host/rx_backend.c").read_text(encoding="utf-8")
    if not re.search(r"hos_out_select, hos_bare_head_live, hos_gpu_wrote,\n};", rx):
        fails.append("rx_backend.c: the host table's gpu_wrote is hos_gpu_wrote")
    glue = (ROOT / "host/mkw_glue.c").read_text(encoding="utf-8")
    crash = glue[glue.index("static LONG WINAPI report_crash("):]
    crash = crash[:crash.index("\n}\n")]
    if crash.count("crash_regs(info->ContextRecord, c,") != 1 or "crash_regs(info->ContextRecord, NULL," not in crash:
        fails.append("mkw_glue.c report_crash: the registers and write-backs told for a guest thread and for a host thread")
    if "hos_wbs_note(&wb_stamps, guest, size, value, wb_ms());" not in glue:
        fails.append("mkw_glue.c: hos_gpu_wrote notes each write-back")
    for f in fails:
        print("FAIL:", f)
    with tempfile.TemporaryDirectory(prefix="hookshot-wbstamp-") as temp:
        exe = Path(temp) / "wb_stamp_test.exe"
        subprocess.run([args.cc, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "host"),
                        str(ROOT / "tests/wb_stamp_test.c"), "-o", str(exe)], check=True)
        rc = subprocess.run([str(exe)], timeout=120).returncode
    return 1 if fails or rc else 0


if __name__ == "__main__":
    sys.exit(main())
