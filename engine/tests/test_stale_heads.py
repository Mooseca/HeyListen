# Copyright (C) 2026 Sacrappy

"""A bare storage entry whose buffer the game freed is left unbound (CRASH3, issue 55): the big heap blocks' table
(host/hl_stale_heads.h, tests/stale_heads_test.c) and its wiring, read from the source: the heaps' entry gates fill it with or
without the trace (host/hl_trace.c), the host table answers bare_head_live (host/rx_backend.c, MKWVK_API_VERSION 23), and the
back end asks it for a bare written entry before binding and binds nothing when it is stale (gpu/vk/vk_draw.cpp)."""
import argparse
import re
from pathlib import Path
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
    version = re.search(r"#define MKWVK_API_VERSION (\d+)", api)
    if "    int (*bare_head_live)(uint64_t guest);\n" not in api or not version or int(version.group(1)) < 23 or \
            api.index("void (*out_select)(") > api.index("int (*bare_head_live)("):
        fails.append("vk_api.h: bare_head_live after out_select, version 23 or later")
    if "hos_out_select, hos_bare_head_live," not in (ROOT / "host/rx_backend.c").read_text(encoding="utf-8"):
        fails.append("rx_backend.c: the host table answers bare_head_live")
    trace = (ROOT / "host/hl_trace.c").read_text(encoding="utf-8")
    alloc = trace[trace.index("static int alloc_gate("):]
    alloc = alloc[:alloc.index("\n}\n")]
    free = trace[trace.index("static int free_gate("):]
    free = free[:free.index("\n}\n")]
    if "hl_stale_alloc(&stale_heads, block, size);" not in alloc or "if (hl_trace_mask) chain_of(c, chain);" not in alloc:
        fails.append("hl_trace.c alloc_gate: every allocation listed, the chain only with the trace")
    if free.index("hl_stale_free(&stale_heads, c->x[ptr_arg]);") > free.index("if (!hl_trace_mask) return 0;"):
        fails.append("hl_trace.c free_gate: every free told before the trace's own work")
    gates = trace[trace.index("void hl_trace_gates(void) {"):]
    gates = gates[:gates.index("\n}\n")]
    if 'getenv("RX_VK_STALE_HEAD_GUARD")' not in gates or "stale_on = stale;" not in gates:
        fails.append("hl_trace.c hl_trace_gates: the gates on for RX_VK_STALE_HEAD_GUARD (default on) as for the trace")
    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    if "if (bare && d.is_written && host->bare_head_live)" not in draw or \
            "const bool plausible = !stale && (d.count == 1 ||" not in draw:
        fails.append("vk_draw.cpp: a stale bare written entry asked about and left unbound")
    elif draw.index("if (bare && d.is_written && host->bare_head_live)") > draw.index("const bool plausible = !stale"):
        fails.append("vk_draw.cpp: the question comes before the binding")
    for f in fails:
        print("FAIL:", f)
    with tempfile.TemporaryDirectory(prefix="hookshot-stale-") as temp:
        exe = Path(temp) / "stale_heads_test.exe"
        subprocess.run([args.cc, "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "host"),
                        str(ROOT / "tests/stale_heads_test.c"), "-o", str(exe)], check=True)
        rc = subprocess.run([str(exe)], timeout=120).returncode
    return 1 if fails or rc else 0


if __name__ == "__main__":
    sys.exit(main())
