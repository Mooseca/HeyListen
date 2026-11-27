# Copyright (C) 2026 Sacrappy

"""The game's allocator returning null is told once, with the heap (host/hl_alloc_null.c, nx2/hl_gates.py's HL_NEW_HOOK).

"Title and intro" crashes (family B of v0.4.3's reports): operator new returned 0 while the modules were made and the caller
wrote through it; the crash record held no heap, size or caller. This test:

- puts the hook into lifted text shaped as the lift writes operator new (f_8005ebe0) and aligned_alloc (f_8005eca0): the
  heap's own call becomes a call and a test of x0, the no-heap exit and aligned_alloc's failure path get a line, the function's
  hash is unchanged, a second run changes nothing, taking the hook out restores the text, other text is left alone;
- builds host/hl_alloc_null.c over a guest memory of its own with made-up sead heaps and checks what is told: the size and
  alignment, the caller, the heap's name, size and free size by its own getFreeSize, each parent up to the root; that the
  registers and flags are as they were; that only the first twelve are told and then every 256th; HOS_NEW_NULL_LOG=0: nothing.

python -I -B tests/test_new_null.py [--cc gcc]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import hl_gates  # noqa: E402

HOS_H = r'''#pragma once
#include <stdint.h>
#include <string.h>
typedef struct { uint64_t x[32]; uint8_t n, z, c, v; } Ctx;
typedef void (*A64Fn)(Ctx *);
typedef struct HosThread HosThread;
#define GUEST 0x80000000ull
extern unsigned char mem[0x100000];
static inline uint64_t recomp_load8(Ctx *c, uint64_t a) { (void)c; return mem[a - GUEST]; }
static inline uint64_t recomp_load64(Ctx *c, uint64_t a) { uint64_t v; (void)c; memcpy(&v, mem + (a - GUEST), 8); return v; }
static inline void recomp_store64(Ctx *c, uint64_t a, uint64_t v) { (void)c; memcpy(mem + (a - GUEST), &v, 8); }
A64Fn a64_lookup(uint64_t a);
void a64_icall(Ctx *c, uint64_t a);
void hos_log(const char *fmt, ...);
HosThread *hos_self(void);
const char *hos_thread_name(HosThread *t);
'''

FIXTURE = r'''#include "hos.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
unsigned char mem[0x100000];
static int logs;
static char last[2000];
void hos_log(const char *fmt, ...) { va_list a; va_start(a, fmt); vsnprintf(last, sizeof last, fmt, a); va_end(a); puts(last); logs++; }
HosThread *hos_self(void) { return NULL; }
const char *hos_thread_name(HosThread *t) { (void)t; return "t"; }
#define VT 0x80001000ull
#define FN_FREE 0x80002100ull
#define H(i) (0x80010000ull + 0x100ull * (i))
#define NAME(i) (0x80020000ull + 0x40ull * (i))
static uint64_t room[8];
static void get_free(Ctx *c) { c->x[0] = room[(c->x[0] - H(0)) / 0x100]; c->x[5] = 0xdead; c->n = c->z = c->c = c->v = 1; }
A64Fn a64_lookup(uint64_t a) { return a == FN_FREE ? get_free : NULL; }
void a64_icall(Ctx *c, uint64_t a) { a64_lookup(a)(c); }
static void make_heap(int i, int parent, uint64_t free_room, const char *name, uint64_t size) {
    recomp_store64(NULL, H(i), VT);
    strcpy((char *)mem + (NAME(i) - GUEST), name);
    recomp_store64(NULL, H(i) + 0x20, NAME(i));
    recomp_store64(NULL, H(i) + 0x28, 0x90000000ull + i);
    recomp_store64(NULL, H(i) + 0x30, size);
    recomp_store64(NULL, H(i) + 0x38, parent < 0 ? 0 : H(parent));
    room[i] = free_room;
}
void hl_oot_new_null(Ctx *c, uint64_t heap, uint64_t size, uint64_t align, uint64_t lr, int kind);
void hl_oot_mheap_pre(Ctx *c);
void hl_oot_mheap_post(Ctx *c);
int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "";
    Ctx c;
    memset(&c, 0, sizeof c);
    recomp_store64(NULL, VT + 0x80, FN_FREE);
    make_heap(0, 1, 0x1000, "Module3", 0x100000);
    make_heap(1, 2, 0, "Modules", 0x400000);
    make_heap(2, -1, 0x2000000, "Root", 0x1b000000);
    for (int r = 1; r < 31; r++) c.x[r] = 0x1000 + r;
    c.n = 1, c.z = 0, c.c = 1, c.v = 0;
    Ctx before = c;
    if (!strcmp(mode, "off")) {
        hl_oot_new_null(&c, H(0), 0x268, 8, 0x80c4afbc, 0);
        CHECK(logs == 0);
        puts("PASS: HOS_NEW_NULL_LOG=0: nothing told");
        return 0;
    }
    hl_oot_new_null(&c, H(0), 0x268, 8, 0x80c4afbc, 0);
    CHECK(logs == 1 && strstr(last, "size 0x268") && strstr(last, "align 8") && strstr(last, "caller 0x80c4afbc"));
    CHECK(strstr(last, "\"Module3\" (1024 KB, 4 KB free") && strstr(last, "parent heap 0x80010100 \"Modules\" (4096 KB, 0 KB free"));
    CHECK(strstr(last, "parent heap 0x80010200 \"Root\" (442368 KB, 32768 KB free"));
    CHECK(memcmp(&c, &before, sizeof c) == 0);   /* (registers and flags as they were) */
    hl_oot_new_null(&c, 0, 0x40, 8, 0x80000010, 1);
    CHECK(logs == 2 && strstr(last, "no heap to take from") && strstr(last, "size 0x40"));
    hl_oot_new_null(&c, 0, 0, 0, 0x80000020, 2);
    CHECK(logs == 3 && strstr(last, "aligned_alloc failed"));
    hl_oot_new_null(&c, 0x1234, 0x10, 8, 0x80000030, 0);   /* (a heap that is no guest address: told, not read) */
    CHECK(logs == 4 && strstr(last, "not a guest address"));
    for (int k = 0; k < 1000; k++) hl_oot_new_null(&c, H(0), 0x10, 8, 0x80000040, 0);
    CHECK(logs == 12 + 3);   /* (twelve, then every 256th of 1004: #256, #512, #768) */
    CHECK(memcmp(&c, &before, sizeof c) == 0);
    /* a module heap that was not made: the arguments saved before the test of the size (the name at sp + 8, the parent in x23), the
       null told after the call, or at once when the heap definition has no size for the module */
    memset(&c, 0, sizeof c);
    strcpy((char *)mem + 0x70000, "Graphics");
    recomp_store64(NULL, 0x80070100ull, 0x80070000ull);
    c.x[31] = 0x800700f8ull;
    logs = 0;
    c.x[0] = 0x3a000000ull, c.x[23] = H(1);
    hl_oot_mheap_pre(&c);
    CHECK(logs == 0);
    c.x[0] = 0;   /* (f_809df710 returned null) */
    hl_oot_mheap_post(&c);
    CHECK(logs == 1 && strstr(last, "\"Graphics\", the parent had no room for the size asked (950272 KB), parent heap 0x80010100 \"Modules\"") &&
          strstr(last, "its parent heap 0x80010200 \"Root\""));
    c.x[0] = 0x80090000ull;   /* (a heap that was made: nothing told) */
    hl_oot_mheap_post(&c);
    CHECK(logs == 1);
    c.x[0] = 0;   /* (no size for the module: it has no heap of its own, as most: not told) */
    hl_oot_mheap_pre(&c);
    hl_oot_mheap_post(&c);
    CHECK(logs == 1);
    puts("PASS: a null from the allocator: the heap, its parents, the size, the caller; the first twelve, then every 256th");
    return 0;
}
'''

# (lifted text shaped as the lift writes it: only the lines the hook looks for are the game's own)
LIFTED = '''#include "a64.h"
void f_8005eca0(Ctx *__restrict A64_NOESC c) {
    { extern volatile int hl_gate_on_8005eca0; extern int hl_gate_8005eca0(Ctx *A64_NOESC); if (__builtin_expect(hl_gate_on_8005eca0, 0) && hl_gate_8005eca0(c)) return; }   /* hl gate 8005eca0 */
if (c->x[8] == 0) { goto L_8005ecd4; }
return;
L_8005ecd4:;
c->x[30] = 0x8005ecd8ULL; f_85717f00(c);
    { uint64_t _r = ((uint64_t)0 | (((uint64_t)0) << 0)); c->x[0] = _r; }
return;
}
void f_8005ebe0(Ctx *__restrict A64_NOESC c) {
if (x21_ == 0) { goto L_8005ec38; }
L_8005ec10:; A64_POLL(c);
    x8_=recomp_load64(c,x1_ + 0);
c->x[0] = x0_; c->x[1] = x1_; c->x[8] = x8_; c->x[19] = x19_; c->x[20] = x20_; c->x[21] = x21_; c->x[31] = x31_; c->n = fn_; c->z = fz_; c->c = fc_; c->v = fv_; A64_IJUMP(c, c->x[3]); return;
L_8005ec54:;
    x1_=recomp_load64(c,x8_ + 0);
if (x1_ != 0) { goto L_8005ec10; }
    { uint64_t _b=x31_; int64_t _o=32; { uint64_t _p0,_p1; recomp_ldp64(c,(_b+_o),&_p0,&_p1); x20_=_p0; x19_=_p1; } }
    { uint64_t _r = ((uint64_t)0 | (((uint64_t)0) << 0)); x0_ = _r; }
return;
}
'''
LIFTED_M = '''#include "a64.h"
void f_83b7b340(Ctx *__restrict A64_NOESC c) {
if (c->x[0] == 0x34900000ULL) c->x[0] += hos_rt_pool_size(0x13100000ULL) - 0x13100000ULL;
if (c->x[0] == 0) { goto L_83b7b440; }
c->x[30] = 0x83b7b440ULL; f_809df710(c);
L_83b7b440:; A64_POLL(c);
    recomp_store64_sp(c,c->x[19] + 0,c->x[0]);
}
'''

# (the same function as the lift without registers in locals writes it: c->x[...] throughout)
LIFTED_B = '''#include "a64.h"
void f_8005ebe0(Ctx *__restrict A64_NOESC c) {
if (c->x[21] == 0) { goto L_8005ec38; }
L_8005ec10:; A64_POLL(c);
    c->x[8]=recomp_load64(c,c->x[1] + 0);
A64_IJUMP(c, c->x[3]); return;
L_8005ec54:;
    c->x[1]=recomp_load64(c,c->x[8] + 0);
if (c->x[1] != 0) { goto L_8005ec10; }
    { uint64_t _b=c->x[31]; int64_t _o=32; { uint64_t _p0,_p1; recomp_ldp64(c,(_b+_o),&_p0,&_p1); c->x[20]=_p0; c->x[19]=_p1; } }
    { uint64_t _r = ((uint64_t)0 | (((uint64_t)0) << 0)); c->x[0] = _r; }
return;
}
'''

# (operator new's other two variants, f_8005e9d0 and f_8005eb20, in the context's form and with their registers in locals: the
# tail call through the vtable in the loop and the zero before the epilogue are the places, as in f_8005ebe0)
def variant(addr, locals_):
    r = (lambda n: "x%d_" % n) if locals_ else (lambda n: "c->x[%d]" % n)
    saved = "c->x[0] = x0_; c->x[31] = x31_; " if locals_ else ""
    return ('#include "a64.h"\n'
            "void f_%s(Ctx *__restrict A64_NOESC c) {\n"
            "if (%s == 0) { goto L_x; }\n"
            "L_y:; A64_POLL(c);\n"
            "    %s=recomp_load64(c,%s + 48);\n"
            "%sA64_IJUMP(c, c->x[3]); return;\n"
            "L_x:;\n"
            "    { uint64_t _b=%s; int64_t _o=32; { uint64_t _p0,_p1; recomp_ldp64(c,_b,&_p0,&_p1); %s=_p0; } }\n"
            "    { uint64_t _r = ((uint64_t)0 | (((uint64_t)0) << 0)); %s = _r; }\n"
            "return;\n}\n" % (addr, r(20), r(8), r(8), saved, r(31), r(29), r(0)))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    for addr in ("8005ebe0", "8005eca0"):
        hook = hl_gates.apply_lift(LIFTED, addr, "new", ())
        assert hook is not None, "f_%s: the hook's anchors were not found in text shaped as the lift writes it" % addr
        assert hl_gates.text_hash(hook, addr) == hl_gates.text_hash(LIFTED, addr), "the hook changed f_%s's hash" % addr
        marked = [l for l in hook.splitlines() if l.endswith("/* hl gate %s */" % hl_gates.step_id(addr))]
        assert len(marked) == (1 if addr == "8005eca0" else 2), (addr, len(marked))
        assert all(l.count("{") == l.count("}") for l in marked), "the hook's braces do not balance"
        assert hl_gates.apply_lift(hook, addr, "new", ()) == hook, "a second run changed the text"
        other = LIFTED.replace("A64_IJUMP(c, c->x[3]);", "A64_IJUMP(c, c->x[4]);") if addr == "8005ebe0" else LIFTED.replace("0x8005ecd8ULL", "0x8005ecdcULL")
        assert hl_gates.apply_lift(other, addr, "new", ()) is None, "another version's text was hooked"
    both = hl_gates.apply_lift(hl_gates.apply_lift(LIFTED, "8005ebe0", "new", ()), "8005eca0", "new", ())
    assert both.count("hl_oot_new_null(c") == 3, both.count("hl_oot_new_null(c")
    assert hl_gates.apply_text(both, {}, {}, {}, {})[0] == hl_gates.MARK.sub("", LIFTED), "taking the hooks out did not restore the text"
    tail = [l for l in both.splitlines() if "A64_ICALL(c, c->x[3])" in l][0]
    assert tail.index("A64_ICALL") < tail.index("hl_oot_new_null(c") < tail.index("return;"), "the test of x0 is not after the call"
    hook_b = hl_gates.apply_lift(LIFTED_B, "8005ebe0", "new", ())
    assert hook_b is not None, "the lift without locals was not hooked"
    assert hook_b.count("hl_oot_new_null(c") == 2 and hook_b.count("x0_") == 0, hook_b
    assert hl_gates.text_hash(hook_b, "8005ebe0") == hl_gates.text_hash(LIFTED_B, "8005ebe0")
    assert hl_gates.apply_lift(hook_b, "8005ebe0", "new", ()) == hook_b
    assert hl_gates.apply_text(hook_b, {}, {}, {}, {})[0] == LIFTED_B
    assert "A64_ICALL(c, c->x[3]); if (__builtin_expect(c->x[0] == 0, 0))" in hook_b
    for addr in ("8005e9d0", "8005eb20"):
        for locals_ in (False, True):
            text = variant(addr, locals_)
            hook_v = hl_gates.apply_lift(text, addr, "new", ())
            assert hook_v is not None, "f_%s was not hooked (registers in locals: %s)" % (addr, locals_)
            assert hook_v.count("hl_oot_new_null(c") == 2, hook_v
            assert hl_gates.apply_text(hook_v, {}, {}, {}, {})[0] == text
            assert hl_gates.text_hash(hook_v, addr) == hl_gates.text_hash(text, addr)
    hook_m = hl_gates.apply_lift(LIFTED_M, "83b7b340", "new", ())
    assert hook_m is not None, "the module heap hook was not put in"
    lines_m = hook_m.splitlines()
    i = lines_m.index("c->x[30] = 0x83b7b440ULL; f_809df710(c);")
    j = lines_m.index("if (c->x[0] == 0) { goto L_83b7b440; }")
    assert "hl_oot_mheap_pre" in lines_m[j - 1] and "hl_oot_mheap_post" in lines_m[i + 1], "the hook's lines are not around the size test and the call"
    assert hl_gates.text_hash(hook_m, "83b7b340") == hl_gates.text_hash(LIFTED_M, "83b7b340")
    assert hl_gates.apply_text(hook_m, {}, {}, {}, {})[0] == LIFTED_M
    asked = hl_gates.wanted_lifts()
    assert asked.get("8005ebe0", (None, None))[1] == "new" and asked.get("8005eca0", (None, None))[1] == "new", \
        "host/hl_alloc_null.c does not ask for the hooks"
    # (the lift's two forms of each variant, the text of an older lift and of a fresh one: both hashes are asked for)
    for addr in ("8005e9d0", "8005eb20", "8005ebe0"):
        assert len(asked[addr][0].split(",")) == 2, "f_%s asks for one form of the lift's text only" % addr
    print("PASS: nx2/hl_gates.py: operator new's two exits and aligned_alloc's failure path hooked once, hash unchanged, "
          "a second run changes nothing, taking them out restores the text, other text is left alone")

    cc = shutil.which(a.cc) or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        print("SKIP: no C compiler")
        return
    with tempfile.TemporaryDirectory(prefix="new-null-") as tmp:
        tmp = Path(tmp)
        (tmp / "hos.h").write_text(HOS_H, encoding="utf-8")
        (tmp / "hl_host.h").write_text('#include "hos.h"\n#define HL_NEW_HOOK(a, h) extern const int hook_##a\n', encoding="utf-8")
        (tmp / "fixture.c").write_text(FIXTURE, encoding="utf-8")
        (tmp / "alloc_null.c").write_text((ROOT / "host" / "hl_alloc_null.c").read_text(encoding="utf-8"), encoding="utf-8")
        exe = tmp / ("fixture.exe" if os.name == "nt" else "fixture")
        subprocess.run([cc, "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror", "-I", str(tmp), str(tmp / "fixture.c"),
                        str(tmp / "alloc_null.c"), "-o", str(exe)], check=True)
        env = {k: v for k, v in os.environ.items() if k != "HOS_NEW_NULL_LOG"}
        for mode, extra in (("", {}), ("off", {"HOS_NEW_NULL_LOG": "0"})):
            r = subprocess.run([str(exe), mode], env=dict(env, **extra), capture_output=True, text=True)
            print("\n".join(l for l in r.stdout.splitlines() if l.startswith("PASS")))
            if r.returncode:
                raise SystemExit("FAIL (%s):\n%s%s" % (mode or "told", r.stdout, r.stderr))


if __name__ == "__main__":
    main()
