"""The performance summary (gpu/vk/perf_report.h, perf_report.cpp), ported from Longshot's #983, with no game and no GPU.

- tests/test_perf_report.cpp: the buckets, the interval, what a hitch is and what it waited on, the pacing misses, the JSON
  (every key of Longshot's field tables, and the limits where they cut a field), the release flag, and what a frame costs.
- The wiring in the source: the summary is gated by the menu's row AND an address in the build (nothing is measured or written
  without both), the row defaults to off and is saved as send_performance_stats, turning it off deletes perf_pending and
  perf_sent, the host's perf_info is in the API (version 14), and the frame hook is in the shown-frame count.

    python -I -B tests/test_perf_report.py [--cxx g++]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]


def check(ok, what):
    if not ok:
        print("FAIL:", what)
        sys.exit(1)
    print("PASS:", what)


def wiring():
    cpp = (ROOT / "gpu/vk/perf_report.cpp").read_text(encoding="utf-8")
    menu = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")
    menu_h = (ROOT / "gpu/vk/vk_menu.h").read_text(encoding="utf-8")
    api = (ROOT / "gpu/vk/vk_api.h").read_text(encoding="utf-8")
    check(re.search(r"int send_perf = 0;", menu_h) and re.search(r"int send_crash = 0;", menu_h),
          "both rows default to off (0) in the options")
    check('{TAB_GAMEPLAY, "Send performance statistics", &opts.send_perf, 0, 1, 1,' in menu and
          '{TAB_GAMEPLAY, "Send crash reports automatically", &opts.send_crash, 0, 1, 1,' in menu,
          "the two rows are on the Gameplay tab, Off or On")
    check('return "send_performance_stats";' in menu and 'return "send_crash_reports";' in menu,
          "they are saved with the other options under the keys host/hos_telemetry.h reads")
    check("Not available in this build" in menu and "!telemetry_available()" in menu,
          "without an address the rows say so and are fixed (no arrows)")
    check("return available && opts.send_perf == 1;" in cpp, "measuring needs the row on and an address")
    check("hos_telemetry_base(" in cpp and "HOS_TELEMETRY_ENV" in cpp, "the address is the build's or HL_TELEMETRY_URL's, by the host's rule")
    switch_off = cpp[cpp.index("void switch_off() {"):]
    switch_off = switch_off[:switch_off.index("\n}\n")]
    check('"perf_pending", "perf_sent"' in switch_off and "perf_measure.store(false" in switch_off,
          "turning the row off stops the measuring and deletes perf_pending and perf_sent")
    check("perf_frame_shown();" in menu, "the frame hook is where the shown frames are counted")
    check(re.search(r"#define MKWVK_API_VERSION 14\b", api) and "perf_info" in api, "the host's perf_info is in the API, version 14")
    check("hos_perf_info" in (ROOT / "host/rx_backend.c").read_text(encoding="utf-8"), "rx_backend.c fills perf_info")
    check("perf_report_final(-1);" in (ROOT / "gpu/vk/vk_main.cpp").read_text(encoding="utf-8"),
          "the window's close writes the last summary")
    check("parts_ms" in (ROOT / "gpu/vk/perf_report.h").read_text(encoding="utf-8"), "the payload keeps Longshot's parts_ms")


def unit(cxx):
    with tempfile.TemporaryDirectory(prefix="perf-report-") as t:
        exe = Path(t) / "unit.exe"
        subprocess.run([cxx, "-std=c++20", "-O2", "-I", str(ROOT / "gpu/vk"), str(ROOT / "tests/test_perf_report.cpp"), "-o", str(exe)],
                       check=True, timeout=300)
        out = subprocess.run([str(exe)], capture_output=True, text=True)
        print(out.stdout.strip())
        check(out.returncode == 0, "the summary's buckets, hitches, JSON, release flag and cost" + (": " + out.stderr.strip() if out.returncode else ""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    wiring()
    unit(args.cxx)


if __name__ == "__main__":
    main()
