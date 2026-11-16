"""Who decodes ASTC on the CPU (gpu/vk/vk_texture.cpp astc_cpu_wanted, astc_on_cpu, astc_ready). Ported from Longshot a4ead95c (#489).

The graphics in AMD's Ryzen 7000 (PCI 0x164E) and 9000 (0x13C0) desktop CPUs lose the device on Windows when the GPU decodes
Kokiri Forest's terrain arrays in one long submission, so there ASTC is decoded on the CPU unless RX_VK_ASTC_CPU=0. This cuts
astc_cpu_wanted out of the source, compiles it for Windows (_WIN32 defined: the rule is Windows only) and for the rest, and checks:
 - RX_VK_ASTC_CPU unset: on for those two device ids of vendor 0x1002 on Windows, off for other AMD parts (a 780M, an RX 7800 XT),
   other vendors, and everywhere off Windows;
 - RX_VK_ASTC_CPU=1 (or any value but 0, false, off, no, empty): on everywhere; =0: off even for the Ryzen graphics;
and that astc_ready gives the GPU decoder up when astc_on_cpu says so, and the switch is in docs/development.md.
python -I -B tests/test_astc_cpu.py [--cxx g++]
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r"""
#include <cstdint>
#include <cstdio>
#include <cstring>
%s
int main() {
    struct { const char* env; uint32_t vendor, device; } cases[] = {
        {nullptr, 0x1002, 0x164E}, {nullptr, 0x1002, 0x13C0}, {nullptr, 0x1002, 0x15BF}, {nullptr, 0x1002, 0x747E},
        {nullptr, 0x10DE, 0x164E}, {nullptr, 0x8086, 0x13C0},
        {"1", 0x10DE, 0x2684}, {"2", 0x1002, 0x747E}, {"0", 0x1002, 0x164E}, {"false", 0x1002, 0x13C0},
        {"off", 0x1002, 0x164E}, {"no", 0x1002, 0x164E}, {"", 0x1002, 0x164E}, {"", 0x10DE, 0x2684},
    };
    for (const auto& c : cases) std::printf("%%d\n", astc_cpu_wanted(c.env, c.vendor, c.device) ? 1 : 0);
    return 0;
}
"""

# (the rule on Windows, then elsewhere: one line a case)
WINDOWS = [1, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0]
OTHER = [0, 0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0]


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default=os.environ.get("CXX", "g++"))
    args = parser.parse_args()
    source = (ROOT / "gpu" / "vk" / "vk_texture.cpp").read_text(encoding="utf-8")
    problems = []
    rule = block(source, "bool astc_cpu_wanted(")
    ready = block(source, "bool astc_ready() {")
    if "astc_on_cpu()" not in ready:
        problems.append("astc_ready does not give the GPU decoder up when astc_on_cpu() says so")
    if 'getenv("RX_VK_ASTC_CPU")' in ready:
        problems.append("astc_ready still reads RX_VK_ASTC_CPU itself (any value, =0 too, turned the CPU decode on)")
    docs = (ROOT / "docs" / "development.md").read_text(encoding="utf-8")
    if "`RX_VK_ASTC_CPU=1` or `0`" not in docs:
        problems.append("docs/development.md does not describe RX_VK_ASTC_CPU")
    with tempfile.TemporaryDirectory(prefix="astc-cpu-") as folder:
        tmp = Path(folder)
        # (the rule's _WIN32 renamed: a Windows compiler defines _WIN32 itself, so the check of the other platforms got Windows'
        # rule, and its own headers cannot do without it)
        for name, define, want in (("windows", ["-DASTC_RULE_WIN32"], WINDOWS), ("other", [], OTHER)):
            cpp = tmp / (name + ".cpp")
            cpp.write_text(HARNESS % rule.replace("_WIN32", "ASTC_RULE_WIN32"), encoding="utf-8")
            exe = tmp / name
            r = subprocess.run([args.cxx, "-std=c++17", "-O0", "-Wall", "-Wextra", "-Werror", *define, str(cpp), "-o", str(exe)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode:
                raise SystemExit("FAIL: astc_cpu_wanted does not compile (%s)\n%s%s" % (name, r.stdout, r.stderr))
            got = [int(x) for x in subprocess.run([str(exe)], capture_output=True, text=True, timeout=30).stdout.split()]
            if got != want:
                problems.append("%s: the rule answers %s, wanted %s" % (name, got, want))
    if problems:
        raise SystemExit("FAIL:\n  " + "\n  ".join(problems))
    print("PASS: ASTC is decoded on the CPU for Ryzen 7000/9000 graphics on Windows unless RX_VK_ASTC_CPU=0, and by the switch elsewhere")


if __name__ == "__main__":
    main()
