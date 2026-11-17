"""A compute program's local memory size is read from its NVN2 control section (+0x68, bytes a thread), and a program that
names an undefined SPIR-V value (a local access with no local array among them) is left out instead of aborting the game.

The Env gave every compute program 0 bytes of local memory: the SPIR-V back end then declared no local array, and the first
LDL/STL of a compute program that spills wrote a null Id in Sirit's OpAccessChain (EmitLoadLocal), where Sirit called
std::abort(). Once programs over 1 MiB lowered (Longshot #427's port), the start-up's preparation of an older game folder's
seed reached one and the game aborted (SIGABRT) before the title. The size is now read (+0x50 holds it times 32, a warp's;
a size that does not match that, or over 64 KB, is not used; Hookshot a0838250 / f58c6c0e, #1800), and Sirit refuses a null Id
by throwing, not std::abort() (Hookshot 6749ba2174, #1830): EmitInst names the IR op, translate_into's catch leaves the
program out and logs it.

The source is checked for the control section's read, the Env's use of it, Sirit's throw and EmitInst's catch of it;
EmitLoadLocal and EmitWriteLocal are cut out of the back end into a Sirit fixture that (1) emits them with no local array:
each must be refused by an exception, not abort the process; (2) writes a null Id straight into an instruction: Sirit must throw, not
abort; (3) emits them with a declared local array (as DefineLocalMemory): the module must pass spirv-val.

    python -I -B tests/test_compute_local_memory.py --headers <SPIRV-Headers/include> [--cxx g++] [--spirv-val spirv-val]
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu" / "vk"
SPIRV = VK / "eden" / "shader_recompiler" / "backend" / "spirv"


def block(text, marker):
    at = text.index(marker)
    end = text.index("{", at) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[at:end]


def check_source():
    src = (VK / "vk_shader.cpp").read_text(encoding="utf-8")
    fail = []
    if "uint32_t local_memory = 0;" not in src.split("struct Code {", 1)[1].split("bool ok = false;", 1)[0]:
        fail.append("Code has no local_memory field")
    compute = re.search(r"if \(!graphics\) \{(.*?)\n    \}\n    c\.ok = true;", src, re.S)
    if not compute or "std::memcpy(&c.local_memory, ctl + 0x68, 4);" not in compute.group(1):
        fail.append("parse_code does not read the compute local memory size from ctl + 0x68")
    elif "* 32 != warp_local" not in compute.group(1) or "c.local_memory = 0;" not in compute.group(1):
        fail.append("the size is not checked against +0x50 (a warp's)")
    env = src.split("class Env final", 1)[1].split("u64 ReadInstruction", 1)[0]
    if not re.search(r"else \{\s*local_memory = nvn\.local_memory;", env):
        fail.append("the Env does not give a compute program its control section's local memory")
    stream = (VK / "sirit" / "src" / "stream.h").read_text(encoding="utf-8")
    if "std::abort();" in block(stream,"Stream& operator<<(Id value)"):
        fail.append("Sirit aborts the process on a null Id")
    emit = (SPIRV / "emit_spirv.cpp").read_text(encoding="utf-8")
    inst = block(emit, "void EmitInst(EmitContext& ctx, IR::Inst* inst)")
    if "catch (const std::runtime_error& e)" not in inst or "throw LogicError(" not in inst:
        fail.append("EmitInst does not turn Sirit's null Id into a LogicError naming the IR op")
    if fail:
        raise SystemExit("FAIL: " + "; ".join(fail))


FIXTURE = r"""
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <exception>
#include <stdexcept>
#include <vector>
#include <sirit/sirit.h>
using Sirit::Id;
using u32 = std::uint32_t;
struct EmitContext : Sirit::Module {
    using Sirit::Module::Module;
    std::array<Id, 5> U32{};
    Id private_u32{};
    Id local_memory{};
    Id Const(u32 value) { return Constant(U32[1], value); }
};
namespace Shader::Backend::SPIRV {
@@LOCAL@@
}
using namespace Shader::Backend::SPIRV;
int main(int argc, char** argv) {
    if (argc < 2) return 2;
    EmitContext ctx{0x00010600};
    ctx.AddCapability(spv::Capability::Shader);
    ctx.SetMemoryModel(spv::AddressingModel::Logical, spv::MemoryModel::GLSL450);
    const Id void_t{ctx.TypeVoid()};
    ctx.U32[1] = ctx.TypeInt(32, false);
    ctx.private_u32 = ctx.TypePointer(spv::StorageClass::Private, ctx.U32[1]);
    std::vector<Id> interfaces;
    const bool declared = !std::strcmp(argv[1], "declared");
    if (declared) {   // (as DefineLocalMemory: an array of one-word structs, zero-initialised)
        const Id element{ctx.TypeStruct(ctx.U32[1])};
        const Id type{ctx.TypeArray(element, ctx.Const(4U))};
        const Id pointer{ctx.TypePointer(spv::StorageClass::Private, type)};
        ctx.local_memory = ctx.AddGlobalVariable(pointer, spv::StorageClass::Private, ctx.ConstantNull(type));
        interfaces.push_back(ctx.local_memory);
    }
    const Id main_id{ctx.OpFunction(void_t, spv::FunctionControlMask::MaskNone, ctx.TypeFunction(void_t))};
    ctx.AddLabel();
    if (!std::strcmp(argv[1], "none")) {
        int refused = 0;
        try {
            EmitLoadLocal(ctx, ctx.Const(1U));
        } catch (const std::exception&) {
            refused++;
        }
        try {
            EmitWriteLocal(ctx, ctx.Const(2U), ctx.Const(7U));
        } catch (const std::exception&) {
            refused++;
        }
        std::printf("refused %d\n", refused);
        return 0;
    }
    if (!std::strcmp(argv[1], "null")) {
        try {
            ctx.OpAccessChain(ctx.private_u32, Id{0}, ctx.Const(0U));
        } catch (const std::exception&) {
            std::printf("refused 1\n");
            return 0;
        }
        std::printf("refused 0\n");
        return 0;
    }
    if (!declared || argc < 3) return 2;
    const Id word{EmitLoadLocal(ctx, ctx.Const(1U))};
    EmitWriteLocal(ctx, ctx.Const(2U), word);
    ctx.OpReturn();
    ctx.OpFunctionEnd();
    ctx.AddEntryPoint(spv::ExecutionModel::GLCompute, main_id, "main", interfaces);
    ctx.AddExecutionMode(main_id, spv::ExecutionMode::LocalSize, 64u, 1u, 1u);
    const std::vector<u32> code{ctx.Assemble()};
    FILE* f = std::fopen(argv[2], "wb");
    if (!f) return 3;
    std::fwrite(code.data(), 4, code.size(), f);
    std::fclose(f);
    std::printf("declared %zu words\n", code.size());
    return 0;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headers", type=Path, required=True)
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--spirv-val", default="spirv-val")
    args = parser.parse_args()
    check_source()
    getset = (SPIRV / "emit_spirv_context_get_set.cpp").read_text(encoding="utf-8")
    pieces = [block(getset, "Id EmitLoadLocal(EmitContext& ctx, Id word_offset)"),
              block(getset, "void EmitWriteLocal(EmitContext& ctx, Id word_offset, Id value)")]
    fixture = FIXTURE.replace("@@LOCAL@@", "\n".join(pieces))
    sirit = VK / "sirit"
    with tempfile.TemporaryDirectory(prefix="compute-local-memory-") as tmp:
        tmp = Path(tmp)
        cpp, exe = tmp / "fixture.cpp", tmp / "fixture"
        cpp.write_text(fixture, encoding="utf-8")
        r = subprocess.run([args.cxx, "-std=c++20", "-O1", "-I" + str(sirit / "include"), "-I" + str(sirit / "src"),
                            "-I" + str(args.headers), str(cpp), *map(str, sorted((sirit / "src").rglob("*.cpp"))),
                            "-o", str(exe)], capture_output=True, text=True, timeout=600)
        if r.returncode:
            print(r.stdout + r.stderr)
            raise SystemExit("FAIL: the fixture did not build")
        for mode, want, why in (("none", "refused 2", "a local load and store with no local array are not both refused"),
                                ("null", "refused 1", "Sirit does not refuse a null Id by an exception")):
            r = subprocess.run([str(exe), mode], capture_output=True, text=True, timeout=30)
            if r.returncode:
                raise SystemExit("FAIL: %s: the fixture ended with %d (%s)%s" % (
                    mode, r.returncode, "aborted" if r.returncode in (-6, 134) else "failed", ": " + why))
            if r.stdout.strip() != want:
                raise SystemExit("FAIL: %s: %s (%s)" % (mode, why, r.stdout.strip()))
            print("%s: %s" % (mode, r.stdout.strip()))
        spv = tmp / "declared.spv"
        r = subprocess.run([str(exe), "declared", str(spv)], capture_output=True, text=True, timeout=30)
        if r.returncode:
            print(r.stdout + r.stderr)
            raise SystemExit("FAIL: declared: the fixture stopped with a local array declared")
        r = subprocess.run([args.spirv_val, "--target-env", "vulkan1.3", str(spv)], capture_output=True, text=True, timeout=60)
        if r.returncode:
            print(r.stdout + r.stderr)
            raise SystemExit("FAIL: declared: spirv-val")
        print("declared: a local load and store, spirv-val ok")
    print("PASS: compute programs get their control section's local memory; a null Id is refused, not an abort")


if __name__ == "__main__":
    main()
