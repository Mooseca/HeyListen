# GPU pass cost and CPU cost by module: what step 1, 2 and 3 are worth (STEP0, 2026-11-21)

Step 0 of `refactor-plan.md`, second deliverable. Two tables: where a frame's GPU time goes by kind of pass (and what our translation
adds), and where its CPU time goes by module; then the candidates for step 2 (direct rendering) ranked by ms and the order of the steps.
No engine change: existing diagnostics only.

## Sources and their limits (read first)

| Source | Machine, scene | What it gives | Limit |
|---|---|---|---|
| `HL_PROFILE_LOCAL=1 HOS_PERF_REPORT=1 RX_VK_PERF_INTERVAL=60 HL_PROFILE_BATCH_S=10 RX_VK_PROF_FINE=1` (`profile_local/*.json`, the game's per-pass GPU timestamps, **not serialized**) | main PC, RTX 5070, Market `market-spin`, 100% render, 150 s run, 7 batches = 33 s of Market, 2,367 frames | per pass (kind, key, count, ms) and per dispatch (program key) | the report keeps the 24 slowest passes of each 10 s batch (`kMaxPasses`), so small passes are cut; one batch file was lost (deleted by mistake while cleaning the slot), 7 of 8 kept; the sampler thread costs 1.1 ms of CPU a frame |
| `RX_VK_PASS_TIMING=1` and `=2` (log block every 600 presents, timestamps around every span, **serialized**: spans add up to more than an unprofiled frame, read the shares) | main PC, Market, Kakariko, Hyrule field | every span by kind (pass, dispatch, barrier, write-back, refresh, mesh conversion, uploads), the 25 slowest spans, with `=2` the 20 programs whose draw runs took longest | 8.2-8.3 ms a frame in Market against the unprofiled 3.5-4.4 ms of GPU: shares only |
| the 3050 logs in `E:\OOT\scratch-step0\3050\` (`100a`, `100b` 100% render, `50` 50%; Market, 1440p) | PC 3050 | "GPU time" lines, "GPU tail", PROF_FINE CPU lines, perf summaries (`parts_ms`) | **no per-pass profile**: no `profile_local/` was written (see "Getting the 3050's per-pass profile") |
| `replay-cost.md` REPLAY1 / DESC1 / ORDER2 (branches `perf/desc-044`, `perf/order2`), `E:\OOT\scratch-trace1\REPORT.md` (WPR) | main PC / PC 3050 | CPU by thread and phase | measured by other streams, cited as is |
| `shader-efficiency.md` (stream P4) | PC 3050, Kokiri and Hyrule field | program keys to what they are, mesh/compute ms on the 3050 | a different scene from Market |

## Getting the 3050's per-pass profile (answer to the coordinator)

The profile is written by `profile_queue()` in `engine/gpu/vk/perf_report.cpp`: a batch **every `HL_PROFILE_BATCH_S` seconds of play
(default 300; accepted range 10-3600)** and a final batch **only at a clean exit** (`profile_queue(true)`), into **`profile_local/` in the
game folder** (next to `HeyListen.exe`, e.g. `C:\OOT\runs\...` there), one file `<unix time>-<n>.json` a batch, only for maps that changed. The
3050's runs lasted 150 s and ended by the harness's kill, so the first 300 s batch never came and no clean exit happened: only
`perf_pending\` (the summaries, every `RX_VK_PERF_INTERVAL` = 60 s) was written. What to run there (no code change, the same 100% render
and options as `100b`):

    HL_PROFILE_LOCAL=1 HOS_PERF_REPORT=1 RX_VK_PERF_INTERVAL=60 HL_PROFILE_BATCH_S=10 RX_VK_PROF_FINE=1   (150 s, Market, market-spin, save market-mid)

then copy `profile_local\*.json` (about 10 s of Market a file) and the log. `HL_PROFILE_BATCH_S=10` is the only addition to the previous
command line. For the pass-by-pass table with program keys, add a second run of 110 s with `RX_VK_PASS_TIMING=2` (log block every 600
presents; adds serialization, so not with the profile run). The tool that sums the files is `E:\OOT\scratch-step0\plagg.py` (local).

## B1. GPU time by kind, main PC, Market (RTX 5070, 100% render, 2560x1440)

Unprofiled frame: 14.0 ms (73 fps with the sampler on), GPU busy 3.5-4.4 ms (`refactor-plan.md`); the GPU is idle for the rest (the
queue picture says 6.25 ms of 14.6 empty between command buffers, 98% of it before an upload command buffer: the replay had not sent more work yet).
The serialized `RX_VK_PASS_TIMING=1` blocks, ms a frame of GPU (shares are what counts):

| Kind | Market 8.32 ms | Kakariko 6.26 | Hyrule field 7.42 | What it is |
|---|---:|---:|---:|---|
| **geometry: render passes** (shadow, main, post, UI) | 4.23 (51%) over 175 spans, 2,322 draws | 3.08 (49%) | 3.86 (52%) | the game's own work, ~24 us a pass |
| **compute: dispatches** | 2.03 (24%) over 168 spans | 1.69 (27%) | 1.93 (26%) | the game's own work; ~100 of the 168 are 1x1x1 or tiny |
| game barriers | 0.51 incl. 0.32 for the game's 141 `nvnCommandBufferBarrier`s | 0.39 | 0.38 | game's own (mostly) |
| **emulation: write-back copies** (`wb`, mirror to guest memory) | 0.47 (10.8 spans, 53 MB) | 0.38 (53 MB) | 0.46 (59 MB) | ours, the readbacks' other half |
| **emulation: readback refresh** (`rbrefresh`, CPU's zero back into the mirror) | 0.18 (27 spans, 5.9 MB) | 0.07 | 0.10 | ours (R1 of the ledger) |
| **emulation: mirror sync** (`msync` scatter, CPU pages to mirrors) | 0.17 (1,337 items, 5.2 MB) | 0.13 | 0.14 | ours |
| **emulation: barriers of the upload command buffer** (`u barrier`, write-back or sync) | 0.19 (127 spans) | 0.12 | 0.14 | ours |
| **emulation: mesh-draw argument conversion** (`meshconv`) | 0.10 (24 spans) | 0.13 | 0.12 | ours (indirect mesh draws) |
| texture upload copies (`xfer`, buffer to texture) | 0.06 | 0.06 | 0.06 | ours (BC/ASTC decode runs elsewhere: not in this table) |
| events, uniform-update copies, pool mirror makes, clears | 0.03 + 0.02 + 0.02 + 0.00 | 0.05 | 0.05 | ours/game |
| **emulation total** | **~1.3-1.8 ms (16-21%)** | ~1.1 (17%) | ~1.3 (18%) | wb + rbrefresh + msync + u barrier + meshconv + the rest |

Not timed at all by these blocks: the present's blit to the window (0.07-0.66 ms on the 3050 log), the renderer's HDR pass and its own
copies, BC/ASTC transcoding passes made elsewhere, clears made by the dry pass on the CPU. "Dry-pass-related" GPU cost is zero: the dry pass
is CPU-only (see B2). **Emulation is a fifth of the GPU's serialized time on the 5070; the other four fifths are the game's own passes
and dispatches.** On the 3050 the "10.8 ms resolution-independent" of the plan is geometry + compute + this overhead; applying the 5070's
shares (an estimate, not a measurement) puts ~2.3 ms of it as emulation, ~2.9 as dispatches and ~5.6 as the geometry passes' vertex/mesh
side. A 3050 profile would replace the estimate.

### Top passes, unserialized (profile JSON, Market, ms a frame, 100% render, 5070)

The 24-per-batch cap cuts the tail; the listed passes sum to 2.65 ms of the frame's ~4 ms of GPU. Kind is the report's heuristic
(`profile_report.h` `pass_kind`: colour+depth is "main", depth only "shadow", colour only with few draws or small is "post"); keys are
`pass_key` (target format, size class, first program) and not program keys.

| Kind | Pass key | ms a frame | a frame | us each | Notes |
|---|---|---:|---:|---:|---|
| main | c9e43b88b6716a41 | 0.341 | 1.0 | 337 | the biggest single pass: the scene's main colour+depth pass, max 1.34 ms |
| main | ef317a5479c11e0b | 0.168 | 0.3 | 536 | every third frame |
| compute | ee7764a6b1ef459c | 0.151 | 1.0 | 152 | grid 8x9x12; 11.8 k SPIR-V instructions, 112 global-memory sites (`shader-efficiency.md`) |
| post | 9151d1cc545e89d3 | 0.146 | 1.0 | 146 | screen effect |
| compute | ab7699ee7f536755 | 0.143 | 1.0 | 143 | grid 4x4x6 |
| compute | 9dc98871eb7fc101 | 0.118 | 1.0 | 118 | the cooperative-matrix ("matrix net", 192 coop-matrix ops) program, grid 64x36x1: the GPU's tensor path, nothing to remove (P4) |
| main | 02c9788dfa1c5fd3 | 0.116 | 1.0 | 116 | |
| compute | 435a0138b9013040 | 0.110 | 1.0 | 110 | **one of the exposure meter's two sum programs**, 1x1x1: pure latency |
| main | 38661608ba66017e | 0.109 | 1.0 | 109 | |
| compute | 09cc9a93a2d7dd81 | 0.104 | 38.6 | 2.7 | 1x1x1, 39 dispatches a frame: latency |
| compute | 27ee9883e2a20323 | 0.104 | 1.0 | 104 | grid 16x9x12, 32 texture ops |
| compute | 612a27de13e44e79 | 0.102 | 16.3 | 6.3 | 1x1x1 |
| main | b624742a9cb7e025 | 0.098 | 16.4 | 6.0 | 16 small passes a frame |
| main | bf87457d0996edb2 | 0.088 | 1.0 | 88 | |
| compute | 755a777ada52677d | 0.087 | 20.2 | 4.3 | 1x1x1, 20 a frame: "latency, not code" (P4) |
| shadow | 154bf4dd0315403e | 0.086 | 10.3 | 8.3 | 10 shadow passes a frame |
| main | 647395d47f52b44b | 0.083 | 1.0 | 83 | |
| compute | aa76b702d5b1ff0d | 0.083 | 3.0 | 28 | |
| main | 85583e00276a14c5 | 0.077 | 0.1 | 561 | every ten frames |
| main | 0b3bf877b1d267b5 | 0.070 | 1.6 | 45 | |
| compute | 26fe0c70ab9fc547 | 0.066 | 1.0 | 68 | grid 80x60x1; one 8 ms spike in 1,523 frames |
| main | b904a551db3bf98a | 0.066 | 1.0 | 68 | |
| compute | b612216258832b9c | 0.061 | 1.0 | 62 | |
| compute | abccf81b45c5eb50 | 0.039 | 0.6 | 61 | indirect dispatch |
| | by kind (listed only) | main 1.25, compute 1.17, post 0.15, shadow 0.09 | | | |

By programs (`RX_VK_PASS_TIMING=2`, serialized, Market, draw runs a frame, longest first): `fb7de12443c80159` 0.228 ms (16.7 draws),
`d8180bd8c6ecc77b` 0.144 (a 2560x1440 full-screen pass with 6 sampled textures; 0.49 ms in Kokiri on the 3050), `d8e59341cf4f629c` 0.114 (a
mesh+fragment program, 1.41 ms in Kokiri on the 3050), `46c14f8ee79c5349` 0.109 (62 draws), `1a7482c0ec9991ea` 0.108 (full-screen fragment,
1.07 ms Kokiri / 0.92 Hyrule on the 3050), `636eed4d5000d1c0` 0.086, `3427a1dbefd5e02c` 0.084, `ffb53ed102dd9908` 0.084 (483 draws at 0.17 us:
instanced, cheap), `48ed51830b1d8fb7` 0.066, `262c53789ef5dda1` 0.064, `3b4b12921b5d7d1c` 0.062, `c254a02b6a76abe8` 0.061 (14 runs). **No program
or pass takes more than ~0.34 ms of the 5070's frame: the 5070 is CPU-bound, and no single pass is the lever there.** The 3050 is the GPU
judge, and `shader-efficiency.md` (Kokiri and Hyrule field, 3050) already says where its ms are: mesh pipelines 7.2 ms (Kokiri) and 4.5
(Hyrule) of 20 ms, compute 2.2-2.4, vertex+fragment 2.9-3.5, fixed dispatch costs 120 dispatches x 36 us.

### The 3050, what the logs hold (Market, 100% render, 1440p)

| Number | 100% render (`100b`) | 50% render (`50`) | Reading |
|---|---:|---:|---|
| frames/s | 41.7-44.4 | 50.6-53.4 | |
| draws / dispatches / passes / barriers a frame | 2,113-2,176 / 147-162 / 164-167 / 174-175 | 2,116-2,146 / 135-145 / 161-164 / 168-170 | same scene |
| "GPU time" a frame | 17.5-18.1 ms | 12.6 ms | the plan's 18.1 / 12.6, so ~10.8 ms is resolution-independent (5.5 ms in the pixel work at 100%) |
| longest submission | 4.4-4.5 ms | 2.8 ms | |
| uploads | 0.5-0.7 ms | 0.5 ms | texture uploads and decodes |
| gaps between recordings | 4.7-4.9 ms | 6.5 ms | the GPU idle between pieces (waiting for the replay) |
| GPU tail before the late waits | 13.7-14.1 ms busy | 8.05-8.16 ms | what a readback waits for (ledger) |
| summary `parts_ms`: game / render / gpu_wait | 0.66 / 8.5 / 14.2 | | per frame of a 22.7 ms frame |
| `submissions` (replay thread wall, PROF_FINE) | 13.7 ms (13.9 per frame), of it dry pass 3.25, segments' recording and wait 7.5, 17.9 small buffers recorded whole 1.5, memory work 0.86 | | CPU, below |

## B2. CPU time by module, one table (ms of CPU a frame; bold = on the critical path)

Main PC = Ryzen 7 7800X3D (REPLAY1, Market, 11.9-12.8 ms frames, 70-72 ms of CPU a frame, ~6 cores busy); 3050 = i5-10400F (24.3 ms
frames; ORDER2's counters from PROF_FINE, and the WPR trace `TRACE1`). Replay phases are summed over the threads that do them.

| Module (what a native module would own) | Main PC ms | PC 3050 ms | Step | Source |
|---|---:|---:|---|---|
| Game: BaseProcExecutor, ModuleSystemWorker, main thread, NavMesh workers | ~27 / ~15 / 3.2-4.0 / ~2.5 (~50 in all) | 4.8 cores busy; the game's threads' ready-queue wait 3.7% only | 3 (visibility job ~4.4 of it), later | REPLAY1 section 1; WPR |
| Visibility / culling job (`f_800998a0` and its readbacks R4) | ~4.4 (the plan) | not split | 3 | `refactor-plan.md`, ledger R4 |
| Readback waits (summed over threads) | 0.9 (Market) / 4.2 / 3.6 | ~16 (389 of 3000 calls x 1.5 ms) | 1 | ledger |
| **Replay: per-draw work in the segment workers** (draw idx 5.64 us a draw x 2,313 = 13.06; 14.5 with all draw sections) | 14.5 | 20.3 (draw idx 9.63 us x 2,112) of 25.8 in the workers | 2 | REPLAY1 section 2; 3050 PROF_FINE |
| - of it descriptors (6.2 pushed a draw) | 7.4 | | 2 | REPLAY1 |
| - of it texture slots (kept 3.94 + resolved again 1.22 + view/sampler misses 1.7) | 3.8-3.9 | | 2 | REPLAY1, DESC1 (no gain from `HL_DESC_PATCH`) |
| - of it program lookup (memo on) | 1.4-1.5 | | 2 | DESC1 |
| - of it user uniform buffers, storage buffers, vertex/index binds, pipeline bind | 1.4 / 0.9 / 0.9 / 0.7 | | 2 | REPLAY1 |
| **Replay: the dry pass** (serial; also writes guest memory: 963 report counters, clears, render-condition reads) | **2.2** (ops 1.69; 43 depth clears 0.65) | **3.25-3.5** | 2 | REPLAY1, ORDER2, 3050 PROF_FINE |
| **Replay: the replay/order thread's own segment + waits for the workers** | **3.76 + 0.95 whole buffers** (submissions 7.7 ms wall) | **7.5 (+1.5 whole buffers); order thread 9.0 of 24.3 ms (37% of the critical path)** | 2 | REPLAY1, TRACE1 |
| Replay: commands, dispatch, programs, textures, pipelines, queue submit | 4.2 / 0.8 / 1.5 / 1.1 / 0.4 / 0.2 | queue submits 14 a frame 0.57 ms | 2, 4 | REPLAY1, ORDER2 |
| Replay: capture, mirror sync, write-back diff | 0.12 per submit (210 pages); sync 0.45 wall; write-back 52.8 MB a frame, 7 MB a submit compared, in the order thread's 2-2.5 | `capture copy/hash worker` 1.27 ms on the path | 1, 2 (they disappear with the pools they serve) | REPLAY1, TRACE1 |
| **Presenter** (game thread that submits and presents) | 4.6-5.5 | **4.2, plus 2.4 woken from timers/DPC**; waits ~10.5 ms for the order thread's replay | 2 | TRACE1 |
| Order thread ("mkw_vk order") | 2.0-2.5 | **9.0** (9.7 CPU, 46% of it in the driver and syscalls) | 2, 4 | REPLAY1, TRACE1 |
| Replay workers (4-5 threads) | 9.9-12.1 | idle 85% | 2 | REPLAY1, TRACE1 |

Not oversubscribed anywhere (3050: 3.7% ready-queue wait). Point fixes inside the current architecture gave nothing measurable
(`refactor-plan.md`: DESC1, ORDER1, WAIT1, PRESENT1, GAMEWAIT1).

## Candidates for step 2 (direct rendering), ranked by measured ms

Ranked by the CPU and GPU time that the module removes **on the 3050**, because that is where the frame is both CPU-path-bound
(order thread 9 ms) and GPU-heavy; main-PC ms in brackets.

| Rank | Candidate | What it removes | Measured ms (3050 / main PC) | Basis |
|---:|---|---|---|---|
| 1 | **The draw loop as records** (draw idx + descriptors + texture slots + uniform binds, per draw in the workers, with the decode of every draw of the ~2,100 a frame) | the per-draw replay: the 25.8 ms of worker CPU (20.3 draw idx) and, because the order thread records 84% of `run_submit` itself, most of the 9 ms critical path | 20.3 (draw idx) of 25.8 worker ms; critical path 7.5 own segment / 14.5 [main PC] | REPLAY1 and 3050 PROF_FINE; TRACE1 |
| 2 | **The dry pass** as a native pass over the records (no state walk twice; counters, clears and render-condition reads moved with it) | the serial 3.25-3.5 ms (2.2) in front of every segment | 3.25-3.5 / 2.2 | ORDER2 (analysis: not a pure walk) |
| 3 | **Mesh/task pipelines on the GPU side** (the drawing of the geometry itself: the program text is the game's, but the *translated* global-memory helper and mesh-argument conversion are ours) | GPU: meshconv 0.10 + the helper's cost: `shader-efficiency.md` measures 0.4-1.1 ms a program for the three biggest mesh programs | ~1-3 / 0.10 (meshconv) | `shader-efficiency.md` (Kokiri, 3050); `meshconv` span here |
| 4 | **Write-back, refresh and mirror syncs of the pools the module takes over** | GPU `wb` 0.47 + `rbrefresh` 0.18 + `msync` 0.17 + u barriers 0.19 = ~1.0 ms (5070, Market, serialized), and the CPU diffs (7 MB a submit) | ~1.0 / 1.0 (shares, 3050 not measured) | PASS_TIMING block above |
| 5 | **Tiny dispatches** (1x1x1 programs: 39 + 20 + 16 + 1 a frame, 4-6 us each; the meter's two sum programs among them) folded or batched by their owning module | GPU latency ~0.4 ms (5070) of fixed cost | ~0.4-1 (120 dispatches x 36 us on the 3050 = 4.3 ms in all, of which the tiny ones are most) | profile JSON; `shader-efficiency.md` |
| 6 | Full-screen/pixel work (d8180bd8, 1a7482c0, da7a7ab2: ~2.0 ms on the 3050) | not a module: resolution-dependent, stays | 0 | `shader-efficiency.md` |

The two largest GPU items, the main scene pass (c9e43b88, 0.34 ms on the 5070) and the game's compute (ee7764a6 0.15, ab7699ee 0.14), are
the game's own work that no step changes; direct rendering removes the **overhead around them** (items 1-4), not their shaders.

## Recommended order of modules, with expected ms

| Order | Module | Expected gain | Why this place |
|---:|---|---|---|
| 1 | **Readbacks**: R1 exposure (same side on the GPU), then R2/R3 (`0x40` ring, `0x2000` pair) one frame late, R6 cut grass with its particle job | removes the late-fix wait: 0.9-4.2 ms summed on the 5070, **~16 ms summed on the 3050** (the CPU waits 13.8 ms of GPU tail); on the frame's chain the measured bound is +17% (`NO_READBACK_WAIT`, castle-move, 5070). Also drops `rbrefresh` 0.18 and part of `wb` 0.47 ms of GPU | It is the enabler: while a read waits for the previous frame's GPU work the CPU phase cannot overlap it, and on the 3050 gpu_wait is 14.2 of 22.7 ms. Also the only step that deletes a bug family (#93, white flashes, #50) |
| 2 | **Draw loop + dry pass as records** (descriptors, texture slots, uniform binds, dry pass; then Vulkan draw lists) | order thread 9 ms of the 24.3 ms 3050 critical path (37%); 14.5 ms summed per-draw CPU and 2.2-3.5 ms dry pass; GPU emulation ~1.3-1.8 ms (16-21%) | The largest CPU block by far, and where the 3050's critical path sits. Ordered after 1 because the records' write-back protocol touches the same pools |
| 3 | **Visibility job** (~4.4 ms CPU) and its culling readback R4 | ~4.4 ms of CPU (game threads), 0.02 ms of wait | The largest remaining translated CPU block; the loop that calls it goes native with it |
| 4 | Thin NVN layer for what stays | residual: the remaining small buffers (17.9 recorded whole, 1.5 ms), queue submits (0.57 ms), the present path | After 1-3 it is a small share |

Ordering by total ms alone puts step 2 first (about 30 ms of CPU summed on the 3050, 14.5 + 3.5 + 7.5 + overhead) and step 3 second (4.4),
step 1 third on the 5070 (0.9-4.2) but first on the 3050 (~16 summed, and the enabler). The recommendation keeps the plan's order because
step 1 is cheap per module and unblocks overlap; step 2's gain has to be re-measured on the 3050's own per-pass profile (recipe above)
before the first draw-list module is built.

## Not verified

- The 3050's per-pass GPU times (not collected, recipe above); the emulation share on the 3050 is the 5070's, applied.
- The 5070 profile covers 33 s of Market with the 24-passes-per-batch cap; passes below ~0.04 ms a frame are not in it.
- Pass keys of the JSON profile (target format, size, first program) are not program keys; the table maps them to programs only where
  `shader-efficiency.md` and the `PASS_TIMING=2` list agree (marked). The other passes are named by kind and number.
- The CPU table mixes streams' measurements (REPLAY1 with `HL_THREAD_CPU`, TRACE1's WPR, the 3050's PROF_FINE) taken on different builds
  of the same day; they are cited, not re-measured here.
