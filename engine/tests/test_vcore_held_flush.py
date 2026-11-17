"""The held submits' flush and the presenting thread's submit give the virtual core up before they take flush_cs and take it
back only after it is let go (host/nvn_native.c held_flush_why, nvnQueueSubmitCommands).

flush_cs is held through a replay: the held submits' thread's (a host thread, no core) or a guest thread's that flushes
(a present, a fence wait, an event poll, the presenting thread's own submit). While a zone loads a replay takes up to
hundreds of ms. Before, a guest thread took flush_cs with its core held, and the one that replayed took the core back
before it let flush_cs go: the Presentation Thread sat on its core waiting for flush_cs (Linux, RX 9070 XT: 10 of 10 vcore
escapes during a tour's area loads at a 120 fps cap, each a 250-ms frame), and a flusher waiting for a core with flush_cs
held stalled the holders of the cores that wanted it. The actual held_flush_why and nvnQueueSubmitCommands are compiled
with stand-ins that record whether the thread holds its core when it takes flush_cs or replays, and whether it waits for a
core while it holds flush_cs:

- a flush of two held submits by a thread with a core: the replay and flush_cs without the core, the core taken again
  once, after flush_cs is let go; nothing held: nothing given up;
- a thread without a core takes none;
- the presenting thread's submit with a held one before it (HOS_NVN_HOLD=2), and a submit with the hold off: flush_cs
  and the replay without the core, the core back once, after flush_cs;
- another thread's submit with the hold on: held, flush_cs not taken, the core kept.

python -I -B tests/test_vcore_held_flush.py [--cxx clang++]
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def line(source, marker):
    start = source.index(marker)
    return source[start:source.index("\n", start)]


HARNESS = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef long LONG;
typedef long long LONG64;
typedef void *HANDLE;
typedef struct HosThread { int id; } HosThread;
typedef struct { int depth; } CRITICAL_SECTION;
typedef struct { uint64_t x[32]; } Ctx;
typedef struct { uint32_t magic; uint64_t submits; } nvn_queue;
#define NV(name) static void n_##name(Ctx *c, void *u_)
#define P(i) ((void *)(uintptr_t)c->x[i])
#define PN(i, n) ((void *)(uintptr_t)c->x[i])
#define I(i) ((int)c->x[i])
#define HOS_JT(t, a, b) ((void)0)
static int64_t hos_now_ns(void) { return 1000; }
static void hos_log(const char *f, ...) { (void)f; }
static void die(const char *f, ...) { printf("die: %s\n", f); exit(2); }
static volatile LONG64 hos_present_count;
static int64_t lag_t_sub, lag_f_sub;
static LONG InterlockedIncrement(volatile LONG *p) { return ++*p; }
static LONG64 InterlockedExchange64(volatile LONG64 *p, LONG64 v) { LONG64 o = *p; *p = v; return o; }
static int sets;
static void SetEvent(HANDLE h) { (void)h; sets++; }
void hos_renderer_wait(void) {}
static void check_handle(uint64_t h) { (void)h; }
static void resolve_deferred(uint8_t *p) { (void)p; }
int64_t hos_hold_snapshot(uint32_t **pages, uint8_t **copy) { (void)pages, (void)copy; return 0; }
void hos_hold_check(uint32_t *pages, int64_t n, uint8_t *copy, int64_t *again, int64_t *differ) {
    (void)pages, (void)n, (void)copy, *again = *differ = 0;
}
static HosThread me = {1}, presenter = {2};
static HosThread *self_thread = &me;
static HosThread *hos_self(void) { return self_thread; }
static const char *hos_thread_name(HosThread *t) { return t ? "t" : "-"; }

@GLOBALS@
static void held_init(void) {}

/* the thread's virtual core, as hos_vcore_away / hos_vcore_back keep it (host/hos_thread.c) */
static int core, takes, takes_under_flush, enters_with_core, replays, replays_with_core;
int hos_vcore_away(void) { if (!core) return 0; core = 0; return 1; }
void hos_vcore_back(void) {
    if (core) return;
    core = 1, takes++;
    if (flush_cs.depth) takes_under_flush++;
}
static void EnterCriticalSection(CRITICAL_SECTION *cs) {
    if (cs == &flush_cs && !cs->depth && core) enters_with_core++;
    cs->depth++;
}
static void LeaveCriticalSection(CRITICAL_SECTION *cs) { cs->depth--; }
static void rx_nvn_submit_q(const uint64_t *h, int n, uint64_t q) { (void)h, (void)n, (void)q; replays++, replays_with_core += core; }
static void rx_nvn_submit(const uint64_t *h, int n) { (void)h, (void)n; replays++, replays_with_core += core; }

@FLUSH@

@SUBMIT@

static int bad;
static void check(int ok, const char *what) { if (!ok) { printf("FAIL: %s\n", what); bad = 1; } }
static void reset(int with_core, int n_held) {
    core = with_core, takes = takes_under_flush = enters_with_core = replays = replays_with_core = 0;
    nheld = n_held;
    for (int i = 0; i < n_held; i++) held[i].n = 1, held[i].queue = 7;
    flush_cs.depth = held_cs.depth = 0;
}
static void submit(void) {
    static nvn_queue q;
    static uint64_t handles[1] = {0x1000};
    Ctx c;
    memset(&c, 0, sizeof c);
    c.x[0] = (uint64_t)(uintptr_t)&q, c.x[1] = 1, c.x[2] = (uint64_t)(uintptr_t)handles;
    n_nvnQueueSubmitCommands(&c, NULL);
}
int main(void) {
    hold_on = 2;
    reset(1, 2);
    held_flush_why(HF_PRESENT);
    check(replays == 2 && nheld == 0, "the two held submits replayed");
    check(enters_with_core == 0, "flush_cs taken without the core");
    check(replays_with_core == 0, "the replay without the core");
    check(takes == 1 && takes_under_flush == 0 && core == 1, "the core taken again once, after flush_cs is let go");

    reset(1, 0);
    held_flush_why(HF_SYNC);
    check(replays == 0 && takes == 0 && core == 1, "nothing held: the core kept, nothing replayed");

    reset(0, 1);
    held_flush_why(HF_EVENT);
    check(replays == 1 && takes == 0 && core == 0, "a thread without a core takes none");

    present_thread = &presenter, self_thread = &presenter;
    reset(1, 1);
    submit();
    check(replays == 2 && nheld == 0, "the presenting thread's submit: the held one, then its own");
    check(enters_with_core == 0 && replays_with_core == 0, "the presenting thread's submit: flush_cs and the replays without the core");
    check(takes == 1 && takes_under_flush == 0 && core == 1, "the presenting thread's submit: the core back once, after flush_cs");

    hold_on = 0, self_thread = &me;
    reset(1, 0);
    submit();
    check(replays == 1 && replays_with_core == 0 && takes == 1 && takes_under_flush == 0 && core == 1,
          "the hold off: replayed without the core, the core back once");

    hold_on = 2;
    reset(1, 0);
    sets = 0;
    submit();
    check(replays == 0 && nheld == 1 && sets == 1, "another thread's submit: core, the core submits' thread woken");
    check(enters_with_core == 0 && takes == 0 && core == 1, "another thread's submit: flush_cs not taken, the core kept");
    if (!bad) puts("ok");
    return bad;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    parser.add_argument("--source", type=Path, default=ROOT / "host/nvn_native.c")
    args = parser.parse_args()
    src = args.source.read_text(encoding="utf-8")
    globals_ = "\n".join((
        line(src, "typedef struct { int n; uint64_t h[64];"),
        line(src, "static int64_t lag_held_ts[256]"),
        line(src, "static held_submit held[256];"),
        line(src, "static volatile LONG nheld;"),
        line(src, "static CRITICAL_SECTION held_cs, flush_cs;"),
        line(src, "static int held_ready, hold_on = -1;"),
        line(src, "static HosThread *present_thread;"),
        line(src, "static int hold_check = -1;"),
        line(src, "static HANDLE hold_event;"),
        re.search(r"static int64_t st_hold_flushes,[^;]*;", src).group(0),
        line(src, "enum { HF_FLUSH,"),
        line(src, "static int64_t hold_linger_ns = -1;"),
        line(src, "static volatile LONG64 hold_linger_until;"),
        line(src, "static void *volatile hold_linger_thread;"),
    ))
    globals_ = globals_.replace("static HANDLE hold_event;", "static HANDLE hold_event = (HANDLE)1;")
    fixture = (HARNESS.replace("@GLOBALS@", globals_)
               .replace("@FLUSH@", block(src, "static void held_flush_why(int why) {"))
               .replace("@SUBMIT@", block(src, "NV(nvnQueueSubmitCommands) {")))
    compiler = shutil.which(args.cxx)
    if not compiler:
        raise SystemExit("C++ compiler not found: " + args.cxx)
    with tempfile.TemporaryDirectory(prefix="vcore-held-flush-") as temporary:
        folder = Path(temporary)
        (folder / "fixture.cpp").write_text(fixture, encoding="utf-8")
        exe = folder / ("fixture.exe" if os.name == "nt" else "fixture")
        subprocess.run([compiler, "-std=c++17", "-O1", "-w", str(folder / "fixture.cpp"), "-o", str(exe)], check=True,
                       timeout=120)
        result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        print(result.stdout, end="")
        if result.returncode or "ok" not in result.stdout:
            raise SystemExit("a guest thread holds its virtual core while it waits for flush_cs, or waits for a core "
                             "while it holds it")


if __name__ == "__main__":
    main()
