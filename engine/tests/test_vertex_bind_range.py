"""A draw whose vertex streams changed binds the bindings that changed, not all 16 (gpu/vk/vk_draw.cpp; no game/GPU).

The driver takes every binding it is handed. A draw whose streams differed from the last ones bound handed it all 16,
the unused ones with the zero buffer again: 1.1 % of the replay thread on a Steam Deck, in the driver. vertex_bind_range
gives the bindings that differ from what this command buffer has, and only those are bound. RX_VK_VB_RANGE=0: all 16.

Cuts vertex_bind_range out of the source and runs it; checks draw() binds its range and still remembers all 16. A
partial bind is right only while the 16 remembered (last_vb) are what the command buffer has, so it also checks that
every other vertex or graphics pipeline bind of vk_draw.cpp leaves last_vb_valid false: the mesh fallback's one empty
stream is bound only while it is false, and a host graphics pipeline (a masked clear, the temporal passes) clears it.
From Hookshot 33ed7b81a.

python -I -B tests/test_vertex_bind_range.py [--cxx g++]
"""
import argparse
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    source = (ROOT / "gpu" / "vk" / "vk_draw.cpp").read_text(encoding="utf-8")
    draw = block(source, "void draw(VkCommandBuffer cmd, NvnState& s, const DrawArgs& d)")
    ask = "vertex_bind_range(vbufs, voffs, vsizes, vstrides, last_vb.b, last_vb.o, last_vb.z, last_vb.s, last_vb_valid, &vb_first, &vb_count);"
    bind = "vkCmdBindVertexBuffers2(cmd, vb_first, vb_count, vbufs + vb_first, voffs + vb_first, vsizes + vb_first, vstrides + vb_first);"
    for needle in (ask, bind, '"RX_VK_VB_RANGE"', "if (vb_count && vb_all) vb_first = 0, vb_count = 16;"):
        if needle not in draw:
            raise SystemExit("draw() no longer has: " + needle)
    if "vkCmdBindVertexBuffers2(cmd, 0, 16," in source:
        raise SystemExit("the vertex streams are bound from somewhere that does not ask for the range")
    # (the one other vertex bind: the mesh fallback's empty stream, only while nothing is remembered, which it leaves so)
    fallback = "if (!last_vb_valid && zero_buffer) {"
    binds = [m.start() for m in re.finditer(r"vkCmdBindVertexBuffers2?\(", source)]
    others = [i for i in binds if source[i:].startswith(bind) is False]
    for i in others:
        if fallback not in source[max(0, i - 400):i]:
            raise SystemExit("a vertex bind outside draw()'s range that last_vb does not know of: " +
                             source[i:source.index("\n", i)].strip())
    if not draw.index(ask) < draw.index(bind) < draw.index("std::memcpy(last_vb.b, vbufs, sizeof vbufs)"):
        raise SystemExit("draw() binds before it asks for the range, or remembers the streams before it binds them")
    for needle in ("std::memcpy(last_vb.b, vbufs, sizeof vbufs), std::memcpy(last_vb.o, voffs, sizeof voffs);",
                   "std::memcpy(last_vb.z, vsizes, sizeof vsizes), std::memcpy(last_vb.s, vstrides, sizeof vstrides);"):
        if needle not in draw:
            raise SystemExit("draw() no longer remembers all 16 bindings after a bind: " + needle)
    # (a graphics pipeline of the host's, bound on the replay's command buffer, may set the strides from itself: the next
    # draw must bind all 16 again)
    for m in re.finditer(r"vkCmdBindPipeline\(cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, (\w+)\)", source):
        line = source[m.start():source.index("\n", m.start())]
        if "last_pipeline = " in line:   # (draw()'s own: a game program's pipeline, its strides dynamic)
            continue
        if "last_vb_valid = false" not in source[m.end():m.end() + 300]:
            raise SystemExit("a host graphics pipeline is bound without clearing last_vb_valid: " + line.strip())
    for m in re.finditer(r"= temporal_upscale\(", source):
        if "last_vb_valid = false" not in source[m.end():m.end() + 400]:
            raise SystemExit("the temporal passes' pipelines are bound without clearing last_vb_valid")
    if "last_vb_valid = false" not in block(source, "void draw_begin_recording("):
        raise SystemExit("a new recording keeps the last one's vertex bindings")
    fn = block(source, "void vertex_bind_range(")
    fixture = f'''#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using VkBuffer = uint64_t;
using VkDeviceSize = uint64_t;
#define CHECK(x) do {{ if (!(x)) {{ std::fprintf(stderr, "FAIL:%d %s\\n", __LINE__, #x); std::exit(1); }} }} while (0)
{fn}
int main() {{
    VkBuffer b[16], lb[16];
    VkDeviceSize o[16], z[16], s[16], lo[16], lz[16], ls[16];
    for (int i = 0; i < 16; i++) b[i] = lb[i] = 100 + i, o[i] = lo[i] = 8 * i, z[i] = lz[i] = 65536, s[i] = ls[i] = 12;
    uint32_t first = 99, count = 99;
    vertex_bind_range(b, o, z, s, lb, lo, lz, ls, false, &first, &count);   // (nothing bound on this command buffer yet)
    CHECK(first == 0 && count == 16);
    vertex_bind_range(b, o, z, s, lb, lo, lz, ls, true, &first, &count);    // (the same 16: nothing to bind)
    CHECK(count == 0);
    b[3] = 7;                                                               // (one stream's buffer)
    vertex_bind_range(b, o, z, s, lb, lo, lz, ls, true, &first, &count);
    CHECK(first == 3 && count == 1);
    o[9] = 4096;                                                            // (and another's offset: the range over both)
    vertex_bind_range(b, o, z, s, lb, lo, lz, ls, true, &first, &count);
    CHECK(first == 3 && count == 7);
    b[3] = lb[3], o[9] = lo[9], s[0] = 16;                                  // (a stride alone, the first binding)
    vertex_bind_range(b, o, z, s, lb, lo, lz, ls, true, &first, &count);
    CHECK(first == 0 && count == 1);
    s[0] = ls[0], z[15] = 1;                                                // (a size alone, the last binding)
    vertex_bind_range(b, o, z, s, lb, lo, lz, ls, true, &first, &count);
    CHECK(first == 15 && count == 1);
    b[0] = 1;                                                               // (the first and the last: all 16)
    vertex_bind_range(b, o, z, s, lb, lo, lz, ls, true, &first, &count);
    CHECK(first == 0 && count == 16);
    // (exhaustive over which bindings changed: the range covers every changed one, and binding it gives the same 16)
    for (uint32_t mask = 0; mask < (1u << 16); mask += 37) {{
        for (int i = 0; i < 16; i++) b[i] = lb[i], o[i] = lo[i], z[i] = lz[i], s[i] = ls[i];
        for (int i = 0; i < 16; i++)
            if (mask >> i & 1) o[i] += 64;
        vertex_bind_range(b, o, z, s, lb, lo, lz, ls, true, &first, &count);
        VkDeviceSize bound[16];
        for (int i = 0; i < 16; i++) bound[i] = lo[i];
        for (uint32_t i = first; i < first + count; i++) bound[i] = o[i];
        CHECK(first + count <= 16);
        CHECK(std::memcmp(bound, o, sizeof bound) == 0);
        CHECK((count == 0) == (mask == 0));
    }}
    std::puts("vertex bind range: ok");
    return 0;
}}
'''
    with tempfile.TemporaryDirectory(prefix="vertex-bind-range-") as tmp:
        cpp, exe = Path(tmp) / "t.cpp", Path(tmp) / "t"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
