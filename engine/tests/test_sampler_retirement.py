"""The sampler cache's retirement (gpu/vk/vk_draw.cpp, "samplers" section; Longshot #442, HeyListen issue 30).

The renderer never destroyed a sampler: it makes one for each sampler state it meets, and a new set at every Anisotropic
filtering, Render resolution or Upscaler change, while a driver allows only so many (maxSamplerAllocationCount: NVIDIA's about
4000). Now identical create infos share one sampler, and from 3/4 of the room the least recently used is retired, destroyed once
the GPU is past the recordings that may use it. This runs the section's own code (cut out of the source) against a modeled driver
that makes 80 samplers and a modeled timeline (tests/sampler_retirement_test.cpp), each case three ways (sampler_for, sampler_make),
and reads the source for the places that hold a sampler handle:

- a texture slot (TexSlot) keeps its sampler only while no sampler has been retired since, and, near the limit, for a present;
- sampler_for's table and the descriptors kept by reuse follow samplers_changed();
- the resources line of the periodic log (the VRAM line) carries the sampler count.
"""
import argparse
from pathlib import Path
import re
import subprocess
import sys
import tempfile

RUN_ALL_ARGS = ["--cxx", "{cxx}", "--headers", "{vulkan_headers}"]

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    """From the marker to the brace that closes the first { after it (braces in strings, characters and comments not counted)"""
    if text.count(marker) != 1:
        raise SystemExit(f"{marker!r} is not in the source once (renamed or reshaped? update the check with the source)")
    start = text.index(marker)
    i = text.index("{", start)
    depth = 0
    while i < len(text):
        c = text[i]
        if text.startswith("//", i):
            i = text.index("\n", i)
            continue
        if text.startswith("/*", i):
            i = text.index("*/", i) + 2
            continue
        if c in "\"'":
            j = i + 1
            while text[j] != c:
                j += 2 if text[j] == "\\" else 1
            i = j + 1
            continue
        depth += c == "{"
        depth -= c == "}"
        i += 1
        if depth == 0:
            return text[start:i]
    raise SystemExit(f"{marker!r}: the block does not close")


def sources():
    source = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    nvn = (ROOT / "gpu/render/rx_nvn.h").read_text(encoding="utf-8")
    return source, nvn


def wiring(source):
    """The places that hold a sampler handle follow a retirement"""
    slot = block(source, "struct TexSlot {")
    if "samp_retired" not in slot or "samp_frame" not in slot:
        raise SystemExit("a texture slot does not keep the sampler book's retirement stamp")
    descriptors = source[source.index("const uint64_t samp_retired = "):]
    descriptors = descriptors[:descriptors.index("sampler = sampler_for(")]
    if "sl->samp_retired == samp_retired" not in descriptors or "sl->samp_frame == samp_frame" not in descriptors:
        raise SystemExit("a texture slot's hit does not compare the retirement stamp and the present")
    if "TexSlot{handle, version, samp_version, texture_epoch(), dgen_now, samp_retired, samp_frame," not in source:
        raise SystemExit("a texture slot is not made with the stamp the sampler was resolved under")
    retire = block(source, "bool sampler_retire() {")
    if "samplers_changed()" not in retire or "retired_gen.fetch_add" not in retire:
        raise SystemExit("a retirement does not move the samplers' generations (sampler_for's tables, the kept descriptors)")
    if "vk_retirement_value()" not in retire:
        raise SystemExit("a retired sampler is not destroyed after the recordings that may use it")
    reap = block(source, "void samplers_reap(")
    if "vkDestroySampler" not in reap or "r.after > completed" not in reap:
        raise SystemExit("a retired sampler is destroyed before the GPU is past its retirement value")
    room = block(source, "bool sampler_room() {")
    if "vk_timeline_reached()" not in room:
        raise SystemExit("sampler_room does not reap against the timeline")
    table = block(source, "VkSampler sampler_for(")
    if "e.frame == frame" not in table or "if (made) e = " not in table:
        raise SystemExit("sampler_for's table does not last a present near the limit or caches a failed creation")
    texture = (ROOT / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    if "sampler_counts(" not in texture or "samplers %u made" not in texture:
        raise SystemExit("the periodic VRAM line does not carry the sampler count")
    replay = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    if "signaled + 1" not in block(replay, "uint64_t vk_retirement_value() {"):
        raise SystemExit("vk_retirement_value is not the value after the next signal")
    if "vkGetSemaphoreCounterValue" not in block(replay, "uint64_t vk_timeline_reached() {"):
        raise SystemExit("vk_timeline_reached does not read the timeline")
    print("PASS: texture slots, sampler_for's table, kept descriptors, the log line and the timeline values follow a retirement")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--headers", type=Path, required=True)
    p.add_argument("--cxx", default="g++")
    p.add_argument("--sanitize", action="store_true")
    a = p.parse_args()
    source, nvn = sources()
    wiring(source)
    head = source[source.index("// ---- samplers (by NVN sampler parameters) ----"):source.index("VkSamplerAddressMode wrap(")]
    actual = head + "\n".join(block(source, marker) for marker in [
        "VkSamplerAddressMode wrap(", "uint32_t aniso_override() {", "VkCompareOp compare_op(",
        "VkSampler sampler_make(int id, bool compare) {", "VkSampler sampler_for(int id, bool compare) {"])
    start = nvn.rfind("typedef struct {", 0, nvn.index("} nvn_samp_par;"))
    params = nvn[start:nvn.index("} nvn_samp_par;", start) + len("} nvn_samp_par;")]
    symbols = sorted(set(re.findall(r"\bNVN_[A-Z0-9_]+", actual)))
    enums = "enum { " + ", ".join(name + "=" + str(i + 1) for i, name in enumerate(symbols)) + " };"
    fixture = (ROOT / "tests/sampler_retirement_test.cpp").read_text(encoding="utf-8")
    fixture = fixture.replace("/* PARAMS */", params).replace("/* ENUMS */", enums).replace("/* ACTUAL */", actual)
    cases = ["limit", "limit-full", "limit-reuse", "limit-threads", "below", "counts"]
    failed = []
    with tempfile.TemporaryDirectory(prefix="sampler-retirement-") as temp:
        cpp, exe = Path(temp) / "fixture.cpp", Path(temp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-DVK_NO_PROTOTYPES", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-missing-field-initializers",
                        "-Wno-unused-function", "-Wno-unused-variable", "-pthread", "-I" + str(a.headers),
                        *(["-fsanitize=address,undefined", "-fno-omit-frame-pointer"] if a.sanitize else []),
                        str(cpp), "-o", str(exe)], check=True)
        for route in ["id", "make"]:
            for case in cases:
                r = subprocess.run([str(exe), route, case], timeout=60, capture_output=True, text=True)
                if r.returncode:
                    last = (r.stderr.strip().splitlines() or ["exit %d" % r.returncode])[-1]
                    failed.append(f"{route} {case}: {last}")
    for f in failed:
        print("FAIL: " + f)
    if failed:
        print(f"{len(failed)} of {len(cases) * 2} sampler retirement cases failed")
        return 1
    print(f"{len(cases) * 2} sampler retirement cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
