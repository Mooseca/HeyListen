<!-- Copyright (C) 2026 Sacrappy -->
# GPU11: the GPU time that does not shrink with the render resolution (RTX 3050)

Branch `perf/gpu11` (worktree `E:\OOT\HeyListen-wt\gpu11`, from main c79bee6f6, perf/pass1 merged in for its pass-map labels and
`RX_VK_PASS_TIMING_TOP`). Scratch `E:\OOT\scratch-gpu11`. Lease name `gpu11`.

## Final summary

- **What the fixed GPU time is** (RTX 3050, 1440p, PASS_TIMING=2, matrix60): Kokiri 10.1 ms of 17.4, Hyrule 10.6 of 17.0, Market 11.7 of 18.9
  (50% is the lowest render level with the upscaler off: 33% is drawn at 50%). Largest: the one-draw foliage/grass mesh passes (Kokiri
  d8e59341 1.50 ms, Hyrule 4f0c0b40 1.08 + d905f52b 0.53; 81% mesh stage), the volumetric fog compute (ee7764a6 0.40-0.45 + 27ee9883
  0.30-0.38 + 1e2fcee3 0.07), our write-back 0.39-0.43, cc627640 0.36, the game's barriers 0.31-0.40, the meter 0.20, the upload buffer
  0.47-0.65, meshconv 0.12-0.15. Table below.
- **Levers measured**:
  - `RX_VK_MESH_DIRECT` (mesh attributes straight to the outputs): -0.05 ms on d8e59341, about -1% of the passes; pictures right; off
    (not worth a shader-stamp move alone).
  - Volumetric fog: the two big programs ping-pong two image sets by frame parity, so a dispatch-level half rate is wrong (staggered:
    haze gone; copied: white-out). **Fog off** (RX_VK_SKIP_PROG on the three) is clean in pictures and gives, one run a cell: Kokiri
    +3.2%, Hyrule +2.7%, Market +4.0% at 100%; -0.6 to -1.1 ms of GPU time (matrix62). A candidate "volumetric fog: on / off" option.
  - Depth/colour mesh twins share their meshlet lists but not their per-vertex work; the depth twin costs 5% of the colour pass: a shared
    geometry stage is not worth it, and the compute path (the no-mesh fallback) costs 0.5 ms more GPU than native mesh (matrix63).
  - With our upscalers the game's network is replaced, not run (source); the 3050 run could not start DLSS to confirm.
- **Nothing is on by default.** Commits on `perf/gpu11` (bb5c4a460 .. this one).

## State

