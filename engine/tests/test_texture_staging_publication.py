"""Execute texture staging and both publication sites against separate host/device caches."""
import argparse
from pathlib import Path
import subprocess
import tempfile

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
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--headers", type=Path, required=True)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    tex = (a.source / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    vma = (a.source / "gpu/vk/vk_vma.cpp").read_text(encoding="utf-8")
    actual = block(tex, "struct Arena {") + ";\nstd::vector<Arena> arenas;\nconstexpr uint64_t kArena=4096;\n"
    actual += block(tex, "struct Staging {") + ";\n" + block(tex, "Staging staging(")
    actual += "\n" + block(vma, "void flush_mapped_range(")
    astc = block(tex, "bool upload_astc_gpu(")
    # The actual layer selection, staging, gather and publication. main's function has since grown the BC cache before the staging
    # and the decoder after it: neither is in this cache fixture, so the head is cut where the cache starts and the gather
    # runs from the staging call to the publication, where the decoder's command buffer is requested.
    head = astc[:astc.index("    // (a level over the chunk bound")]
    start = astc.index("    const Staging s = staging(tail * layers.size()")
    mark = "    flush_mapped_range(s.allocation, s.offset, staged);"
    end = astc.index("\n", astc.index(mark)) + 1
    actual += "\n" + head + astc[start:end] + "    consume(upload_cmd());\n    return true;\n}\n"
    cpu = block(tex, "bool upload_inner(Texture& tex, const Ranges* dirty) {")
    start = cpu.index("                    if (!some) continue;")
    start = cpu.index("\n", start) + 1
    assert cpu[start:].startswith("                }")
    start = cpu.index("\n", start) + 1
    end = cpu.index("                copies.push_back(c);", start) + len("                copies.push_back(c);")
    # The publication site must remain after conversion workers joined and before a copy is queued.
    assert cpu.index("for (std::thread& t : pool) t.join();") < start < cpu.index("vkCmdCopyBufferToImage(upload_cmd(), buffer, tex.image", start)
    actual += "\nvoid cpu_slice(Staging st, uint64_t out_bytes) {\n" + cpu[start:end] + "\n}\n"
    fixture = (ROOT / "tests/texture_staging_publication_test.cpp").read_text(encoding="utf-8").replace("/* ACTUAL */", actual)
    with tempfile.TemporaryDirectory(prefix="texture-staging-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers",
                        "-I" + str(a.headers), *(["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-fno-pie", "-no-pie"] if a.sanitize else []),
                        str(cpp), "-o", str(exe)], check=True)
        for cache in ["coherent", "noncoherent"]:
            for case in ["cpu", "astc", "atom", "reuse", "multiple", "failure", "empty-range"]:
                subprocess.run([str(exe), case, cache], check=True, timeout=15)


if __name__ == "__main__":
    main()
