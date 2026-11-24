# Copyright (C) 2026 Sacrappy

"""The write-back's diff keeps the CPU's stores into a page the GPU writes as well (issue 89; gpu/vk/vk_memory.cpp
shadow_sync_copies, wb_shadow_sync_on; no game/GPU).

The diff writes back the words of a written run in which the mirror differs from the shadow. A page the CPU wrote was made
unknown to the shadow and read again from guest memory by the write-back, after the submission's GPU work: a store the CPU
made after the mirror's sync was then in the shadow and not in the mirror, and the mirror's older word went back over it (the
lock-on ring's pointers: elements 1..3 of the 16 KB pool f_812f0fc0 writes and a compute program updates went back to the
game's 0x6f fill). Now a mirror sync makes the same copies into the shadow as into the mirror, and a mirrored pool's pages
stay known: the shadow is the mirror as the GPU found it.

Compiles shadow_sync_copies and shadow_forget as they are in the source, with stubs for the copies, and checks:
- every copy the sync makes into the mirror (from the captures, the late merges, guest memory) is made into the shadow, with
  the same source and offsets; the pages they cover whole become known, a page partly covered keeps its bit; the live pages of
  a pool with no guest memory buffer are made unknown instead (the write-back reads them whole);
- a word-level model of one page through two submissions, with the diff's rule (a word where the mirror and the shadow differ
  goes to guest memory and the shadow): the CPU's store made after the sync survives the write-back with the shadow kept by
  the sync, and is lost when the page is read again from guest memory at the write-back (the old way);
and in the source: the mirror sync calls it before its copies, shadows_forget_written leaves the pages of a mirrored pool
known when the switch is on, a new mirror makes its shadow unknown, RX_VK_WB_SHADOW_SYNC is on by default.

python -I -B tests/test_wb_shadow_sync.py [--cxx clang++]
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block  # noqa: E402

COPIES_HEAD = ("void shadow_sync_copies(Pool& p, const std::map<VkBuffer, std::vector<VkBufferCopy>>& cap_runs, "
               "const std::vector<VkBufferCopy>& live,\n                        const std::map<VkBuffer, "
               "std::vector<VkBufferCopy>>& late_runs) {")

FIXTURE = r'''
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <vector>
typedef struct VkBuffer_T* VkBuffer;
typedef struct VkCommandBuffer_T* VkCommandBuffer;
#define VK_NULL_HANDLE nullptr
struct VkBufferCopy { uint64_t srcOffset, dstOffset, size; };
constexpr uint64_t kPageShift = 12;
struct Pool {
    uint64_t lo = 0, hi = 0;
    VkBuffer buffer = nullptr, mirror = nullptr, shadow = nullptr;
    void* memory = nullptr;   // (a VkDeviceMemory in the source)
    std::vector<uint64_t> shadow_known;
};
struct Copy { VkBuffer src, dst; VkBufferCopy r; };
static std::vector<Copy> recorded;
static VkCommandBuffer upload_command_buffer() { return (VkCommandBuffer)1; }
static void vkCmdCopyBuffer(VkCommandBuffer, VkBuffer src, VkBuffer dst, uint32_t n, const VkBufferCopy* r) {
    for (uint32_t i = 0; i < n; i++) recorded.push_back({src, dst, r[i]});
}
#define CHECK(ok) do { if (!(ok)) { std::fprintf(stderr, "failed: %s (line %d)\n", #ok, __LINE__); std::exit(1); } } while (0)
@FORGET@
@COPIES@
static bool known(const Pool& p, uint64_t pg) { return p.shadow_known[pg >> 6] >> (pg & 63) & 1; }
static VkBuffer buf(uintptr_t k) { return (VkBuffer)k; }

// (the sync's copies as the mirror gets them, applied to a byte array: the model's GPU copies)
typedef std::vector<uint32_t> Words;
static void apply(const std::vector<Copy>& cs, VkBuffer dst, Words& to, const std::map<VkBuffer, const Words*>& from) {
    for (const Copy& c : cs)
        if (c.dst == dst)
            std::memcpy((uint8_t*)to.data() + c.r.dstOffset, (const uint8_t*)from.at(c.src)->data() + c.r.srcOffset, c.r.size);
}
// (the diff's rule, shaders/wb_diff.comp: a word of the run where the mirror and the shadow differ goes to guest memory and the shadow)
static void diff(const Words& mirror, Words& shadow, Words& guest, uint32_t lo, uint32_t hi) {
    for (uint32_t w = lo; w < hi; w++)
        if (mirror[w] != shadow[w]) guest[w] = shadow[w] = mirror[w];
}

int main() {
    // 1. the copies and the known pages
    {
        Pool p;
        p.lo = 0x10000000, p.hi = 0x10000000 + 6 * 4096;
        p.buffer = buf(0x100), p.mirror = buf(0x200), p.shadow = buf(0x300), p.memory = (void*)1;
        p.shadow_known.assign(1, 0);
        p.shadow_known[0] |= 1ull << 4;   // (page 4 known before: a partial copy keeps it)
        std::map<VkBuffer, std::vector<VkBufferCopy>> cap, late;
        cap[buf(0x10)] = {{0, 0, 4096}, {4096 * 7, 4096, 4096}};   // (pages 0 and 1 whole, from a capture's slots)
        late[buf(0x20)] = {{4096 * 3 + 64, 4096 * 2 + 64, 128}};  // (page 2: a late page's changed words only)
        std::vector<VkBufferCopy> live = {{4096 * 3, 4096 * 3, 4096}, {4096 * 4 + 256, 4096 * 4 + 256, 512}};   // (page 3 whole, page 4 in part)
        recorded.clear();
        shadow_sync_copies(p, cap, live, late);
        CHECK(recorded.size() == 5);
        for (const Copy& c : recorded) CHECK(c.dst == p.shadow);
        int from_cap = 0, from_late = 0, from_live = 0;
        for (const Copy& c : recorded) {
            if (c.src == buf(0x10)) { from_cap++; CHECK((c.r.srcOffset == 0 && c.r.dstOffset == 0) || (c.r.srcOffset == 4096 * 7 && c.r.dstOffset == 4096)); }
            if (c.src == buf(0x20)) { from_late++; CHECK(c.r.dstOffset == 4096 * 2 + 64 && c.r.size == 128); }
            if (c.src == p.buffer) { from_live++; CHECK(c.r.srcOffset == c.r.dstOffset); }
        }
        CHECK(from_cap == 2 && from_late == 1 && from_live == 2);
        CHECK(known(p, 0) && known(p, 1) && known(p, 3));   // (covered whole)
        CHECK(!known(p, 2));                                // (partly covered, unknown before: still unknown)
        CHECK(known(p, 4));                                 // (partly covered, known before: still known)
        CHECK(!known(p, 5));
        // a pool not imported now: its live pages unknown, no copy from a buffer it does not have
        Pool q = p;
        q.memory = nullptr;
        q.shadow_known.assign(1, ~0ull);
        recorded.clear();
        shadow_sync_copies(q, {}, live, {});
        CHECK(recorded.empty());
        CHECK(!known(q, 3) && !known(q, 4) && known(q, 0) && known(q, 5));
    }
    // 2. one page, two submissions: the CPU's store after the sync, the GPU's word in the same page
    for (int keep = 0; keep < 2; keep++) {
        const uint32_t fill = 0x6f6f6f6fu, gpu_word = 0x3f800000u, cpu_word = 0x3f08abd9u;
        const uint32_t e0 = 64 + 61, e1 = 128 + 4;   // (element 0's +244, the compute's; element 1's +16, the CPU's)
        Words guest(1024, fill), mirror(1024, fill), shadow(1024, fill);
        Pool p;
        p.lo = 0x10386c6000, p.hi = p.lo + 4096;
        p.buffer = buf(0x100), p.mirror = buf(0x200), p.shadow = buf(0x300), p.memory = (void*)1;
        p.shadow_known.assign(1, 1);
        // submission 1: its sync found nothing new; the GPU writes element 0
        mirror[e0] = gpu_word;
        // the game's thread, a frame ahead, stores element 1 after that sync
        guest[e1] = cpu_word;
        // the write-back of submission 1
        if (!keep) shadow = guest;   // (the old way: the page the CPU wrote, read again from guest memory after the GPU's work)
        diff(mirror, shadow, guest, 0, 1024);
        CHECK(guest[e0] == gpu_word);
        if (!keep) {
            CHECK(guest[e1] == fill);   // (the store lost: what issue 89 drew)
            continue;
        }
        CHECK(guest[e1] == cpu_word);   // (kept: the GPU did not write it)
        // submission 2: the sync takes the page live, into the mirror and, by shadow_sync_copies, the shadow
        const std::vector<VkBufferCopy> live = {{0, 0, 4096}};
        recorded.clear();
        shadow_sync_copies(p, {}, live, {});
        std::vector<Copy> to_mirror = {{p.buffer, p.mirror, live[0]}};
        to_mirror.insert(to_mirror.end(), recorded.begin(), recorded.end());
        const std::map<VkBuffer, const Words*> src = {{p.buffer, &guest}};
        apply(to_mirror, p.mirror, mirror, src);
        apply(to_mirror, p.shadow, shadow, src);
        CHECK(known(p, 0) && mirror == shadow && mirror[e1] == cpu_word);
        mirror[e0] = gpu_word + 1;   // (the GPU's next word)
        diff(mirror, shadow, guest, 0, 1024);
        CHECK(guest[e0] == gpu_word + 1 && guest[e1] == cpu_word);
    }
    std::puts("PASS: a mirror sync makes its copies into the shadow too; the CPU's store after the sync survives the write-back");
}
'''


def check_source(text):
    sync = block(text, "int64_t mirror_sync(Pool& p) {")
    call = "if (p.shadow && wb_shadow_sync_on()) shadow_sync_copies(p, cap_runs, runs, late_runs);"
    if call not in sync:
        raise SystemExit("mirror_sync no longer gives its copies to shadow_sync_copies")
    if sync.index(call) > sync.index("for (const auto& [buf, rs] : cap_runs) {") or sync.index(call) > sync.index("scatter_add(p.address"):
        raise SystemExit("mirror_sync gives its copies to shadow_sync_copies after it made (or scattered, and cleared) them")
    forget = block(text, "void shadows_forget_written() {")
    if "if (sync_keeps && p->mirror && p->mstate == Pool::MIRROR_ON) continue;" not in forget:
        raise SystemExit("shadows_forget_written makes a mirrored pool's pages unknown again with RX_VK_WB_SHADOW_SYNC on")
    if "if (p->shadow && wb_shadow_sync_on()) std::fill(p->shadow_known.begin(), p->shadow_known.end(), 0ull);" not in text:
        raise SystemExit("a new mirror no longer makes its pool's shadow unknown (RX_VK_WB_SHADOW_SYNC)")
    on = block(text, "bool wb_shadow_sync_on() {")
    if '!getenv("RX_VK_WB_SHADOW_SYNC") || atoi(getenv("RX_VK_WB_SHADOW_SYNC")) != 0' not in on:
        raise SystemExit("RX_VK_WB_SHADOW_SYNC is no longer on by default (=0 off)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    text = (ROOT / "gpu/vk/vk_memory.cpp").read_text(encoding="utf-8")
    check_source(text)
    src = FIXTURE.replace("@FORGET@", block(text, "void shadow_forget(Pool& p, uint64_t at, uint64_t len) {"))
    src = src.replace("@COPIES@", block(text, COPIES_HEAD))
    with tempfile.TemporaryDirectory() as tmp:
        cpp = Path(tmp) / "shadow_sync.cpp"
        exe = Path(tmp) / "shadow_sync.exe"
        cpp.write_text(src, encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++20", "-O1", str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
