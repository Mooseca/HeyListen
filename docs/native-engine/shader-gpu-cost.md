# Where the translated shaders lose GPU time (SHADERQ, 2026-11-21)

Side item of `refactor-plan.md` for GPU-bound cards. Question: in Market (`market-spin`) on the RTX 3050 at 1440p scene geometry is ~11.9 ms of
~18 ms of GPU a frame (`gpu-pass-cost.md` B3), no program above 5.5%. Does the SPIR-V we hand the driver cost more than the guest's program did,
and what is each fix worth? Read first: `shader-efficiency.md` (P4/P5: the global-memory helper in mesh programs, already worked: NOINLINE_ABOVE and
FOLD_PSEUDO are on by default), `shader-key.md` (what a translator change throws away).

**Answer in short.** In Market's top programs the translation is close to one SPIR-V instruction per guest instruction. The inflation I can find
is small and spread thin: about 3% of a fragment program's instructions are sign flips done on the register bits, 5-10% is the global-memory
helper (vertex pulls and one light fetch), 12% of the blocks of the big fragment programs are empty `if`s left by predication. Nothing here
reaches 0.3 ms of the 3050's 11.9 ms by reading. **On the RTX 5070 none of the four run-time variants I built moves any program beyond noise**
(table below); the 5070 is CPU-bound in Market (GPU 4 ms a frame), so this is a weak judge: the 3050 runs are the real test and are prepared
(commands at the end). Honest expectation for the 3050: 0.1-0.4 ms (1-3%) from the best variant, not more.

## What I looked at

SPIR-V of the Market programs by GPU ms on the 3050 (`pt2` log: 1a7482c0 1.07 ms, fb7de124 0.83, d8180bd8 0.48, 7b8eefac 0.44, 17c69696 0.32,
46c14f8e 0.32, 3427a1db 0.31, c254a02b 0.25, ffb53ed1 0.24, d8e59341 0.23, b89bd6c2 0.20, 48ed5183 0.20; together ~5.5 of 11.9 ms), read from slot a's
program cache with `engine/scripts/spirv_stats.py` helpers, disassembled with `spirv-dis` (scratch `E:\OOT\scratch-shaderq`, nothing of the game is in the
repository). Findings by pattern, with the counts of the programs above:

