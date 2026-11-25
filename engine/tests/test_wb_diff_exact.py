# Copyright (C) 2026 Sacrappy

"""The write-back's diff writes only the vectors that differ (issue 89; gpu/vk/shaders/wb_diff.comp, no game/GPU).

The pass copied a chunk of 16-byte vectors back to guest memory a subgroup's span at a time: when ANY of the 32 vectors of a span
differed between the mirror and the shadow, all 32 (512 bytes) went from the mirror to guest memory. The vectors of the span that
had not changed on the GPU went back too, with the mirror's older words, over whatever the CPU had stored in them since the
mirror's last sync. The lock-on ring's pool (issue 89) holds 256-byte elements: a compute program updates the fields of element 0
and element 2 every frame, the span of 512 bytes held element 1 (and 3) as well, and the game's single store of the pointer's
position there went back to the game's 0x6f fill in the next write-back: one or two of the four pointer triangles were drawn.
Now a lane writes its own vector, and only when it differs.

Checks: the shader has no subgroup vote and guards every store of the vector branch by its own difference; the compiled header
(shaders/wb_diff_comp_spv.h) has no OpGroupNonUniformAny / OpSubgroupAnyKHR and does not ask for the vote capabilities; a model
of the old and the new rule over a span with the GPU's change in one vector and the CPU's store in its neighbour: lost with the
vote, kept without.

python -I -B tests/test_wb_diff_exact.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
SHADER = ROOT / "gpu/vk/shaders/wb_diff.comp"
HEADER = ROOT / "gpu/vk/shaders/wb_diff_comp_spv.h"
SUBGROUP = 32


def code_of(text):
    return "\n".join(line.split("//")[0] for line in text.splitlines())


def check_shader():
    code = code_of(SHADER.read_text(encoding="utf-8"))
    assert "subgroupAny" not in code and "subgroup_vote" not in code, "the pass must not vote across a subgroup"
    vec = code[code.index("if (c.vecs != 0u) {"):code.index("} else {")]
    stores = re.findall(r"\b[gs]\.v\[i\]\s*=", vec)
    assert len(stores) == 2, "the vector branch stores to guest memory and to the shadow"
    guard = re.search(r"if \(any\(notEqual\(v, s\.v\[i\]\)\)\) \{\s*g\.v\[i\] = v;\s*s\.v\[i\] = v;\s*\}", vec)
    assert guard, "both stores sit under the lane's own difference"
    print("shader: no vote, each vector stored only when it differs")


def check_header():
    words = [int(x, 16) for x in re.findall(r"0x[0-9a-f]{8}", HEADER.read_text(encoding="utf-8"))]
    assert words[0] == 0x07230203
    i, ops, caps = 5, set(), set()
    while i < len(words):
        n, op = words[i] >> 16, words[i] & 0xFFFF
        ops.add(op)
        if op == 17:   # OpCapability
            caps.add(words[i + 1])
        i += n
    assert 335 not in ops and 4429 not in ops, "OpGroupNonUniformAny / OpSubgroupAnyKHR in the compiled pass"
    assert 62 not in caps and 4431 not in caps, "the vote capabilities asked for"   # GroupNonUniformVote, SubgroupVoteKHR
    print("header: no vote operation, no vote capability")


def old_rule(mirror, shadow, guest):
    for base in range(0, len(mirror), SUBGROUP):
        span = range(base, min(base + SUBGROUP, len(mirror)))
        if any(mirror[i] != shadow[i] for i in span):
            for i in span:
                guest[i] = shadow[i] = mirror[i]


def new_rule(mirror, shadow, guest):
    for i in range(len(mirror)):
        if mirror[i] != shadow[i]:
            guest[i] = shadow[i] = mirror[i]


def model():
    fill = 0x6F6F6F6F
    for rule, kept in ((old_rule, False), (new_rule, True)):
        # one span of 32 vectors = two 256-byte elements; vector 17 is element 1's position (offset 16 of its 256 bytes)
        mirror = [fill] * SUBGROUP
        shadow = list(mirror)
        guest = list(mirror)
        guest[17] = 0x3F000000                  # the CPU's store, made since the mirror's sync
        mirror[8] = 0x3F800000                  # the GPU's change in element 0's fields (vector 8)
        rule(mirror, shadow, guest)
        assert guest[8] == 0x3F800000, "the GPU's own word reaches guest memory"
        assert (guest[17] == 0x3F000000) == kept, "%s: the CPU's neighbouring store %s" % (rule.__name__, "survives" if kept else "is lost")
    print("model: the CPU's store beside a GPU-changed vector is lost with the vote and kept without")


def main():
    check_shader()
    check_header()
    model()


if __name__ == "__main__":
    main()
