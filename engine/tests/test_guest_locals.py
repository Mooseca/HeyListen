# Copyright (C) 2026 Sacrappy

"""nx2/guest_locals.py (A64_LOCAL_REGS, A64_LOCAL_FLAGS) and the plain / plain0 texts, game-free, no compiler:

  - the defaults (6 registers, flags on), A64_LOCAL_REGS=0 and A64_LOCAL_FLAGS=0, the kit's A64_PACKED_FLAGS;
  - mentioned_addresses() holds the addresses the text edits pin (oot_patches' heads and labels, native_replace's, the hl_gates
    hooks of host/hl_*.c), keep_mentioned() puts the function that holds one into no_local and plain0, keep_spliced() the
    functions with C spliced in, keep_entered_below() the ones that start below their entry, keep_hot() the hot list,
    keep_not_ran() the functions an A64_LOCAL_FUNCS list does not name;
  - plain0's inverses: nx2/cmpflags.undo and nx2/vecfp.undo give back the translator's text exactly (the edits' recorded
    hashes were made on it);
  - check_patched() stops a lift that wrote a function with an edit's mark and locals.

    python -I -B tests/test_guest_locals.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "nx2"))
sys.path.insert(0, os.path.join(ROOT, "third_party", "a64-kit", "lift"))
for _n in ("A64_LOCAL_REGS", "A64_LOCAL_FLAGS", "A64_PACKED_FLAGS", "A64_LOCAL_FUNCS", "A64_HOT_FUNCS"):
    os.environ.pop(_n, None)
import cmpflags  # noqa: E402
import guest_locals as gl  # noqa: E402
import vecfp  # noqa: E402


def fail(msg):
    raise SystemExit("guest_locals: FAIL: " + msg)


class Lifter:
    """what the keep_* functions read of a lifter"""

    def __init__(self, funcs, after=(), plt=()):
        self.funcs = {e: ({pc: None for pc in body}, {}) for e, body in funcs.items()}
        self.after = {pc: "x" for pc in after}
        self.plt = set(plt)
        self.no_local = set()
        self.plain0 = set()
        self.plain1 = set()

    def fname(self, e):
        return "f_%08x" % e


def check_switches():
    if (gl.local_regs(), gl.local_flags()) != (6, True):
        fail("defaults are %s" % ((gl.local_regs(), gl.local_flags()),))
    os.environ["A64_LOCAL_REGS"] = "0"
    os.environ["A64_LOCAL_FLAGS"] = "0"
    if (gl.local_regs(), gl.local_flags()) != (0, False):
        fail("A64_LOCAL_REGS=0 / A64_LOCAL_FLAGS=0 leave one on")
    os.environ["A64_LOCAL_REGS"] = "4"
    os.environ["A64_LOCAL_FLAGS"] = "1"
    os.environ["A64_PACKED_FLAGS"] = "1"
    if (gl.local_regs(), gl.local_flags()) != (4, False):
        fail("A64_PACKED_FLAGS does not turn the flags' locals off")
    for n in ("A64_LOCAL_REGS", "A64_LOCAL_FLAGS", "A64_PACKED_FLAGS"):
        del os.environ[n]


def check_sets():
    m = gl.mentioned_addresses()
    # (heads in oot_patches.py and native_replace.py, a label in oot_native_resolution.py's neighbours, a return address)
    for a in (0x80b1e140, 0x805aeea0, 0x806702e0, 0x80a9ca9c):
        if a not in m:
            fail("%#x is not among the %d addresses the edits name" % (a, len(m)))
    import hl_gates
    gates = set(int(a, 16) for a in hl_gates.wanted())
    if not gates or not gates <= m:
        fail("the hl_gates addresses are not all mentioned")
    funcs = {0x80000000: [0x80000000, 0x80000004, 0x80000008], 0x80000100: [0x80000100, 0x80000104],
             0x80000200: [0x800001f0, 0x80000200], 0x80000300: [0x80000300], 0x80000400: [0x80000400]}
    L = Lifter(funcs, after=[0x80000104], plt=[0x80000400])
    if gl.keep_spliced(L) != 1 or L.no_local != {0x80000100} or L.plain0 != {0x80000100}:
        fail("keep_spliced: %s %s" % (L.no_local, L.plain0))
    if gl.keep_entered_below(L) != 1 or 0x80000200 not in L.no_local or 0x80000400 in L.no_local:
        fail("keep_entered_below: %s" % sorted(L.no_local))
    if gl.keep_mentioned(L, {0x80000004, 0x80000300, 0x7fffff00}) != 2 or not {0x80000000, 0x80000300} <= L.plain0:
        fail("keep_mentioned: %s" % sorted(L.plain0))
    if 0x80000200 in L.plain0:
        fail("a function kept only for its entry has its passes off too")
    with tempfile.TemporaryDirectory() as tmp:
        hot = os.path.join(tmp, "hot.txt")
        with open(hot, "w") as f:
            f.write("f_80000000\nf_80000300 12\n")
        os.environ["A64_HOT_FUNCS"] = hot
        L2 = Lifter(funcs)
        if gl.keep_hot(L2) != 2 or L2.no_local != {0x80000000, 0x80000300} or L2.plain1 != L2.no_local:
            fail("keep_hot: %s" % sorted(L2.no_local))
        del os.environ["A64_HOT_FUNCS"]
        lst = os.path.join(tmp, "ran.txt")
        with open(lst, "w") as f:
            f.write("f_80000000 1\nf_80000300 2\n")
        L3 = Lifter(funcs, plt=[0x80000400])
        if gl.keep_not_ran(L3) is not None:
            fail("keep_not_ran with no list keeps functions")
        os.environ["A64_LOCAL_FUNCS"] = lst
        gl.keep_not_ran(L3)   # (the PLT stub is not counted: it has no body)
        if L3.no_local != {0x80000100, 0x80000200}:
            fail("keep_not_ran: %s" % sorted(L3.no_local))
        os.environ["A64_LOCAL_FUNCS"] = "all"
        if gl.keep_not_ran(Lifter(funcs)) is not None:
            fail("A64_LOCAL_FUNCS=all keeps functions")
        del os.environ["A64_LOCAL_FUNCS"]


def check_undo():
    sub64 = "{ uint64_t _fa=(c->x[1]),_fb=(c->x[2]),_fr=(c->x[1]-c->x[2]); c->z=(_fr==0); c->n=(int)((_fr>>63)&1); c->c=(_fa>=_fb); " + \
        cmpflags.OLD[64] + " }\n"
    sub32 = sub64.replace("uint64_t", "uint32_t").replace(cmpflags.OLD[64], cmpflags.OLD[32])
    for t in (sub64, sub32, "c->x[0]=1;\n"):
        if cmpflags.undo(cmpflags.rewrite(t)) != t:
            fail("cmpflags.undo(rewrite(t)) != t for %s" % t[:80])
    for orig in ("    { uint32_t _a[4]; memcpy(_a,c->vreg[1],16); }\n", "    { x }\n    { y }\n", "a;\n"):
        wrapped = vecfp.wrap(orig, "a64_vfx_div32v(c,c->vreg[1],c->vreg[2],c->vreg[3],4)")
        if vecfp.undo(wrapped) != orig:
            fail("vecfp.undo(wrap(t)) != t for %r: %r" % (orig, vecfp.undo(wrapped)))
    if vecfp.undo("c->x[0]=1;\n") != "c->x[0]=1;\n":
        fail("vecfp.undo changed an unwrapped text")


def check_patched():
    head = "void f_80000000(Ctx *__restrict A64_NOESC c) {"
    plain = head + "\n    c->x[8] = 1; /* (nx2/oot_patches.py: x) */\n}\n"
    local = head + "\n    uint64_t x8_ = c->x[8];\n    x8_ = 1; /* (nx2/oot_patches.py: x) */\n}\n"
    other = "void f_80000100(Ctx *__restrict A64_NOESC c) {\n    uint64_t x8_ = c->x[8];\n    x8_ = 2;\n}\n"
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "code_000.c"), "w", newline="\n") as f:
            f.write('#include "a64.h"\n' + plain + other)
        if gl.check_patched(tmp) != 1:
            fail("check_patched does not count a marked function with no locals")
        with open(os.path.join(tmp, "code_000.c"), "w", newline="\n") as f:
            f.write('#include "a64.h"\n' + local + other)
        try:
            gl.check_patched(tmp)
        except SystemExit as e:
            if "f_80000000" not in str(e) and "80000000" not in str(e):
                fail("check_patched stops without naming the function: %s" % e)
        else:
            fail("check_patched let a marked function with locals through")


def main():
    check_switches()
    check_sets()
    check_undo()
    check_patched()
    print("guest_locals: pass")


if __name__ == "__main__":
    main()