| Pattern | What it is | Count | Cost reasoning |
|---|---|---|---|
| Sign flip on bits | the Ampere to Maxwell lowering (`lower_to_maxwell.h` `materialize`) and LOP forms make `OpBitcast u32`, `OpBitwiseXor 0x80000000`, `OpBitcast f32` where the GPU has a free FADD/FMUL/FFMA source modifier | 1,914 xors in 66 k instructions (2.9%); 4% of the big fragments; abs (and 0x7fffffff) 162 | one extra LOP per use unless the driver recognises the idiom (not known); 222 of 230 in fb7de124 are covered by `fneg2` |
| Predication as branches | every predicated guest instruction is a one-instruction `if` on the same predicate; chains of 5-20 on one condition; many bodies empty after folding | fb7de124 fragment: 267 conditional branches, 121 empty; 17c69696/46c14f8e the same; 1a7482c0: 22 | the drivers probably if-convert; empty ones are pure phi selects. `emptyif` removes the empty ones (-12% words) |
| Global-memory helper | `DontInline` search over the candidate storage buffers (~29 instr a candidate, 64-bit math) | vertex 7b8e/48ed/b89b: 72 call sites, 2 candidates, 96-instr helper (effective 6.9 k of 4.7 k body); fragments fb7de/46c1/17c6: 5 sites, 4 candidates (the light list: 4 vec4 loads + 1 word a pixel, ~8% of the program) | the 22% of a skinned vertex stage and ~5-8% of the big lit fragments; same finding as P4, a host-made range table (P4 #2) is the fix; Market's share ~0.1-0.3 ms |
| Float controls | `SignedZeroInfNanPreserve 32` on every module, `NoContraction` on ~every FMul/FAdd that is not an Fma (1,183 in fb7de124) | all | exact to the guest (no fusing it did not do); fusing is bounded by the FAdd count (3% of instructions): at most ~3% ALU |
| Conversions | 9.3 k bitcasts in 66 k instructions, 25% of instructions are f32 ALU | all | bitcasts are free in every driver I know; not a cost |
| 16-bit | f16 ops: 12 in each big fragment, 0 elsewhere (0.29 M of 330 M cache-wide) | | nothing to gain; GA10x runs f16 at the f32 rate |
| Constant buffers | two views (u32 and f32 arrays, 64 KB) of each buffer, constant indices (292 of 297 accesses in fb7de124), no storage-buffer emulation | | maps to the constant bank directly; fine |
| Attributes, interpolation | vertex inputs and Input variables, `Flat`/`NoPerspective` kept as the guest had them; mesh programs only d8e59341 in the top 12 | | fine. Mesh conversion (`meshconv`) is 0.12 ms on the 3050 |
| Quad ops | fragment ballot + shuffle in fb7de124 (the guest's own SHFL) | 10 | the guest's, not ours |
| Subgroup pins | 32-lane stages on NVIDIA: no emulation (`RX_VK_WARP_WIDE` is a no-op there) | | nothing |

The big programs are simply big: fb7de124's fragment has 2,270 f32 ALU operations a pixel on its own, 1a7482c0 (1.07 ms, 3.7 Mpixel, 16 texture
operations including gathers) is a pixel-bound shading pass. Resolution-dependent work is 5.5 ms of the 3050's frame and that is the game's.

## Variants (default off): `RX_VK_POLISH=<names>`

`engine/gpu/vk/spirv_polish.h`, applied in `make_module` (`vk_shader.cpp`) to every module as the driver gets it, so cached programs are polished too and an
arm needs **no new translation**. The name is outside the stamp prefixes; the pipeline ledger's fingerprint carries the mask (`program_fingerprint`),
so a polished pipeline is built again and never confused with a plain one. The only stamp change is the one edit of `vk_shader.cpp` (it is in the stamp's
file list): one re-prepare for everybody if this is ever shipped; with the switch off the modules are bit-identical.

| Name | What | Validated |
|---|---|---|
| `fneg` | `Bitcast(Xor(Bitcast f, 0x80000000))` as `OpFNegate f` in place (142 of 230 in fb7de124) | spirv-val on the 4 programs; unit test |
| `fneg2` | as `fneg` for any u32 source (cbuf word, phi): one more `OpBitcast`, then `OpFNegate` (222 of 230) | spirv-val; unit test. **Not in the exe built for the A/B** (committed after it; needs one more build) |
| `emptyif` | the SH1 empty-selection fold (`empty_if_select.h`) for every module | spirv-val on 4 programs |
| `nonan` | drops `SignedZeroInfNanPreserve` (a test of its cost; not exact for NaN/signed zero) | spirv-val |
| `nocontr` | drops `NoContraction` (upper bound for FMA fusing; last-bit differences) | spirv-val |

Unit test: `python -I -B engine/tests/test_spirv_polish.py --cxx clang++` (llvm-mingw first on PATH). Branch `refactor/shaderq`, worktree
`E:\OOT\HeyListen-wt\shaderq`, commits 1963bc165 and bc42adff6. Build of the first commit: `E:\OOT\HeyListen\build\s5\bin\shaderq` (277 s).

## Measurements, RTX 5070, Market `market-spin` (`market-mid` save), 100% render, dlss=0 upscaling=0 resolution=1 hdr=0 vsync=0 frame_rate_limit=6, `RX_VK_PASS_TIMING=2`

Speed lease (priority 4) granted 21:47 after STEP2P and STEP1; slot b with the shaderq build and slot a's options file with those values (restored).
One run of each arm re-compiles its new modules in the driver (fps 1-40 the first time): those runs are thrown away; shown, the runs with fps over 55
(n = 1 or 2 per arm; 3 reps were launched, the first of each arm is the compile). Ms a frame per program, serialized (PT2), mean of the blocks after warm-up:

| arm | all | pass | dispatch | 1a7482c0 | fb7de124 | d8180bd8 | 7b8eefac | 17c69696 | 46c14f8e | 3427a1db | c254a02b | ffb53ed1 | 48ed5183 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base (rep 3 / rep 2) | 7.38 / 7.78 | 3.70 / 3.90 | 1.75 / 1.83 | 0.094 / 0.099 | 0.193 / 0.203 | 0.124 / 0.131 | 0.046 / 0.043 | 0.044 / 0.041 | 0.098 / 0.103 | 0.073 / 0.076 | 0.059 / 0.063 | 0.073 / 0.076 | 0.053 / 0.057 |
| fneg (rep 3) | 7.78 | 3.87 | 1.83 | 0.099 | 0.204 | 0.131 | 0.042 | 0.040 | 0.103 | 0.076 | 0.061 | 0.077 | 0.057 |
| emptyif (rep 3 / 2) | 7.22 / 7.80 | 3.43 / 3.86 | 1.86 / 1.83 | 0.103 / 0.099 | 0.214 / 0.205 | 0.137 / 0.131 | 0.047 / 0.044 | 0.043 / 0.040 | 0.107 / 0.101 | 0.080 / 0.076 | 0.063 / 0.061 | 0.080 / 0.076 | 0.063 / 0.059 |
| nonan (rep 3) | 8.28 | 4.11 | 1.94 | 0.104 | 0.217 | 0.138 | 0.043 | 0.042 | 0.108 | 0.081 | 0.065 | 0.081 | 0.059 |
| nocontr (rep 3 / 2) | 7.81 / 8.12 | 3.88 / 4.05 | 1.83 / 1.92 | 0.098 / 0.103 | 0.199 / 0.220 | 0.130 / 0.136 | 0.046 / 0.043 | 0.046 / 0.042 | 0.103 / 0.107 | 0.076 / 0.080 | 0.063 / 0.064 | 0.076 / 0.080 | 0.058 / 0.060 |

Reading: base against itself differs by 5% between reps (the 5070 runs a 1440p pass in 0.1 ms and clocks wander), every arm is inside that. **No
variant is distinguishable from noise on the 5070**, `nonan` and `nocontr` (the two upper bounds) included: the driver there is not limited by what they
remove. Not measured: `fneg2`, any picture check by `RX_VK_SHOTS` (see below), the existing switches `RX_VK_NO_F16`, `RX_VK_FOLD_EMPTY_IF` (covered by `emptyif`),
`RX_VK_LOCAL_PAD` (only the two giant mesh programs, not in Market), `RX_VK_WARP_WIDE` (no-op on a 32-lane GPU), `RX_VK_MESH_CONV`, `RX_VK_FORCE_MESH_FALLBACK`: each
of those is a translator or stamp switch (a prefix in the stamp list) that re-prepares all 31,985 programs per value (55 s on the 5070, minutes on the
3050), and the lease (45 min, 33 of them runs) ended; Market has one mesh program in its top 12 (0.23 ms), so the mesh switches cannot matter here.

## Ranked proposals (ms a frame on the 3050 in Market, estimates; none measured on the 3050)

1. **Host-made range table for the global-memory helper** (P4 #2): -0.1 to -0.3 ms in Market (skinned vertex programs 7b8e/48ed/b89b 0.83 ms with 22% helper
   instructions, the lit fragments' light fetch, compute programs with 112 sites such as ee7764a6 0.38 ms), more in Kokiri and Hyrule. Effort M-L, stamp moves, new binding.
2. **`fneg2` (all sign flips as source modifiers)**: 0 to -0.2 ms (3-4% of fragment instructions if the driver does not already fold them; the 5070 shows nothing). Effort done, S to ship.
3. **`emptyif` for modules above ~20 k words**: 0 to -0.1 ms; shrinks SPIR-V 12% in the big fragments (translation and driver compile time, also a win for cold starts).
4. **Fusing (`nocontr`) and NaN preserve (`nonan`)**: not shippable as they are (exactness); only worth a number if the 3050 shows more than 3%, then a per-program rule (fuse where the result does not feed depth, positions or a comparison) would be the item.
5. Nothing else in the translated shaders: f16, bitcasts, constant buffers, attribute fetch and interpolation are as the guest had them.

Where the 3050's other ms are is not in the shaders: 4.0 ms of compute (153 dispatches, 100 of them 1x1x1 and tiny: latency, owners are the exposure meter and
culling), 0.6 ms of barriers and 2.9-3.1 ms of emulation (`gpu-pass-cost.md`).

## Implemented (behind a switch, default off)

`RX_VK_POLISH` as above, on `refactor/shaderq`. It is the cheapest clear item because it is the A/B vehicle for #2, #3 and #4 at no translation cost; I did **not**
make any of them the default (no gain measured). **Picture checks are still to do** (`RX_VK_SHOTS=E:/dir` with and without `RX_VK_POLISH=fneg2,emptyif`, one scene,
under a slot lease): `fneg` and `emptyif` are exact by construction (same bits), `nonan` and `nocontr` are not.

## Hand-over: runs for the 3050 (through its own session; do not run over ssh)

Builds: `C:\OOT\builds\shaderq\HeyListen.exe` + `hookshot_vk.dll` (the first commit: `fneg`, `emptyif`, `nonan`, `nocontr`, no `fneg2`). For `fneg2` rebuild
`refactor/shaderq` (a build command was refused for me in the last step: `powershell -File build\s5\mkg.ps1 -Root E:/OOT/HeyListen-wt/shaderq/engine -Name shaderq2 -Block -Lift -Pgo ...hookshot_pieces.prof`
under a build lease) and `scp` to the same folder.

Per arm (each arm is a new set of SPIR-V for the driver: **run it once and throw that run away**, then 3 timed runs interleaved with base):

    arms (env): base | RX_VK_POLISH=fneg | RX_VK_POLISH=emptyif | RX_VK_POLISH=nonan | RX_VK_POLISH=nocontr   (| fneg2 after the rebuild)
    each run: RX_VK_PASS_TIMING=2 plus the arm; Market `market-spin`, options dlss=0 upscaling=0 resolution=1 hdr=0 vsync=0 frame_rate_limit=6
    read: "GPU time N ms a frame" lines (the unserialized one) and the PT2 block's programs (1a7482c0 fb7de124 d8180bd8 7b8eefac 17c69696 46c14f8e 3427a1db c254a02b)
    my aggregator: E:\OOT\scratch-shaderq\agg.py <prefix> <arms> (reads build/s5/sq-<prefix>-<arm>-<rep>/game_log.txt)

A gain of 0.05 ms on a program or 0.3 ms of the frame in two of three runs is the bar; the 5070's own run-to-run spread is 5%.

## Not verified / limits

* Everything above the table is reading, not measurement. The helper's weight in Market's fragments is from the call structure (5 sites, 4 candidates), not a timestamp.
* The 5070 table has n=1-2 clean runs per arm (time ran out after the compile runs); noise 5%.
* Whether NVIDIA's compiler folds the integer sign flips is unknown; a `nvdisasm` of one compiled program would answer #2 in minutes.
* Slot b's `hookshot_vk.dll` and `HeyListen.exe` are now the shaderq build (the previous exe is saved as `E:\OOT\scratch-shaderq\b-orig.exe`, the dll was not); options restored.
