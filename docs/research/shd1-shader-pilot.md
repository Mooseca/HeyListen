<!-- Copyright (C) 2026 Sacrappy -->
# SHD1: does an optimizing shader translation pay? (2026-11-22)

**Question.** Could an offline optimizing shader translation, shipped in the builder, give large GPU gains on the RTX 3050? That PC is GPU-bound at about 15-20 ms a frame at 2560x1440.

**Audit** (77,234 stages of a slot's program cache)
- NoContraction sits on 90.5% of float add/sub/mul/div.
- Sign flips and absolute values are done on the bits: 6.4M XORs, 26.5% of float arithmetic, against 201 FNegate.
- Bit casts are 10.5% of instructions.
- Constant banks are UBO arrays, 96% read with a constant index.
- There is no bindless: textures are rebound per draw (CPU-side; BIND1 follows this up).
- Control flow is structured.
- f16 is negligible, so a native Ampere frontend (3-4 months) would not pay.

**Measurement** (3050, Task 30, 36 runs). The 20 most expensive programs (12 draw, 8 compute) were overridden through RX_VK_SPV_OVERRIDE in five variants:
- spirv-opt perf;
- spirv-opt without inlining;
- the sign peephole;
- NoContraction removed;
- sign + contract.

Results, three scenes (Market, Hyrule, Kokiri), two runs each:
- **fps:** unchanged within noise in every arm. The perf arm was 2-5% worse in Hyrule.
- **Per program:** the top program, 1a7482c0 (about 1 ms, full screen), did not change. d8180bd8 and the compute programs did not change (±0.01 ms). 918adef1 and 43ec86f3 improved by 1-4% at best. The only clear case was 701ae221 in Hyrule: -20% in perf, noinline and contract, about 0.2 ms, with no fps change.

**Conclusion.** The NVIDIA driver already does what spirv-opt and these peepholes do. An optimizing translation tool is NOT worth building for GPU time; the gate was ≥ 0.5 ms a frame, and the gain was about 0.2 ms in one scene. The switches (RX_VK_SPV_DUMP, OVERRIDE, KEYS, LOWER_STATS, FOLD_SIGN, FOLD_CONTRACT) stay off, as diagnostics. The 3050's GPU time lies elsewhere: the GPU idling while it waits for upload command buffers (SUBQ1), write-backs, and fixed-cost passes.

Data: C:\OOT\pc3050s-out\shd1\ (on the 3050, matrix30.txt) and E:\OOT\scratch-shd1.
