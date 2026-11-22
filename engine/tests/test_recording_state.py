"""(stream REC1) The recording state a segment's worker reads: what is per recording or per thread, by the text of the sources.

docs/native-engine/recording-state.md has each piece's note. Here, the pieces already made per recording (Stage A):
- the page table's deferred changes (table_defer, table_pending) are per thread: one recording is one thread's, so a worker's
  texture_uploads_recorded flushes only what its own recording changed, never the replay thread's next recording's;
- the segments' init command buffers are an object of their group (SegTable), held by the group and by a worker while it records a
  segment of it: no global table (seg_init_mu, seg_inits), and nothing replaces it at a join;
- the uniform updates' list positions are absolute (ub_base, ub_end, ub_at): a prune moves nothing a recording holds, and the deque is
  read through ub_at only.

python -I -B tests/test_recording_state.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu" / "vk"


def need(ok, why):
    if not ok:
        raise SystemExit("FAIL: " + why)


def main():
    mem = (VK / "vk_memory.cpp").read_text(encoding="utf-8")
    tex = (VK / "vk_texture.cpp").read_text(encoding="utf-8")
    hdr = (VK / "vk_texture.h").read_text(encoding="utf-8")
    rep = (VK / "vk_replay.cpp").read_text(encoding="utf-8")

    need("thread_local std::vector<TableRun> table_pending;" in mem and "thread_local bool table_defer = false;" in mem,
         "the page table's deferred changes are no longer per thread")

    need("seg_init_mu" not in tex and "seg_inits" not in tex, "a global segment init table is back")
    need("struct SegTable {" in tex and "SegTableRef texture_segments_begin(" in tex and "SegTableRef texture_segments_begin(" in hdr,
         "texture_segments_begin does not make a table of its own")
    need("texture_segments_begin(nullptr, 0)" not in rep, "a join clears a table that is no longer global")
    need("tl_seg_table = table.get();" in tex, "a worker does not hold its group's table")
    need(len(re.findall(r"texture_segment_worker\(", rep)) == 4, "a segment's worker is set or cleared in a place not seen here")

    need(re.search(r"\bub_updates\[", rep) is not None and len(re.findall(r"\bub_updates\[", rep)) == 1,
         "the uniform updates are read other than through ub_at")
    need("const UbUpdate& ub_at(size_t pos) { return ub_updates[pos - ub_base]; }" in rep, "ub_at does not subtract ub_base")
    need(rep.count("ub_updates.pop_front();\n        ub_base++;") == 1, "a pop does not move ub_base with it")
    need("if (ub_first_of_recording) ub_first_of_recording--;" not in rep, "a prune moves the recording's first position again")
    print("PASS recording state: page table changes per thread, segment init table per group, uniform update positions absolute")


if __name__ == "__main__":
    main()
