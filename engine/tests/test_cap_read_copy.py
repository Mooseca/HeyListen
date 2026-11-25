# Copyright (C) 2026 Sacrappy

"""Issue 135 (change by azy2): the CPU reads the capture buffers with streaming loads (vk_memory.cpp cap_read_copy), which write
the same bytes as memcpy for every source/destination alignment and size (the streaming path takes a source aligned to 32 bytes,
and a destination aligned to 32 for streaming stores; the tail and anything else goes through memcpy); RX_VK_CAP_READ_STREAM=0
is memcpy; without AVX2 the function is memcpy; and every read of a capture buffer by the CPU goes through it.

python -I -B tests/test_cap_read_copy.py --cxx <compiler>
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    source = (ROOT / "gpu/vk/vk_memory.cpp").read_text(encoding="utf-8")
    a = source.index("bool cap_read_stream_on() {")
    b = source.index("// ---- texture storage in the capture ----")
    block = source[a:b]
    if "_mm_mfence();" not in block or "_mm256_stream_load_si256" not in block or "#if defined(__AVX2__)" not in block:
        raise SystemExit("cap_read_copy lost its fence, its streaming loads or its AVX2 guard")
    if 'getenv("RX_VK_CAP_READ_STREAM")' not in block:
        raise SystemExit("no RX_VK_CAP_READ_STREAM switch")
    # the readers of a capture buffer: the shadow's two 4 KB copies, the overlay's two copies, the pre-copy grow
    n = source.count("cap_read_copy(")
    if n < 6:
        raise SystemExit("cap_read_copy is used %d times, expected the definition, the fallback and 5 readers" % n)
    for bad in ("std::memcpy(slot.b.get(), map +", "std::memcpy(slot.b.get(), (const uint8_t*)c->map +",
                "std::memcpy((uint8_t*)dst + (a - guest), (const uint8_t*)b->second.map"):
        if bad in source:
            raise SystemExit("a read of a capture buffer went back to memcpy: " + bad)
    fixture = r'''
#include <immintrin.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"FAIL:%d %s\n",__LINE__,#x); std::exit(1); } } while (0)
''' + block + r'''
int main() {
    std::vector<uint8_t> src(1 << 20), a((1 << 20) + 64), b((1 << 20) + 64);
    for (size_t i = 0; i < src.size(); i++) src[i] = (uint8_t)(i * 2654435761u >> 13);
    uint8_t* da = (uint8_t*)(((uintptr_t)a.data() + 63) & ~(uintptr_t)63);
    uint8_t* db = (uint8_t*)(((uintptr_t)b.data() + 63) & ~(uintptr_t)63);
    // (the source is the vector's data: 16-byte aligned at least; the offsets make 32-byte aligned and unaligned starts)
    const uintptr_t base = ((uintptr_t)src.data() + 63) & ~(uintptr_t)63;
    const size_t off0 = (size_t)(base - (uintptr_t)src.data());
    const size_t sizes[] = {0, 1, 31, 32, 127, 128, 129, 255, 4096, 4096 * 3, 4096 * 17 + 128, 4096 * 17 + 130, 65536};
    const size_t src_offs[] = {0, 1, 7, 16, 32, 4096};
    const size_t dst_offs[] = {0, 8, 32, 33};
    for (int stream_store = 0; stream_store < 2; stream_store++)
        for (size_t n : sizes)
            for (size_t so : src_offs)
                for (size_t dof : dst_offs) {
                    std::memset(da, 0xAB, 1 << 19);
                    std::memset(db, 0xAB, 1 << 19);
                    cap_read_copy(da + dof, src.data() + off0 + so, n, stream_store != 0);
                    _mm_sfence();
                    std::memcpy(db + dof, src.data() + off0 + so, n);
                    CHECK(std::memcmp(da, db, 1 << 19) == 0);
                }
    std::puts("ok");
    return 0;
}
'''
    work = Path(os.environ.get("RX_TEST_WORK", tempfile.gettempdir())) / "test_cap_read_copy"
    work.mkdir(parents=True, exist_ok=True)
    cpp = work / "t.cpp"
    exe = work / ("t.exe" if os.name == "nt" else "t")
    cpp.write_text(fixture, encoding="utf-8")
    for flags in (["-mavx2"], []):   # (with AVX2: the streaming loads; without: the memcpy fallback)
        subprocess.run([args.cxx, "-std=c++20", "-O2", *flags, str(cpp), "-o", str(exe)], check=True)
        for env in ({}, {"RX_VK_CAP_READ_STREAM": "0"}):
            out = subprocess.run([str(exe)], capture_output=True, text=True, env={**os.environ, **env})
            if out.returncode != 0 or "ok" not in out.stdout:
                raise SystemExit("cap_read_copy differs (%s %s): %s%s" % (flags, env, out.stdout, out.stderr))
    print("ok: cap_read_copy matches memcpy")


if __name__ == "__main__":
    main()
