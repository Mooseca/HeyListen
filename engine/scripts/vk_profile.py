"""The Vulkan back end's play profile (nx2/vk_pgo.py): merge a counting run's raw profiles and stamp the result.

    python -I scripts/vk_profile.py merge <raw .profraw files or folders ...> [--out <work>/hookshot_vk.profdata]

Recording one (Linux):
  1. build with RX_VK_PGO=gen (the rest of the build's environment as for the build that will use the profile: RX_RELEASE and the
     like change the code the counters belong to);
  2. play with LLVM_PROFILE_FILE=<dir>/hookshot_vk-%p.%cprofraw: the counters are written into that file as they count, so the game
     can end any way;
  3. merge from the same checkout (the stamp is this checkout's back end sources and compiler): this writes the profile and
     <profile>.stamp beside it. The default place, <work>/hookshot_vk.profdata (OOT_WORK, else the checkout's work/), is where
     nx2/build.py looks when RX_VK_PGO is not set.
"""
import argparse
import os
import subprocess
import sys

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ENGINE, "nx2"), os.path.join(ENGINE, "third_party", "a64-kit", "tools")]
import kit   # noqa: E402
import toolchain   # noqa: E402
import vk_pgo   # noqa: E402


def raw_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith(".profraw"))
        else:
            out.append(p)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge", help="merge raw profiles into the back end's profile and stamp it")
    m.add_argument("raw", nargs="+", help=".profraw files, or folders holding them")
    m.add_argument("--out", default=os.path.join(kit.WORK, vk_pgo.PROFILE))
    a = ap.parse_args(argv)
    raws = raw_files(a.raw)
    if not raws:
        raise SystemExit("no .profraw files in %s" % " ".join(a.raw))
    profdata = toolchain.need(toolchain.find("llvm-profdata"))
    subprocess.run([profdata, "merge", "-o", a.out] + raws, check=True)
    stamp = vk_pgo.stamp_text(os.path.join(ENGINE, "gpu"), vk_pgo.compiler_version(toolchain.need(toolchain.find("clang++"))))
    with open(a.out + ".stamp", "w", encoding="utf-8", newline="\n") as f:
        f.write(stamp)
    print("wrote %s (%d KB, from %d raw profiles) and its stamp:\n%s" % (a.out, os.path.getsize(a.out) >> 10, len(raws), stamp.rstrip()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
