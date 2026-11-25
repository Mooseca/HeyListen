# Copyright (C) 2026 Sacrappy
"""The Handheld profile row applies at once (host/nn_applet.c): a change of the row is told to the game as a console tells a
dock or an undock, the operation mode and performance mode changed messages through the notification calls, and
GetOperationMode / GetPerformanceMode answer the new profile. The poll and the message queue are cut out of the source and
run here; the notification calls and the option's answer are checked by their text. No game or GPU.

    python -I -B tests/test_handheld_live.py [--cxx g++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r'''
#include <cassert>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
typedef long LONG;
static LONG InterlockedCompareExchange(volatile LONG *p, LONG v, LONG cmp) { LONG o = *p; if (o == cmp) *p = v; return o; }
static LONG InterlockedExchange(volatile LONG *p, LONG v) { LONG o = *p; *p = v; return o; }
void hos_log(const char *f, ...) { va_list a; va_start(a, f); vprintf(f, a); va_end(a); printf("\n"); }
static int boot_value;   // (the options file's profile at the start)
static int handheld(void) { return boot_value; }
#define HL_OPT_HANDHELD 101
'''

MAIN = r'''
int main() {
    boot_value = 0;                                   // (docked at the start)
    assert(handheld_live() == 0);
    assert(hos_handheld_poll(-1) == 0 && hos_handheld_take() == 0);      // (the menu not ready: nothing)
    assert(hos_handheld_poll(0) == 0 && hos_handheld_take() == 0);       // (the row as the game started: nothing)
    assert(hos_handheld_poll(1) == 2 && handheld_live() == 1);           // (undocked: two messages, the answer follows)
    assert(hos_handheld_poll(1) == 2);                                   // (polled again: not queued twice)
    assert(hos_handheld_take() == 30 && hos_handheld_take() == 31 && hos_handheld_take() == 0);
    assert(hos_handheld_poll(1) == 0);                                   // (nothing more while the row stays)
    assert(hos_handheld_poll(0) == 2 && handheld_live() == 0);           // (docked again)
    assert(hos_handheld_take() == 30 && hos_handheld_take() == 31);
    assert(hos_handheld_poll(-1) == 0 && handheld_live() == 0);          // (the menu's answer lost: the profile stays)
    static char env[] = "HOS_HANDHELD=1"; putenv(env);                                   // (the environment stands over the row)
    assert(hos_handheld_poll(1) == 0 && hos_handheld_poll(0) == 0 && handheld_live() == 0);
    puts("handheld live: all checks passed");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    src = (ROOT / "host/nn_applet.c").read_text(encoding="utf-8")
    start = src.index("enum { OE_MSG_OPERATION_MODE")
    end = src.index("/* The only system notifications")
    cut = src[start:end]
    for need in ("static int handheld_live(void) {", "static int hos_handheld_poll(int row_value) {",
                 "static unsigned hos_handheld_take(void) {", "OE_MSG_OPERATION_MODE = 30, OE_MSG_PERFORMANCE_MODE = 31"):
        if need not in cut:
            raise SystemExit("host/nn_applet.c no longer has: " + need)
    # (the game's calls: the answers follow the live profile, the notifications come from the poll of the row's option)
    for need in ("HLE(_ZN2nn2oe16GetOperationModeEv) { RET(handheld_live() ? 0 : 1); }",
                 "HLE(_ZN2nn2oe18GetPerformanceModeEv) { RET(handheld_live() ? 0 : 1); }"):
        if need not in src:
            raise SystemExit("host/nn_applet.c no longer has: " + need)
    pops = src[end:]
    for name in ("_ZN2nn2oe25TryPopNotificationMessageEPj", "_ZN2nn2oe22PopNotificationMessageEv"):
        body = pops[pops.index("HLE(" + name + ")"):]
        body = body[:body.index("\n}\n")]
        if "hos_handheld_poll(rx_option(HL_OPT_HANDHELD, -1));" not in body or "hos_handheld_take()" not in body:
            raise SystemExit(name + " does not deliver the Handheld profile's messages")
    if "*(uint32_t *)GP(ARG(0)) = m;" not in pops or "RET(m ? 1 : 0);" not in pops:
        raise SystemExit("TryPopNotificationMessage does not write the message and answer true")
    replay = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    if "if (id == HL_OPT_HANDHELD) return menu_handheld_now();" not in replay:
        raise SystemExit("vk_replay.cpp does not answer HL_OPT_HANDHELD")
    menu = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")
    if "int menu_handheld_now() { return options_read.load(std::memory_order_acquire) ? opts.handheld != 0 : -1; }" not in menu:
        raise SystemExit("vk_menu.cpp: menu_handheld_now is not -1 until the options are read")
    if "options_read.store(true, std::memory_order_release);" not in menu[menu.index("void menu_init() {"):]:
        raise SystemExit("vk_menu.cpp: menu_init does not mark the options as read")
    with tempfile.TemporaryDirectory(prefix="handheld-live-") as tmp:
        cpp = Path(tmp) / "handheld.cpp"
        cpp.write_text(FIXTURE + "static int handheld_live(void);\n" + cut + MAIN,
                       encoding="utf-8")
        exe = Path(tmp) / "handheld"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-x", "c++", str(cpp), "-o", str(exe)],
                       check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