- [x] worktree, perf/pass1 merged (labels `dw/latez/blend/cl/vrs`, `RX_VK_PASS_TIMING_TOP`, switches VRS / LOAD_CLEAR / SHADOW_SHIFT off).
- [x] ranked table on the 3050 (matrix60, build gpu11c = main + this branch's switches, all off): below. Logs on the 3050 in
      `C:\OOT\pc3050s-out\gpu11\` (game_log of each run), the 600-present blocks copied to `E:\OOT\scratch-gpu11\m60\*-block.txt`,
      tables made by `E:\OOT\scratch-gpu11\maptable.py` (`table60.txt`, `table60M.txt`).
- [x] `RX_VK_MESH_DIRECT` (mesh attributes straight to the outputs, no workgroup copy): pictures right, 3050 pass ms -0.05 (d8e59341)
      to -0.18 (all passes); fps not measurable with the measurement alias (see below). Kept off.
- [x] `RX_VK_GPU11_MESH_PAD`: +4 KB of workgroup memory slows 43ec86f3 by 63% on the 3050 (0.286 -> 0.465 ms), d8e59341 not at all;
      +14 KB lost the device on the main PC (past NVIDIA's 28 KB mesh shared-memory limit) and not on the 3050.
- [x] volumetric fog (coordinator's request): `RX_VK_PROG_EVERY` written; the fog ping-pongs two image sets by frame parity: the staggered
      half rate loses the haze, the `:c` copy (gpu11e) whites the picture out. Only "fog off" is offerable; matrix62 measures it.
- [x] main PC: gpu11e pictures of the copied half rate (list4, `r4`): white-out. 3050 matrix62: fog plain / staggered / off measured.
- [x] studies 1 and 2 (coordinator): twins, compute path (matrix63: costs more), upscaler (source; the 3050 DL run did not start DLSS).
- [x] tests: run_all 512 passed, 3 failed, 55 skipped (test_nup_paths, test_nup_read_name, test_renderer_new_handler: known here;
      the earlier test_drawn_page_map failure fixed); SWITCHES regenerated. No lease held, nothing of mine running on either machine.

## Crashes of my runs

- Main PC slot b, run `q1` of list2 (gpu11c, Kokiri, `RX_VK_GPU11_MESH_PAD=3584`, started 16:44:15 local): **device lost** at 16:45:04,
  `E:\OOT\scratch-gpu11\r2\q1.log`. It belongs to that arm's switch: 3584 words (14 KB) on top of the 14.3 KB copy pass NVIDIA's
  28 KB mesh shared-memory limit. Its numbers are void. Its crash record is `E:\OOT\slots\b\bug-reports\pending\crash-20261124T154504Z.txt`:
  moved by the coordinator to the scratch-crater folder pending-gpu11 (with the unclean records of d1, started 16:42:19, and e1, 16:45:10:
  harness ends, no device loss in their log tails). That
  device loss also made slot b's program cache start empty for the next runs (a2, d2: "0 program keys", prepared again, fps 0: void).
- The 3050's Q1 with 3584 (matrix61, before the correction) did not lose the device (32.8 fps): marked as the old value, not used.
- No other run of mine ended in FATAL / device lost (logs r1, r2, r3). The harness-killed runs' "unclean" records of my slot a list
  (16:46-17:12) were moved to `E:\OOT\scratch-gpu11\bug-reports-slot-a\`.

## Resolution levels available

`resolution=6` (33%) is drawn at 50% with the upscaler off: the log says "Render resolution: 33% chosen, drawn at 50% with Upscaler 0"
(3050, `Kr6`). So the lowest level here is 50%, and fixed = (4 x ms(50%) - ms(100%)) / 3 (ms = fixed + pixel share x pixel part).

## Ranked fixed GPU cost, RTX 3050, 2560x1440, PASS_TIMING=2 (serialized: shares count; the 3050's unprofiled "GPU time" lines say 16.9 ms Kokiri, 16.6 Hyrule, 18.0 Market at 100%)

Totals (ms a frame, 100% / 50%): Kokiri 17.39 / 11.90 -> fixed 10.1; Hyrule 16.99 / 12.20 -> fixed 10.6; Market 18.90 / 13.55 -> fixed 11.7
(`table60.txt`, `table60M.txt`). By kind, Kokiri fixed: passes 5.22, dispatches 3.21, barriers 0.48, write-back 0.39, upload buffer (rbrefresh 0.17
+ msync 0.15 + barriers 0.15) 0.47, meshconv 0.12, events/ubupd 0.06. Hyrule: passes 5.88, dispatches 2.93, barriers 0.47, write-back 0.42,
upload buffer 0.53, meshconv 0.15. Write-back is down from 1.14 (23 Nov) to 0.39-0.42 ms with WBL1 merged.

| Rank | What (program / span) | Kokiri 100% / 50% | Hyrule 100% / 50% | Market 100% / 50% | What it is |
|---:|---|---|---|---|---|
| 1 | mesh pass `d8e59341` (1 mesh draw, 128 v/p, no task) | 1.500 / 1.314 | 0.258 / 0.234 | 0.573 / 0.549 | the foliage's colour pass (shots `r1\k1b`: without it the leaves are dark silhouettes); 81% of it is the mesh stage (rasterizer discard `Kd`: 1.50 -> 1.22) |
| 2 | other one-draw mesh passes | 43ec86f3 0.282 / 0.262, 89ca750f 0.240 / 0.215, 51183fe7 0.227 / 0.214, d905f52b 0.115 / 0.101 | 4f0c0b40 1.084 / 0.969, d905f52b 0.531 / 0.377, d4abbcb4 0.136 / 0.124, 51183fe7 0.119 / 0.114, 3b8c07f2 0.082 / 0.078, 89ca750f 0.075 / 0.073 | d4abbcb4 0.125 / 0.123, 89ca750f 0.125 / 0.123 | grass and foliage (`r1\k2`: 43ec/89ca/5118 skipped = no grass tufts on the rocks) |
| 3 | dispatch `ee7764a6` (8x9x12 / 6x9x12) | 0.400 / 0.403 | 0.436 / 0.434 | 0.452 / 0.444 | volumetric fog, 48x36x48 volume (coordinator, from the IR) |
| 4 | dispatch `27ee9883` (16x9x12 / 12x9x11), then `1e2fcee3` | 0.339 / 0.348, 1e2fcee3 0.070 / 0.071 | 0.298 / 0.293 | 0.371 / 0.379 | volumetric fog, 96x72x88 volume, and its pass after |
| 5 | write-back copies | 0.407 / 0.394 | 0.421 / 0.419 | 0.413 / 0.425 | ours (WBL1 on) |
| 6 | dispatch `cc627640` (6 x 2x1x1, 60 us each) | 0.362 / 0.363 | under the top 80 | under the top 80 | 128 threads of serial code, global helper 72 x 8 |
| 7 | the game's barriers (120-147 a frame) | 0.332 / 0.327 | 0.307 / 0.304 | 0.402 / 0.395 | GPUOV2's `RX_VK_BARRIER_HAZARD` covers them |
| 8 | dispatch `9dc98871` (mma, 64x36) at 100%, `72ba090c` (mma, 54x30) at 50% | 0.425 (A1, matrix61) / 0.288 | - / 0.287 | - / 0.288 | the game's upscaling network: another program per resolution, not fixed |
| 9 | dispatch `435a0138` (1x1x1, 16x16 threads) | 0.204 / 0.204 | 0.203 | 0.206 | the exposure meter's sum: one workgroup |
| 10 | `755a777a` (1x1x1, 11-59 a frame) | under the top 80 | 0.236 / 0.235 | under the top 80 | latency |
| 11 | upload buffer: rbrefresh + msync + barriers (kinds, fixed) | 0.165 + 0.154 + 0.149 | 0.179 + 0.185 + 0.167 | 0.220 + 0.230 + 0.197 | ours (readback protocol) |
| 12 | the other dispatches: `ab7699ee` 0.16, `383a5669` 0.12 (Kokiri), `b6122162` 0.16 (Hyrule), `09cc9a93` 0.11 (Market), indirect ones 0.05-0.11 each | rest of the 3.2 ms of dispatch | rest of 2.9 | rest of 3.1 | GPU-driven culling for the mesh passes and the like |
| 13 | meshconv | 0.122 / 0.121 | 0.152 / 0.151 | 0.121 / 0.117 | ours |

## The mesh passes (program cache, `meshinfo.py`)

Every hot mesh stage runs 32 threads a workgroup and declares 96-128 vertices and primitives. `d8e59341`'s mesh: 128/128, 10 vec4 outputs
a vertex (20 KB) + indices 1.5 KB, and 14.3 KB of workgroup memory: our copy of the stage buffer (`isbe_attributes` 12.8 KB = 25 lines x
128 vertices, `isbe_map` 1.5 KB), which the epilogue copies into the outputs (`emit_spirv_mesh.cpp`). The same for `4f0c0b40`, `89ca750f`
(13.3 KB), `918adef1` (13.3 KB), `43ec86f3`/`d905f52b`/`739acd67` (9.2 KB, 96/96).

`RX_VK_MESH_DIRECT=1|2` (in the stamp) / `RX_VK_GPU11_DIRECT=1|2` (the same, out of the stamp: mesh programs then bypass the program
cache) writes each attribute straight to its output through a function (`gpu11_mesh_direct_write`) and leaves the copy at one word.
Mode 1 sets the counts to the maxima in the prologue and gives primitives past the program's count no area; mode 2 keeps the epilogue's
count. 3050, Kokiri 100%, PASS_TIMING=2 (matrix61, blocks in `E:\OOT\scratch-gpu11\m61`):

| arm | all ms | d8e59341 | 43ec86f3 | 89ca750f | 51183fe7 |
|---|---|---|---|---|---|
| A (plain) x2 | 17.54, 17.47 | 1.511, 1.515 | 0.286, 0.286 | 0.240, 0.250 | 0.228, 0.228 |
| D (direct 1) x2 | 17.31, 17.48 | 1.460, 1.459 | 0.280, 0.280 | 0.230, 0.232 | 0.225, 0.231 |
| E (direct 2) x2 | 17.23, - | 1.451, 1.469 | 0.276, 0.279 | 0.229 | 0.226, 0.229 |
| Q (pad +4 KB) x2 | 17.75, - | 1.512, 1.499 | 0.465, 0.463 | 0.244, 0.247 | 0.230, 0.231 |

So the workgroup copy costs 0.05 ms on d8e59341 (1.511-1.515 against 1.451-1.469) and 0.006-0.02 on the others; occupancy matters (43ec86f3 +63% with 4 KB more) but the
programs sit below the cliff as translated. fps runs (no PASS_TIMING): Kokiri A 50.1, 49.7, 49.6 / D 47.4, 47.7, 48.1; Hyrule A 50.2, 49.6, 49.2 / D 47.7, 46.6, 47.0
(matrix61.txt): the D arm is slower because of the measurement alias (mesh programs re-translated outside the cache: gaps between
recordings 2.1 -> 3.2 ms), not a GPU cost; a stamped build (`RX_VK_MESH_DIRECT`) is needed for a fair fps A/B. Pictures (main PC, `r1\dk1`,
`r1\dh1`): right. Verdict: all passes 11.44 (A) against 11.26-11.36 (D, E) ms, about 1%, off; not worth a shader-stamp move alone.

## Upscaling network with our upscaler on (study 2)

From the source (`vk_draw.cpp` `temporal_stand_in`, `fsr3` stand-in, `off_stand_in`): with DLSS, FSR 4, FSR 3.1 or Off the gameplay
network's dispatch (9dc98871 at 100%, 72ba090c at 50%, the other per-share networks by shape) is replaced: our upscaler writes the
network's output image, and the network itself is not dispatched. Its output image is the one used. So there is nothing to skip
when our upscaler is on; with the game's own network (dlss=0, the N ini) it is the anti-aliasing and costs 0.42 ms at 100%.
matrix63 part 1 (dlss=1, resolution=4, PASS_TIMING=2) could not check it: the log says "Render resolution: 50% chosen, drawn at 50% with
Upscaler 0" and has no NGX or temporal line (DLSS did not start in that slot), and 72ba090c ran (0.287 ms): the game's own network,
as with dlss=0. A run with DLSS really on (its runtime files in the slot) is still to do; the source answer above stands until then.

## Volumetric fog (coordinator's request, 24 Nov)

Programs: `27ee9883` (96x72x88 volume, 12x9x11 groups of 8x8x8), `ee7764a6` (48x36x48), `1e2fcee3` (12x9x1, the pass after 27ee9883).
`RX_VK_PROG_EVERY=<key prefix>:<n>[:<phase>][:c],...` (vk_draw.cpp `prog_every_skips`, beside RX_VK_SKIP_PROG's dispatch test), with
`RX_VK_PROG_EVERY_LOG=1` (images written and sampled, per frame).

What the log says (main PC, `r3\f0b.log`, `r3\f2b.log`): the images are the same guest images every frame (not cleared, not made again),
but `27ee9883` and `1e2fcee3` **ping-pong two sets of three 128x72x96 images by frame parity**: on even frames 27ee9883 writes set A
(0x1145a70000, 0x1146132000, 0x1146644000) and 1e2fcee3 reads A and writes B (0x114570f000, 0x1145dd1000, 0x1146493000); on odd frames the
other way round. `ee7764a6` writes the same three images every frame (64x36x96, 64x36x96, 64x36x48).

Pictures (main PC, 2560x1440, slot a, `E:\OOT\scratch-gpu11\r3\`):
- `f0b\` plain, Hyrule Field turning (market-spin inputs on the hyrule-field save): the haze in the distance.
- `f2b\` staggered half rate (27ee9883:2:0, ee7764a6:2:1, 1e2fcee3:2:1): **the haze is mostly gone** (crisp far hills): the frames read a
  set that the skipped program would have written. Not usable.
- `fx\` all three skipped ("fog off"): no haze, nothing black, undefined or flashing; `gx\` (Lost Woods) the same: no ground mist, the
  greens darker and more saturated. `g0\` Lost Woods plain, `g2\` staggered.
- `h2f`, `h0f`, `g2f`, `g0f`: flash detector (RX_VK_FLASH, the sensitive one in Lost Woods: DIFF 12, CELLS 20): no one-frame flash in any.
- `:c` (gpu11e, `r4\c2\`, Hyrule turning, all three on even frames, 1e2fcee3's three written images copied over the three it sampled):
  **a white-out**: dense white fog over everything past a few metres (`r4\c2\vk_008100.png`). The copy feeds the integrated set back
  where 27ee9883 keeps its own history, and the volume runs away. Not usable either; no fps measured for it.
- Verdict: the fog's two passes are a temporal pair with history in the other set; a correct reduced rate needs to know which image is
  history and which is output (reading the programs), not a dispatch-level skip. What can be offered now is **"fog off"**
  (RX_VK_SKIP_PROG on the three: pictures `fx`, `gx` clean, no haze or mist) with the 3050 numbers of matrix62's O arm; matrix62's F arm
  (staggered) measures the cost of a picture that is wrong (haze gone), its numbers are not a "half rate" option.

### Fog off on the 3050 (matrix62, build gpu11d, one run per cell, fps from play + 10 s; `C:\OOT\pc3050s-out\matrix62.txt`, logs in `C:\OOT\pc3050s-out\gpu11d\`)

P plain, F staggered half rate (picture wrong: haze gone), O fog off (RX_VK_SKIP_PROG=53509044401d78d2,27ee9883,ee7764a6,1e2fcee3).
fps / unprofiled "GPU time" ms:

| scene, render | P | F | O | O against P |
|---|---|---|---|---|
| Kokiri 100% | 49.69 / 16.5 | 50.37 / 16.3 | 51.29 / 15.9 | +3.2%, -0.6 ms |
| Kokiri 50% | 67.30 / 11.1 | 66.80 / 10.7 | 66.99 / 10.3 | -0.5% (noise; CPU-bound there), -0.8 ms |
| Hyrule 100% | 49.82 / 16.4 | 50.83 / 16.1 | 51.17 / 15.6 | +2.7%, -0.8 ms |
| Hyrule 50% | 64.26 / 11.8 | 66.13 / 11.4 | 67.61 / 11.0 | +5.2%, -0.8 ms |
| Market 100% | 47.08 / 17.8 | 48.11 / 17.4 | 48.95 / 16.7 | +4.0%, -1.1 ms |
| Market 50% | 58.48 / 12.5 | 59.66 / 12.0 | 60.03 / 11.6 | +2.7%, -0.9 ms |

Pass ms (Kokiri 100%, PASS_TIMING=2, blocks in `E:\OOT\scratch-gpu11\m62`): all 17.36 (P) / 17.35 (F) / 16.67 (O); dispatches 4.156 / 3.810 /
3.392; ee7764a6 0.401 / 0.200 / -, 27ee9883 0.339 / 0.160 / -, 1e2fcee3 0.070 / under the cut / -. One run a cell: the fps column is a
screen, not a confirmation (the short A/B rule: three rounds to adopt).

### Do the depth pass and the colour pass run the same meshlets? (study 1, coordinator 24 Nov)

From `RX_VK_LOG_MESH_PROGS` (main PC, `E:\OOT\scratch-gpu11
1\k0.log`, `h0.log`): every colour mesh pass has a depth twin that draws
from **the same indirect argument record** (so the same meshlet list and count) with **another mesh program**:

| colour (cost on the 3050, 100%) | depth twin, same indirect address | mesh code colour / depth | twin's cost |
|---|---|---|---|
| d8e59341 (Kokiri 1.500) | 879fe82ef602ab53, 0x117a4d6000 | bca1ac88 / 66c2d017 | Kokiri 0.078 |
| 4f0c0b40 (Hyrule 1.084), task d91e4f46 | 3cb7682790143836, 0x117898e000, same task | aee23868 / c5f8c2c8 | Hyrule 0.059 |
| 43ec86f3, task 8fb3abac | 8a8304edb7bdf4bf, 0x117896a000 | 7d1fd77e / e850379c | under the top-80 cut |
| 51183fe7, task 1813f9ce | 8e2f7af4245747ef, 0x1178982000 | 29b9ad64 / 2063bc93 | under the cut |
| 89ca750f | 5ba7cf23d6857836, 0x117caa0000 | 1c45a2b3 / 49f1f836 | under the cut |
| d905f52b | 6afe3fda3f4b1752, 0x117982a000 | 9bb0c329 / 8f81c159 | under the cut |
| 3b8c07f2 | f93c1d64658c850b, 0x117d03c000 | 6b175f10 / d1dab91d | under the cut |

The two mesh stages differ: the depth one is 13-16 k words with 3 outputs (position + one vec4, 5.6 KB) and 5.1 KB of workgroup memory;
the colour one is 42-43 k words with 11 outputs (22 KB) and 14.3 KB (`meshinfo.py`). The depth pass costs 5% of the colour pass (0.078
against 1.500; 0.059 against 1.084). So the meshlets are the same but the per-vertex work is not: a shared geometry stage would save at
most the depth twins' own cost (Kokiri 0.078 + the twins under the cut), and would add a buffer of 10 vec4 a vertex written and read
twice. Not worth building. The colour stage itself is the cost: 81% of d8e59341 is the mesh stage (`Kd`). Whether the compute path
(the no-mesh fallback: compute into records, a plain vertex stage) runs that stage cheaper on the 3050 than the native mesh stage is
matrix63's part 2 (RX_VK_MESH_SHADERS=compute against native, 3050, build gpu11d, `C:\OOT\pc3050s-out\matrix63.txt`, logs and blocks in
`C:\OOT\pc3050s-out\gpu11e\`, copies in `E:\OOT\scratch-gpu11\m63`), each arm after its own --prepare-shaders:

| | compute path | native mesh |
|---|---|---|
| Kokiri PASS_TIMING all ms (unnamed glue) | 17.84 (2.52) | 17.34 (0.08; a network copy overlapped this run) |
| Kokiri passes / dispatches | 8.99 / 4.14 (d8e59341's draw 0.255: its mesh work moved into the unnamed fallback compute) | 11.34 / 4.14 |
| Hyrule PASS_TIMING all ms (glue) | 17.37 (2.98) | 16.81 (0.10) |
| Kokiri fps (no PASS_TIMING) | 45.15, 50.34 (GPU time 16.9, 17.1) | 50.16, 50.01 (16.5, 16.4) |
| Hyrule fps | 46.34 (16.5) | 50.52 (16.3) |

The compute path costs 0.5-0.56 ms more GPU a frame and Hyrule -8% fps: running the meshlet work as compute plus a plain draw is not
cheaper on the 3050 than the native mesh stage. The study's "no" stands for both the shared stage and the compute path.

Density / distance controls: not established. The mesh-only colour programs (d8e59341, 89ca750f, d905f52b, 3b8c07f2) take their meshlet
list from an indirect record written by the culling dispatches; the task programs (43ec86f3, 4f0c0b40, 51183fe7) cull per meshlet against a
coarse depth grid and keep everything when bit 4 of c3 word 2320 is set (`RX_VK_MESH_NOCULL`'s note): that is a "draw all" switch, not a
distance. Naming a LOD bias or cull distance needs the culling dispatches' uniform blocks read at run time (RX_VK_LOG_PUSH /
RX_VK_PEEK_PROG on the indirect-writing programs), which was not done.

## What is left (not done here)

- The one-draw mesh passes are the biggest fixed block (Kokiri 1.5 + 0.9 ms, Hyrule 1.1 + 0.9 ms at 100%) and 81% of d8e59341 is its
  mesh stage (`Kd`). They are the game's foliage and grass, drawn twice (a depth pass, then d8e59341's colour pass with depth writes off).
  The translation's own share is small (the copy: 0.05 ms; G3/P5 already took the helper). What could still move them: a foliage /
  grass density or distance option (a picture change: needs the game's LOD inputs, not studied), or the range table of
  `shader-efficiency.md` (#2, never built: the helper's per-candidate math in the mesh and compute programs).
- `cc627640` (6 dispatches of 2 workgroups, 60 us each) and `435a0138` (one workgroup, 0.20 ms) are serial, latency-bound compute that
  leaves the GPU idle; only overlap (no barrier between them and unrelated work) would help, which ASYNC1 and GPUOV found blocked by
  the game's barriers.
- Volumetric fog: "off" is the only safe reduced setting found; a half rate needs the two programs' history/output roles read from
  their code first.
- Our own fixed work: write-back 0.39-0.43, upload buffer (rbrefresh + msync + barriers) 0.47-0.65, meshconv 0.12-0.15, part of the game's
  barriers (GPUOV2): the readback/write-back protocol streams own these.

## Closed attempts not redone

ASYNC1 (async compute), SPEC1 (specialisation), SHD1 (spirv-opt), BC7C, PASS1's LOAD_CLEAR and SHADOW_SHIFT (3050 matrix47: within
noise, Kokiri 48.8-49.9 all arms), VRS on the many-draw passes, GPUOV2's barrier hazard folding (`RX_VK_BARRIER_HAZARD`), WBL1
(write-back put off: merged, auto on the 3050), G3/P5 mesh helper hoist and size-aware inlining (on by default).

## Builds

gpu11a (pad), gpu11b (+ MESH_DIRECT), gpu11c (+ measurement aliases; stamp X), gpu11d (+ PROG_EVERY; same stamp as gpu11c), gpu11e
(+ PROG_EVERY copy; same stamp). On the 3050 in `C:\OOT\builds\gpu11{a,b,c,d}`. Every translator change moves the shader stamp: the
first start prepares every shader (on the main PC two 110 s runs lost each time; the 3050 pilot runs `HeyListen.exe --prepare-shaders`).
