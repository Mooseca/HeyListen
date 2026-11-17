"""Which sleeps under a millisecond wait on the timer (host/hos_thread.c, short_sleep_how and sleep_ns).

On Linux the game's own sleeps (SleepThread, through hos_sleep_logged) wait on the timer and the host's (hos_sleep_ns:
the frame limiter, the audio renderer) still yield; on Windows all yield unless asked. HOS_SHORT_SLEEP_TIMER=0: all
yield (as before on Linux), =1: all on the timer. Cuts short_sleep_how and sleep_ns's choice out of the source, builds
them with a small table of every case, and checks the game's and the host's sleeps take the right path.

    python -I -B tests/test_short_sleep_timer.py [--cc gcc]

Ported from Hookshot a1eb46046 (#2637); the check is HeyListen's.
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "host/hos_thread.c"

DRIVER = r'''#include <stdio.h>
#include <stddef.h>
%(how)s
/* sleep_ns's choice: 1 when a short sleep yields, 0 when it waits on the timer */
static int yields(int short_timer, int guest) { return %(cond)s; }
int main(void) {
    struct { const char *asked; int posix, guest, yields; } t[] = {
        {NULL, 1, 1, 0}, {NULL, 1, 0, 1},             /* Linux: the game's on the timer, the host's yield */
        {NULL, 0, 1, 1}, {NULL, 0, 0, 1},             /* Windows: all yield */
        {"0", 1, 1, 1}, {"0", 1, 0, 1}, {"", 1, 1, 1}, /* =0 (or empty): all yield */
        {"1", 1, 1, 0}, {"1", 1, 0, 0}, {"1", 0, 0, 0}, {"1", 0, 1, 0},   /* =1: all on the timer */
    };
    int bad = 0;
    for (size_t i = 0; i < sizeof t / sizeof t[0]; i++) {
        const int got = yields(short_sleep_how(t[i].asked, t[i].posix), t[i].guest);
        if (got != t[i].yields) {
            printf("FAIL: HOS_SHORT_SLEEP_TIMER=%%s posix %%d guest %%d: %%s, want %%s\n", t[i].asked ? t[i].asked : "(unset)",
                   t[i].posix, t[i].guest, got ? "yields" : "timer", t[i].yields ? "yields" : "timer");
            bad++;
        }
    }
    return bad != 0;
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    text = SRC.read_text(encoding="utf-8")
    start = text.index("static int short_sleep_how(")
    how = text[start:text.index("\n}", start) + 2]
    m = re.search(r"if \(ns < 1000000 && (short_timer < \(guest \? 1 : 2\))\) \{", text)
    if not m:
        raise SystemExit("FAIL: sleep_ns's short-sleep choice is not keyed on short_timer and guest")
    # (the game's sleeps go through hos_sleep_logged as guest, the host's through hos_sleep_ns as not)
    if "void hos_sleep_ns(int64_t ns) { sleep_away(ns, 0); }" not in text:
        raise SystemExit("FAIL: hos_sleep_ns is not the host's sleep (sleep_away(ns, 0))")
    s = text.index("void hos_sleep_logged(")
    logged = text[s:text.index("\n}", s)]
    if "hos_sleep_ns(" in logged or logged.count("sleep_away(ns, 1)") != 3:
        raise SystemExit("FAIL: hos_sleep_logged's three paths do not all sleep as the game's (sleep_away(ns, 1))")
    with tempfile.TemporaryDirectory(prefix="short-sleep-") as tmp:
        src, exe = Path(tmp) / "t.c", Path(tmp) / "t"
        src.write_text(DRIVER % {"how": how, "cond": m.group(1)}, encoding="utf-8")
        subprocess.run([a.cc, "-std=gnu11", "-Wall", "-Werror", str(src), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        if r.returncode:
            raise SystemExit(r.stdout + r.stderr)
    print("PASS: short sleeps: on Linux the game's wait on the timer, the host's yield; HOS_SHORT_SLEEP_TIMER=0/1 all yield/timer")


if __name__ == "__main__":
    sys.exit(main())
