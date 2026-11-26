# SPEC1: specialising shaders on rarely-changing constant buffer values (study, in progress)

Status: done, NO-GO (see Results). Method, stop state and the results below.

## Method (as built)

* Translated shaders read constant buffers as UBOs (`c<N>` variables, set 0): constant offsets as `OpAccessChain(0, imm)` + `OpLoad`
  (scalar or vec4 + extract), a few indexed. c0/c2 are the driver banks, c1 the program's own constants, c3+ the game's uniform buffers.
  Storage-buffer / global-memory reads (pointers held in cbufs) are not specialisable this way.
* `HL_SPEC1_STATS=<dir>` + `HL_SPEC1_PROGS=<prefixes|all>` (+ `HL_SPEC1_AFTER=<s>`): per program, stage and cbuf, the distinct values (up to 8) of every
  word and the distinct whole blocks per draw/dispatch (engine/gpu/vk/vk_spec1.cpp, hooks in vk_draw.cpp). `HL_SPEC1_DUMP=<dir>` writes every shader
  module as `<hash>.spv`; `HL_SPEC1_OVERRIDE=<dir>` makes a module from `<hash>.spv` instead (hand-specialised variant, for timing with RX_VK_PASS_TIMING=2).
* `tools/spec1/spv_cbuf.py report|special`: constant-offset reads, branches/loops whose condition depends only on cbuf words (taint analysis),
  and a rewrite of loads of one-value words into constants (then `spirv-opt -O`; checked valid with spirv-val on a fake-stats case: 1,371 -> 1,274
  instrs plain -O; the fake-constant version 1,239).
* Static look at older dumps (E:\OOT\scratch-shd1\base, not current hashes): 1a7482c0 frag: 103 constant-offset cbuf loads (51 words, c3/c4), 22 branches, 2
  on cbuf words only; d8e59341 mesh: 200 loads (54 words), 65 branches, 0 on cbuf words only; 43ec86f3 mesh: 982 loads (279 words, 214 in c5), 530 branches,
  37 on cbuf only, 14 loops (none on cbuf); 918adef1 mesh: 310 loads, 228 branches, 0 on cbuf only. First read: the control flow of the mesh programs is
  data-driven (culling, SSBO), so branch folding on cbufs looks small; the gain, if any, is constant math.

## State at stop (2026-11-23 reboot)

Done: code committed on `perf/spec1` (switches, tool); build `build/s5/bin/spec1` made (693 s full recompile) and copied into slot a; slot a's shader
cache prepared for it by `warm.sh --slot a` (205 s, "warm: done"). Half done: the first stats run (kokiri) failed because the cache was not prepared
(never reached play); runs for hyrule and market were refused by runguard (RAM < 4 GB free). No stats, no timings yet.
Next command (after the reboot; leases are gone, ask again): 
  `bash build/s5/machine.sh request mainpc spec1 slot 40 1`, wait, then edit T in `E:\OOT\scratch-spec1\stats_runs.sh` and run it (three scenes kokiri-idle / hyrule-idle /
  market-spin with their savelib saves, HL_SPEC1_STATS dirs under E:\OOT\scratch-spec1\st-*, SPIR-V dump to E:\OOT\scratch-spec1\spv). The slot cache may need `bash build/s5/warm.sh --slot a` again (HL_SLOT=a). Then:
  analyse with `python -I tools/spec1/spv_cbuf.py report <spv> <stats> --stage K`, make `special` variants + spirv-opt into an override dir, and time orig / opt-only / specialised
  with RX_VK_PASS_TIMING=2 and HL_SPEC1_OVERRIDE on a speed lease (5070). Delete E:\OOT\scratch-spec1\spv afterwards (20 k files if the whole cache is dumped).
Leases/scripts used: build ticket (released by mkg), slot a ticket 20261123-122022-spec1-slot-63d2 (released at stop); scripts stats_runs.sh (finished), warm.sh (finished).

## Results (2026-11-23)

Runs: kokiri-idle, hyrule-idle, market-spin, HL_SPEC1_AFTER=15 s, then ~90 s of draws per scene (a few thousand draws per program).
Share of constant-offset cbuf words that held ONE value in the whole run (words 1-value / read, kokiri; hyrule and market within a few words):

