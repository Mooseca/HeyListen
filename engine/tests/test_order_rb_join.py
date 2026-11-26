# Copyright (C) 2026 Sacrappy
"""FLASH2: a CPU readback with the order thread waits for the writers of other threads' submissions too, when the range is one the GPU's
write-backs cover (RX_VK_ORDER_RB_JOIN=3), and the audit that found it (RX_VK_ORDER_RB_AUDIT).

By the text of gpu/vk/vk_replay.cpp's ot_join_readback and invalidate:
- the modes: 0 nothing, 2 every job handed over, 4 this thread's jobs and every job for the 0x3980 range, 3 every job for a range with write-backs (memory_writeback_value's `ever`) and this thread's
  jobs for the others, 1 this thread's jobs; the default stays what the brief of the fix says (DEFAULT below);
- the mode-3 test is made before the wait on this thread's own jobs, and the join it takes is ot_join_all (a want taken under ot_mu: every
  job pushed before the call), never a wait on a fixed sequence;
- the audit (logging only) is a post-scope of invalidate that waits for the order thread after the read and compares the write-back value
  taken at the read with the one after: it changes no byte the game reads.

python -I -B tests/test_order_rb_join.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = "5"


def function(text, head):
    i = text.index(head)
    j = text.index("{", i)
    depth = 0
    for k in range(j, len(text)):
        depth += {"{": 1, "}": -1}.get(text[k], 0)
        if depth == 0:
            return text[i:k + 1]
    raise SystemExit("FAIL: unbalanced " + head)


def need(c, msg):
    if not c:
        raise SystemExit("FAIL: " + msg)


def main():
    rp = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    f = function(rp, "void ot_join_readback(uint64_t gpu, uint64_t size) {")
    need('atoi(getenv("RX_VK_ORDER_RB_JOIN")) : ' + DEFAULT in f, "the default mode is not " + DEFAULT)
    need("if (mode == 2) return ot_join_all(OT_READBACK);" in f, "mode 2 is not the join of every job")
    need("if (mode == 4 && size == 0x3980) return ot_join_all(OT_READBACK);" in f, "mode 4 is not the join of every job for the 0x3980 range")
    m5 = f[f.index("if (mode == 5 && size == 0x3980) {"):f.index("if (mode == 3) {")]
    need("want = ot_present_sub, prev = ot_present_seq_prev;" in m5 and "if (own) want = std::max(want, ot_my_seq);" in m5 and "ot_wait_until" in m5 and "ot_join_all" not in m5,
         "mode 5 does not wait for the last present's jobs and this thread's own only")
    need("ot_present_seq = j.seq" in rp[rp.index("void ot_push("):], "ot_push does not note the newest present's sequence")
    need("ot_present_seq_prev = ot_present_seq, ot_present_seq = j.seq, ot_present_sub = ot_last_submit_seq" in rp and "j.since = j.seq - ot_present_seq;" in rp,
         "ot_push does not note the jobs' places in their frames")
    need("prev + d + 2 < want" in m5 and 'getenv("RX_VK_ORDER_R4_LEARN")' in m5, "the learned writer place is not what the wait goes up to")
    need("ot_note_r4_writer();" in (ROOT / "gpu/vk/vk_memory.cpp").read_text(encoding="utf-8").split("BufferRef gpu_buffer_bind(")[1][:900],
         "gpu_buffer_bind does not note the 0x3980 writer")
    onr = function(rp, "void ot_note_r4_writer() {")
    need("if (!ot_self) return;" in onr and "ot_cur_since" in onr, "the writer's place is noted off the order thread or not from the job it is on")
    rr = (ROOT / "gpu/vk/rb_ring.h").read_text(encoding="utf-8")
    need("size == 0x3980 ? 4 : 0" in rr, "the ring has no class for the 0x3980 culling results")
    rb = (ROOT / "gpu/vk/vk_rbring.cpp").read_text(encoding="utf-8")
    need("if (cls == 4 && !r4_on()) return;" in rb and 'getenv("RX_VK_RB_R4") && atoi(getenv("RX_VK_RB_R4")) != 0' in rb, "R4 is not off by default")
    need("uint8_t buf[rb_ring::kMaxCopy];" in rb and "uint8_t waited[rb_ring::kMaxCopy];" in rb, "a class-4 range overflows the ring's buffers")
    need("stats[5];" in rb and "by[5]" in rb, "the per-class tables do not hold class 4")
    m3 = f[f.index("if (mode == 3) {"):]
    m3 = m3[:m3.index("const uint64_t want = ot_my_seq;")]
    need("memory_writeback_value(host->gpu_guest(gpu), size, &ever);" in m3 and "if (ever) return ot_join_all(OT_READBACK);" in m3,
         "mode 3 does not join every job for a range with write-backs")
    need(f.index("if (mode == 3) {") < f.index("const uint64_t want = ot_my_seq;"), "mode 3 is decided after the wait on this thread's jobs")
    need("const uint64_t want = ot_my_seq;" in f and "ot_wait_until" in f, "the other ranges lost the wait on this thread's jobs")
    ja = function(rp, "void ot_join_all(int site) {")
    need("want = ot_seq_pushed;" in ja and "ot_mu" in ja, "ot_join_all does not take its want under ot_mu")
    inv = function(rp, "void invalidate(uint64_t gpu, uint64_t size) {")
    need("ot_join_readback(gpu, size);" in inv, "invalidate does not join")
    need(inv.index("ot_join_readback(gpu, size);") < inv.index("struct RbAuditPost {"), "the audit is taken before the join")
    need("rb_audit_post.v0 = v;" in inv, "the audit does not take the value the read waits for")
    ae = function(rp, "void ot_audit_end(uint64_t want, uint64_t v0, uint64_t gpu, uint64_t size) {")
    need("gpu_write" not in ae and "gpu_read" not in ae, "the audit touches guest memory")
    need("v1 != v0" in ae, "the audit does not compare the two values")
    need('getenv("RX_VK_ORDER_RB_AUDIT")' in function(rp, "bool ot_audit_on() {"), "the audit has no switch")
    print("PASS order readback join")


if __name__ == "__main__":
    main()
