# Copyright (C) 2026 Sacrappy

"""The guessed heads' checked write-back on the GPU (FOLIAGE2; gpu/vk/shaders/wb_guess.comp, vk_memory.cpp "the guessed heads on
the GPU"; no game/GPU). A bare storage entry's head (vk_draw.cpp) is written into guest memory in its own part, as the whole copy
was before CRASH3, but only the words the GPU changed and the CPU did not: checks the shader's rule and its wiring, that the SPIR-V
header is the shader's (when glslangValidator is there), and, on a model of the parts, that the rule keeps CRASH3's guarantee (a
stale entry's head is never written) while the culling counts reach guest memory in the part that wrote them, every part (the
staged form put them there one part late and dropped every other part's: the foliage that vanished, 25 Nov)."""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu/vk"


def check_shader():
    src = (VK / "shaders/wb_guess.comp").read_text(encoding="utf-8")
    for needle in ("if (mv == sv || mv == gv) continue;",
                   "bool untouched = gv == sv;",
                   "by_ours = e.w == 1u && e.x == lo && e.y == hi && e.z == gv;",
                   "g.w[i] = mv;",
                   "pc.ours.e[h] = uvec4(lo, hi, mv, 1u);"):
        if needle not in src:
            raise SystemExit("wb_guess.comp no longer has: " + needle)
    glslang = shutil.which("glslangValidator") or next(
        (p for p in (r"C:\VulkanSDK\1.4.363.0\Bin\glslangValidator.exe",) if os.path.exists(p)), None)
    if not glslang:
        print("wb_guess.comp: glslangValidator not found, the header's match not checked")
        return
    with tempfile.TemporaryDirectory(prefix="wb-guess-gpu-") as tmp:
        out = Path(tmp) / "h.h"
        subprocess.run([glslang, "-V", "--quiet", "--target-env", "vulkan1.3", "--vn", "WB_GUESS_COMP_SPV", "-o", str(out),
                        str(VK / "shaders/wb_guess.comp")], check=True, stdout=subprocess.DEVNULL)
        words = lambda t: re.findall(r"0x[0-9a-f]{8}", t)
        made = words(out.read_text(encoding="utf-8"))
        kept = words((VK / "shaders/wb_guess_comp_spv.h").read_text(encoding="utf-8"))
        if made[5:] != kept[5:]:   # (the header's words past the version and generator words)
            raise SystemExit("shaders/wb_guess_comp_spv.h is not wb_guess.comp's: regenerate it (the command is in the shader)")


def check_wiring():
    mem = (VK / "vk_memory.cpp").read_text(encoding="utf-8")
    for needle in ('#include "shaders/wb_guess_comp_spv.h"',
                   'getenv("RX_VK_WB_GUESS_GPU")',
                   "const bool on_gpu = wb_guess_gpu_on() && gg_pipe_ready() &&",
                   "gg_chunks.push_back({gg_mirror + at, gg_snap.size(), p->address + at, p->lo + at, (uint32_t)((e - w) / 4), 0});",
                   "wb_pages_note(p->lo + at, p->lo + r.dstOffset + e, rec_value_of(), false);",
                   "vkCmdDispatch(cmd, std::min<uint32_t>(n, 65535u), (n + 65534u) / 65535u, 1);",
                   "trace_gpu(MKWVK_TRACE_WRITEBACK, at[k], at[e - 1] + 4 - at[k], 0, t.value);",
                   "if (!on_gpu || (r.dstOffset & 3)) rs.push_back(r);"):
        if needle not in mem:
            raise SystemExit("vk_memory.cpp no longer has: " + needle)


def gpu_rule(m, s, g, ours, addr):
    """wb_guess.comp's rule for one word: (the word guest memory then holds, written?)"""
    if m == s or m == g:
        return g, False
    if g == s or ours.get(addr) == g:
        ours[addr] = m
        return m, True
    return g, False


def staged_rule(m, s, g):
    """CRASH3's staged form for one word, applied a part later (wb_guess.h gpu_words)"""
    return (m, True) if m != s and g == s else (g, False)


def model():
    # (1) a stale entry: the program never writes through it, the CPU's heap writes the words: never written
    ours = {}
    for cpu in (0x11, 0x22, 0x33):
        g, w = gpu_rule(m=0xAA, s=0xAA, g=cpu, ours=ours, addr=0x100)
        assert not w and g == cpu, "a word the GPU did not change was written"
    # (2) a CPU write during the part: left to the CPU
    g, w = gpu_rule(m=7, s=5, g=9, ours={}, addr=0x104)
    assert not w and g == 9
    # (3) the culling count, a new value each part. The snapshot at a part's binding is guest memory as the replay's thread
    # reads it while recording, before the part ahead of it was done on the GPU: one part old. The GPU form lands every part's
    # count in that part (our own last write is not taken for the CPU's); the staged form, written a part later, dropped some
    guest_gpu, ours, landed_gpu = 0, {}, 0
    guest_st, pending, landed_st = 0, [], 0
    prev_guest_gpu, prev_guest_st = 0, 0
    for part in range(1, 41):
        count = 100 + part
        snap_gpu = prev_guest_gpu            # (read while recording, before the previous part's pass ran)
        prev_guest_gpu = guest_gpu
        guest_gpu, w = gpu_rule(m=count, s=snap_gpu, g=guest_gpu, ours=ours, addr=0x200)
        landed_gpu += guest_gpu == count
        snap_st = guest_st
        for (m, s) in pending:               # (the previous part's piece, written at this part's end)
            guest_st, _ = staged_rule(m, s, guest_st)
        pending = [(count, snap_st)]
        landed_st += guest_st == count
        prev_guest_st = guest_st
    assert landed_gpu == 40, landed_gpu
    assert landed_st == 0, landed_st


def main():
    check_shader()
    check_wiring()
    model()
    print("wb_guess_gpu: ok")


if __name__ == "__main__":
    main()