| program, stage | instrs | cbuf words (1-value / read) | read sites on 1-value words | branches on cbuf words only (of them one-value) |
|---|---|---|---|---|
| 1a7482c0 frag | 1,786 | 39 / 51 | 88 / 103 | 2 (2) |
| 918adef1 mesh | 6,185 | 66 / 79 | 338 / 387 | 20 (19) |
| 918adef1 frag | 8,952 | 89 / 142 | 205 / 315 | 1 (1) |
| 43ec86f3 task | 5,199 | 22 / 122 | 22 / 332 | 53 (53) |
| 43ec86f3 mesh | 20,734 | 133 / 279 (market: 40) | 518 / 982 | 37 (37; market 15) |
| 43ec86f3 frag | 5,730 | 58 / 111 | 114 / 216 | 0 |
| d8e59341, 739acd67, d905f52b (all stages) | 5.5k-8.9k | 27-59 / 54-115 | 42-116 / 150-213 | 0 |
| 4f0c0b40 (hyrule) task | 5,845 | 24 / 137 | 19 / 345 | 55 (55) |

So 50-85 percent of the words read are invariant in a scene, but the control flow of d8e59341, 739acd67, d905f52b and of most frag stages does not depend on cbuf words at all. Branches that do are in the task/mesh stages of 43ec86f3, 918adef1, 4f0c0b40, 1a7482c0. In market, 43ec86f3 has only 40 of 279 words constant (the mesh stage varies per draw), so a specialisation there would need a variant per value set. Loops: 14 in 43ec86f3 mesh, none with an exit on cbuf words.

Hand specialisation (tools/spec1 `special` + spirv-opt -O, stats from the kokiri run), SPIR-V instructions (result-id ops):
orig / spirv-opt only / specialised: 43ec86f3 mesh 17,222 / 11,863 / 10,880 (-8 % vs opt); 43ec86f3 task 3,814 / 3,349 / 2,716 (-19 %); 918adef1 mesh 4,735 / 3,572 / 1,892 (-47 %);
918adef1 vert-side 6,413 / 4,923 / 5,063 and frag 6,739 / 5,494 / 5,551 (+3 %: nothing to fold); 43ec86f3 frag 4,417 / 3,660 / 3,704; 1a7482c0 frag 1,371 / 1,274 / 1,288.

GPU time on the RTX 5070 machine, slot lease (not a speed lease: the queue was hours long, a game ran in the other slot, so noise is about +-3 %), kokiri-idle,
RX_VK_PASS_TIMING=2, mean per frame over 10-12 reports: 43ec86f3: orig 0.109 / 0.103 ms (two runs), opt-only 0.101, specialised 0.092 ms (-10 to -15 %, about 0.012 ms);
1a7482c0: 0.114 / 0.109, 0.107, 0.110 (no change); d8e59341 (not overridden, control): 0.376 / 0.361, 0.353, 0.375 (noise +-4 %). 918adef1 was not in the top-20 programs in that scene, so no time. Picture not compared.
Whole-frame GPU: a few ms; the best case gains about 0.012 ms (0.2 %) per frame on the machine where it is cheapest to measure.

## Go / no-go: NO-GO as a general optimisation

* The costly programs (d8e59341, 739acd67, d905f52b) have no cbuf-only branches, so specialising can only fold constant math; their instruction counts barely move.
* The programs with foldable branches (43ec86f3, 918adef1) cost 0.1 ms of the frame; even the best measured case saves 10-15 percent of that.
* Cost of a real implementation: a variant per observed value set (a 64-bit hash of the invariant words), compile off-thread, pipeline-cache growth (5.8 GB cache already), a fallback to the generic module while a variant compiles (a stutter source), and a correctness risk when a "constant" changes (scene, time of day).
* On the 3050 the driver's gain could be larger than on the 5070 but the programs are the same and their share of the frame is the same order; it was not measured (no 3050 slot).

If revisited (only for a GPU-bound 3050 case in a single heavy scene), the plan: 1) 1 d: runtime invariance tracker per (program, cbuf) with a "stable for N draws" gate, reusing vk_spec1 counters; 2) 2 d: in-engine SPIR-V rewriter (port of spv_cbuf.py special, C++) + spirv-opt-like folding of constants and dead branches (or spirv-tools linked) with a unit test; 3) 2 d: variant cache keyed by (module, value hash), async build, generic fallback, de-specialise on change; 4) 1 d: 3050 timings by pass; 5) 1 d: picture checks on the 3 scenes. About 7 days for a result expected at 0.1-0.5 percent of GPU time; not recommended.
