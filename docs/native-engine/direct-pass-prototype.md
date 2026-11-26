# Direct rendering of one heavy pass: what step 2 really buys (STEP2P, 2026-11-21)

Step 2 of `refactor-plan.md` ("direct rendering of the heavy passes: no capture, no mirror, no NVN replay for them") is a large
commitment. This note measures one heavy Market pass before it is made: which guest functions record it, what the replay and the
GPU spend on it, what data it reads, what a direct path would hand the back end, and what that is worth, per pass and summed.
Branch `refactor/step2p`, worktree `E:\OOT\HeyListen-wt\step2p`. Machine: main PC (RTX 5070, Ryzen 7 7800X3D), scene
`market-spin` (save `market-mid`), `dlss=0 upscaling=0 resolution=1 hdr=0 vsync=0`, no frame cap ("Render resolution: 100% chosen,
drawn at 100% with Upscaler 0" in every log), 110 s runs. Guest addresses and sizes only; nothing of the game is quoted.

## The answer in short

1. **The heavy scene passes are small in draws and cheap in replay CPU.** Each of the three candidates is 54-63 draws and
   0.22-0.29 ms of replay CPU a frame (serial, one thread, 3.5-5.4 us a draw). The frame is ~2,350 draws, 7.3 ms of CPU in `draw()`,
   over ~170 passes (~500 pass keys): the three scene passes are 11% of it, the top five passes 22%, the top fourteen 35%.
2. **What step 2 removes is not what these passes cost.** Their vertex and index data are static (no mirror sync of their own),
   the NVN decode is small (the state-setting ops together ~0.8 ms of the replay's 12.7 ms of ops), the dry pass only walks their state. The
   cost is `draw()` itself: 4-5 us a draw, of which at most 15% (the program and pipeline lookups) is pre-resolvable by a native
   producer with no change to the data, and at most ~50% with the texture-slot, uniform-range and storage work done natively too;
   the rest (descriptor pushes, pipeline and descriptor binds, vertex and index binds, the draw) any Vulkan path pays.
3. **The data question says "not without a native writer".** In the pass 647395d4 **95% of the uniform binds (4.7 a draw, 2.9 KB
   each) are not final when the draw is recorded** (the per-draw blocks sit in ring pools of 1 MB or less and are written by
   translated code after the recording ends); 81% in c9e43b88. Inline uniform data, no capture and no mirror for them need the code
   that writes those blocks to be native and to run before the emission: a native draw loop (brick D of `direct-emission.md`), not a
   native producer of records. The pass's vertex and index data need no change (static); the capture's per-frame cost is already
   0.12 ms a submit.
4. **Ceiling measured** (the draws of a pass after its first left out of the replay altogether, which no real path reaches): the
   serial replay's median frame falls by 0.35 ms (647395d4), 0.25 (c9e43b88), 0.15 (ef317a54) and 0.65 ms for the three together
   (13.25 -> 12.6 ms, 5%); 3.8 us a skipped draw, as the `draw()` timing says. A real direct path keeps 50-85% of that cost.
5. **Verdict.** Per scene pass, direct emission is worth **0.03-0.15 ms of replay CPU a frame, about 0 ms of GPU**; the three
   together 0.1-0.4 ms of CPU, under 3% of a frame, a third to a half of it on the critical path. Summed over every draw it is 1-3.6
   ms of CPU (about 1 ms of the critical path, the figure of REPLAY1's lever 2) and, on the 3050, at most ~0.5 ms of GPU (mirror
   syncs, upload barriers, mesh-argument conversion: only for data a native writer makes inline). **No prototype of a per-pass direct
   path was built**: the evidence above says it cannot deliver without the draw loop that owns the per-draw uniform writers, and
   what it could deliver is smaller than the run-to-run spread of an fps round. The note gives the design (section "Design") and
   what to do instead (section "What to commit to").

## Tools built (all off by default; `engine/gpu/vk`, `engine/host/nvn_native.c`; commits on the branch)

| Switch | What it does |
|---|---|
| `HL_DIRECT_PASS_MAP=1` | The NVN layer tags each recording with the guest address that began it and the one that called it into its caller (`NOP_MAP` records, outside the accounting the game reads, as `HL_UBO_CHECK`'s are; `rx_nvn.h` changes, so a first run after the build re-predicts the pipeline notes). The serial replay attributes every `draw()` to that pair and to its pass key (the profile's: target format, size, first program), with the fine sections' time and counts and the mirror sync it caused. Logged every 120 frames: totals, by target family, by recorder, and per pass (top 14). Exact only when one thread replays: `RX_VK_PARALLEL=0`; `RX_VK_PROF_FINE=1` for the sections |
| `HL_UBO_CHECK=1` with the map | each pass's uniform binds, equal to / different from what the replay reads as submitted, per pass and per recorder (heavy: 12-15 fps, timings of that run are not used) |
| `HL_DIRECT_PASS=<pass key prefix,...>` | the ceiling: the draws of the named passes after their first are left out of the replay altogether (no program, pipeline, descriptors or Vulkan commands). The picture is wrong; measurement only. Exact in the serial replay; in the parallel replay it left out about twice the draws it should (323-349 a frame against 172: cause not found), so only the serial numbers are used |
| `HL_THREAD_CPU=1` | CPU a frame by thread (cherry-picked from `diag/replay1`) |

    bash build/s5run.sh --slot <s> --save build/s5/savelib/market-mid <tag> market-spin HL_DIRECT_PASS_MAP=1 RX_VK_PROF_FINE=1 RX_VK_PARALLEL=0

then read the `hl pmap:` lines of `game_log.txt`. A recorder is a return address: the guest function is the one that contains it
(`f_<address>` of the lifted code; a throwaway index of the function starts does it).

## 1. The map: who records the frame's draws, and the candidates

The frame, 2,300-2,450 draws, by recorder (the serial run `s2p-map2`, an average block; "pre-recorded list" = a recording made once
by the function `0x80293890` and called into the caller's by `CallCommands`; the recorder column is where the call was made):

| Draws a frame | us a draw | Recorded by | Native today |
|---:|---:|---|---|
| 800 (35%) | 2.5 | the item body `0x80084de0`, draws made in its own loops (key 0x80 / 0x40 / 0 and the variants' inlined submission) | no (the item is translated; its leaves are native) |
| 347 + 195 | 1.7 / 3.6 | pre-recorded lists called from the item body (`+0x2838`, `+0x4860`) | the preparation `0x8008fc00` before them is native (`HL_GFX_PREP`) |
| **341** (15%) | 4.9 | pre-recorded lists called from the key-0xa0 draw function `0x8008d640` | native on its plain entries with `HL_GFX_VAR=1` (default 0): 89% of its 588,000 entries in the var1 run |
| 177 | 2.1 | the key-5 function `0x8008b3e0` | no |
| 156 + 65 | 4.3 / 1.8 | the sister item body `0x8007ad40` (kind 3) | no |
| 61 | **14.1** | the sub-mesh submission `0x80078fc0` | yes (`HL_GFX_DRAW`, default on) |
| 67 | 2.4 | the pass body `0x8006cd60` | no |
| 62 | 1.7-4.1 | the drawables' methods `0x800955a0` | no |
| 17 | 5-10 | `0x80296540`, `0x800715e0`, `0x806650d0`, `0x802eb390` | no |

The three passes the brief names, with their producers and what they cost:

| Pass | Draws a frame | Replay CPU a frame | us a draw | Recorded by | 3050 GPU (`100c` profile) | 5070 GPU |
|---|---:|---:|---:|---|---:|---:|
| c9e43b88 | 63 (1.03 passes) | 0.28 ms | 4.4 | 50-70% (by run) the key-0xa0 function's lists, the rest the item body's own draws | 0.453 ms | 0.341 |
| **647395d4** | **54 (1.00 passes)** | **0.29 ms** | **5.4** | **100% pre-recorded lists called from the key-0xa0 function `0x8008d640`** | **0.467 ms (0.9 a frame)** | 0.083 |
| ef317a54 | 61 (0.5 a frame) | 0.22 ms | 3.6 | the item body's own draws and the key-0xa0 lists | 0.905 ms (0.5 a frame) | 0.168 |

**The pass chosen: 647395d4.** Producer already native or nearly so: all of its draws go through one function, the key-0xa0 draw
function, whose plain entries (kind mask, state, model class, pre-recorded list, instances 1) are native behind `HL_GFX_VAR=1`
(`hl::bridge::KeyLoopBridge`, checked entry by entry with 0 mismatches in `direct-emission.md`/`gfx-record-job.md` section 13-14),
and whose preparation is native by default. With `HL_GFX_VAR=1` (run `s2p-x-var1`) the map shows its 54 draws a frame all emitted by
the native loop (the call-site tag becomes the item body's, where the native code returns). c9e43b88 is half the item body's own
inline draws, which no native code covers; ef317a54 runs every second frame.

The second most expensive pass of the frame by CPU is **a3667776** (10 draws a frame, 0.32 ms, **31 us a draw**, recorded by the
sub-mesh submission `0x80078fc0`): a texture-heavy character draw, where a resolved packet would pay most per draw (slot misses 0.12 ms).

## 2. What the replay does for 647395d4 every frame

One pass (1.00 passes a frame: no split by hazards), 54 draws, one render target set (2560x1440 colour + depth), 0.29 ms of `draw()`.
A draw, in us (`RX_VK_PROF_FINE` sections of the pass, 26 blocks of 120 frames):

| Section | us a draw | What it is | Pre-resolvable by a native producer |
|---|---:|---|---|
| textures | 1.08 | 10 slots kept, 3 resolved again a draw (slot misses 0.24 us) | partly: handles are the producer's; views depend on registrations |
| descriptors: bind + push | 0.79 | 28 descriptors built, 17 pushed a draw (changed writes only) | no (Vulkan's) |
| program lookup | 0.64 | the program picked from the bound program object | **yes** (a material's program is fixed) |
| user uniform buffers | 0.53 | 8.6 range calls a draw | no for per-draw blocks (they are read as submitted), yes for final ones |
| bind pipeline | 0.40 | 0.55 binds a draw | no |
| vertex + index binds | 0.26 | 0.92 stream binds, 1.0 index bind a draw: static mirrors | no |
| storage buffers | 0.22 | 4 descriptors a draw | partly |
| pipeline lookup | 0.15 | half of the draws take the "fast pair" | **yes** |
| push constants, dynamic state, hazards+pass, draw call | 0.13 + 0.09 + 0.07 + 0.04 | | no |
| other (checks around the draw) | ~1.0 | | partly |

- **Dry pass:** it walks the state only (a draw is `s.samples_passed += 16`, nothing else); for 54 draws it is a few us.
- **Barriers:** `hazards+pass` 0.07 us a draw; the pass is one Vulkan render pass.
- **Decode:** the ops that only set state (everything but draws, dispatches, clears, report counters and barriers; each under 0.15 ms a
  frame, so not listed by the op table) total ~0.8 ms of the replay's 12.7 ms of ops (`ops of the whole on one thread`: draws 8.8, dispatches 1.0,
  depth clears 0.8, mesh draws 0.3, report counters 0.3, barriers 0.2).
- **Per frame, whole replay** (serial): 2,350 draws, 7.34 ms of `draw()` (3.1 us a draw): textures 1.51 (0.74 of it slot misses),
  program lookup 0.81, user uniform buffers 0.71, bind descriptors 0.69, bind pipeline 0.56, vertex+index 0.52, storage 0.25, pipeline
  lookup 0.22, banks 0.11. Program + pipeline lookups 1.03 ms (14%); with textures, uniform and storage ranges and banks 3.6 ms (49%).

## 3. What the capture and the mirrors serve for it

| Data | How the pass gets it | Per-frame cost attributable to the pass |
|---|---|---|
| vertex and index streams | the pre-recorded lists name pool addresses (static pools): mirrors held | **0** (the pass pays no mirror sync: "mirror sync 0.0 KB in 0.0 copies") |
| uniform blocks, 4.7 binds a draw (8.6 range calls), 2.9 KB each | ring pools of 1 MB or less, mirrored; bound ranges served from the mirror (`uniform ranges copied into the stream` 0.00 a draw) | the pools' mirror syncs are paid once a submission by the first draw that binds the pool (the frame: 2.3-2.7 MB in 306-315 copies, paid mostly in small target families: 128x128 372 KB, 256x144 586 KB, 80x44 1,058 KB) |
| storage buffers, 4 a draw | the programs' tables and lists, by address (GPU-written or static) | write-backs where the CPU reads (step 1's) |
| textures, 10 slots a draw | handles in deferred arrays read at the submit; images uploaded at first use | the upload command buffer, not the pass |
| driver banks | 1.0 bank call a draw, 29 bytes filled | in `draw()` (above) |
| capture | pages written since the last submit, 0.12 ms and 0.8 MB a submit (REPLAY1) | none specific |

**Uniform blocks final at the bind (`HL_UBO_CHECK`, binds counted under the next draw's pass; per pass, `s2p-ubo2`):**

| Pass | Binds a draw | Equal at the bind | Different | Bytes a bind |
|---|---:|---:|---:|---:|
| **647395d4** | 4.7 | **4.9%** | **95.1%** | 2,922 |
| c9e43b88 | 4.1 | 18.9% | 81.1% | 2,885 |
| ef317a54 | 3.1 | 56.9% | 43.1% | 1,246 |
| 0b3bf877 (instanced, 446 draws) | 1.6 | 59.5% | 40.5% | 1,007 |
| fef828dd, 154bf4dd, 4e1998ea | 2.8 / 3.0 / 5.2 | 3.4% / 8.6% / 2.5% | 96.6% / 91.4% / 97.5% | 3,954 / 4,346 / 2,648 |

By recorder, the same: the item body's own binds 91% equal (they bind final per-frame blocks); the recorder `0x806002e0` (a function that
begins its own recordings, not read further) has the biggest population, 3.4 million binds a run, 62% different, all between the end of
the recording and the submit. **The writer of the per-draw blocks of 647395d4 was not identified**; the check
says they are written after `EndRecording` and before the submit. `HOS_POOL_TRAP` on one `0x22` ring pool between a recording's end
and its submit would name it.

## 4. Design: direct emission of this pass, and what it needs

**What is emitted.** Per entry of the key-0xa0 function (native for the plain entries), one record `NOP_PASS_DRAW` in place of the 8-10
records the preparation and the list's inline copy produce today: the program object pointer (as `BIND_PROGRAM`), the render-state key,
the uniform ranges (address, size; or inline bytes), the deferred texture-handle array's address and count, and the pre-recorded list
referenced by its handle and not copied (`CallCommands` without `inline_recording`: `gfx-record-job.md` section 9, "Where it leads").
Written by `RecordWriter` into the command buffer's own segment, in order (`direct-emission.md` 3.1: the pass records into a command
buffer translated code is recording, so a second stream is not an option); the entries the native loop declines (11% of them with
`HL_GFX_VAR=1`: masked, methods, culling clusters) stay NVN calls in the same stream.

**What the back end does with it.** `replay()` decodes it into the same `NvnState` fields, so `draw()` and everything it guards
(program readiness, skips, DLSS notes, occlusion, hazards) stay as they are; the record adds a hint (program key, pipeline key) that
`draw()` checks against the stamp of the program object (pointer and stage code addresses) before skipping `program_for` and
`graphics_pipeline`: the 0.8 us a draw of lookups (15% of the pass). A back-end change beyond that (descriptor content cached by
material, resolved texture views, no `NvnState` walk) is brick F of `direct-emission.md`: the pass's 28 descriptors a draw are the
floor of what a Vulkan path without descriptor buffers pays, and DESC1 already showed that caching around them gives nothing
measurable (`HL_DESC_PATCH`: 62-70% hits, no gain).

**The data rule.** Vertex and index data: by address (static, as now). Textures: the game's handles, as now. Uniform blocks, three
classes: final at the bind (equal in every scene): inline bytes (`NOP_UBO_INLINE`, built and clean in `direct-emission.md` section 9;
5% of this pass's binds); **per-draw blocks written after the recording (95% of this pass's): by address, read as submitted through the
mirror, so the capture and the ring pools' mirror syncs stay for them**; blocks a native writer computes before it emits: inline,
which needs that writer (the draw loop) native. "No capture, no mirror" holds for a pass only when every block it binds is of the
first or third class.

**The check (`HL_DIRECT_PASS_CHECK`, not built).** The producer writes both forms in the check mode (the NVN records as now plus the
packet, the packet not executed); the replay compares at each draw what `draw()` built from the NVN records with what the packet
says: program key, pipeline key, descriptor writes (the same `VkWriteDescriptorSet` list), vertex and index binds, dynamic state;
counts equal / different, the first eight differences in full; 0 over a run in each scene is the bar. Pictures: `RX_VK_SHOTS=<drive
path>` with `HL_DIRECT_PASS` off and on, compared shot by shot.

**Why it was not built.** The packet path's gain is the program and pipeline lookups (0.8 us a draw, 0.04 ms for the pass); the data
side that step 2 is meant to remove (capture, mirror, uniform copies) does not belong to this pass: the vertex and index data cost
nothing now, and the uniform blocks cannot be inlined without their writer. Building the packet path to measure 0.04 ms would
confirm what the sections already say.

## 5. The ceiling measurement (`HL_DIRECT_PASS`, main PC, whole machine under a speed lease, `s2p-m-*`)

Serial replay (`RX_VK_PARALLEL=0`, where the skip is exact; the presenter is the replay thread). `HL_THREAD_CPU=1` in every run. fps is
the run's mean; **p50 frame time is the stable number** (the fps mean carries the run's stalls: 1% lows of 5-15 fps).

| Condition (draws left out a frame) | fps | p50 ms | Presenter CPU a frame |
|---|---:|---:|---:|
| base, 2 runs | 69.6 / 70.3 | 13.3 / 13.2 | 12.14 / 10.96 |
| 647395d4 (57) | 72.2 | 12.9 | 10.95 |
| c9e43b88 (59) | 66.5 | 13.0 | 11.59 |
| ef317a54 (67) | 68.0 | 13.1 | 11.43 |
| all three (172-174), 2 runs | 67.6 / 75.0 | 12.8 / 12.4 | 10.28 / 10.04 |

The base's two runs differ by 0.1 ms at p50 and 1.2 ms of presenter CPU (the CPU figure is noisy: the game's threads share cores
with the replay). Reading at p50: 647395d4 -0.35 ms (6.1 us a skipped draw), c9e43b88 -0.25 (4.2), ef317a54 -0.15 (2.2), the three
-0.65 (3.8): the median frame falls by about the passes' own `draw()` time, as the map says it should. The fps means are inside
the spread (one round each). Default parallel replay (`pbase`/`pD`, 2 runs each): p50 11.3 / 11.2 -> 11.0 / 10.7 ms, but those
runs left out 323-349 draws a frame instead of 172, so they overstate the effect and are not used.

GPU, 5070 (`RX_VK_PASS_TIMING=2`, `s2p-x-pt2`): GPU time 7.8 ms a frame serialized, 0.7 ms of uploads; the three passes are below the
25 slowest spans (each 0.08-0.34 ms in the unserialized profile). On the 3050 the three passes are 0.453 + 0.467 + 0.905 ms a frame
(ef317a54 runs every other frame) of the 17.7 ms GPU frame: **the game's own geometry**, which direct emission does not touch; the
emulation's share of the 3050's GPU (`rbrefresh` 1.0, `wb` 0.9, `msync` 0.25, upload barriers 0.2, `xfer` 0.2, `meshconv` 0.12) is
not in these passes' spans (their mirror sync is paid elsewhere) and belongs to step 1 (the first two) and to the pools' owners.

## 6. Extrapolation: what converting the top N passes would save

By replay CPU (serial, map `s2p-map2`, 26 blocks), draws a frame, and the saving at the low estimate (program and pipeline lookups,
14% of a pass's `draw()` CPU) and the high one (everything a native producer can pre-resolve: lookups, texture slots, uniform and
storage ranges, banks; 49%). The wall effect is the serial replay's; in the parallel replay the draw work is spread over five recorders
and the presenter's own segment, and a third to a half of it reaches the critical path.

| Top N passes by replay CPU | Draws a frame | `draw()` CPU a frame | Saved, low | Saved, high |
|---:|---:|---:|---:|---:|
| 1 (0b3bf877, instanced) | 414 | 0.49 ms | 0.07 | 0.24 |
| 3 (+ a3667776, 647395d4) | 479 | 1.10 | 0.15 | 0.54 |
| 5 (+ c9e43b88, ef317a54) | 604 | 1.59 | 0.22 | 0.78 |
| 10 | ~1,000 | 2.26 | 0.32 | 1.11 |
| 14 | ~1,250 | 2.57 | 0.36 | 1.26 |
| all passes (170 a frame) | 2,350 | 7.34 | 1.03 | 3.6 |

The three scene passes of the brief alone: 0.78 ms of `draw()`, saving 0.11-0.38 ms of CPU. On the 3050, whose frame is GPU-bound
(17.7 ms of GPU in 24 ms), none of this shortens the GPU; its CPU critical path is the order thread (9 ms), of which the replay's
per-draw work is a part.

## 7. What to commit to

- **Do not build step 2 as "a direct path per heavy scene pass".** The three heavy scene passes are 11% of the replay's draw CPU and 0% of
  its mirror work; the per-pass ceiling is 0.15-0.35 ms of a 13 ms frame.
- **If step 2 goes on, its units are producers and writers, not passes**: (1) `HL_GFX_VAR=1` on by default after its picture
  validation (the key-0xa0 function: 15% of the frame's draws, native on 89% of entries, no replay change needed); (2) the **code
  that writes the per-draw uniform blocks** (`direct-emission.md` names the draw loop `0x80255be0` as the largest identified writer of the
  `0x22` pools; the writer of 647395d4's blocks is still to be named), which is the only way inline uniform data, no capture and no mirror for those blocks
  becomes true; (3) the expensive-per-draw producers, where a resolved packet pays most: the sub-mesh submission (14 us a draw, 61 draws,
  0.86 ms) and a3667776 (31 us a draw): their cost is texture slot misses, which is the DESC1/REPLAY1 lever 1 (a resolved-handle table),
  not emission.
- **Step 1 first on the 3050**, as `gpu-pass-cost.md` ranks it: the emulation's 3 ms of GPU is the readback protocol, not the scene passes.

## Hand-over

- Branch `refactor/step2p` from main `1109df5c8`; worktree `E:\OOT\HeyListen-wt\step2p`. Commits: `diag(vk): HL_DIRECT_PASS_MAP ...`, the
  cherry-pick of `HL_THREAD_CPU` (`diag/replay1` 886fecbc1), `diag(vk): HL_DIRECT_PASS, a ceiling measurement ...`, this note with the
  regenerated switch lists, and two test updates. No push, no merge. The measured builds are one commit before the last code change
  (`draw()`'s `HL_DIRECT_PASS` note takes the pass reference instead of asking `pass()` again; same behaviour). Slot b holds `step2p-map3`.
- Files: `engine/gpu/render/rx_nvn.h` (`NOP_MAP`, `nvn_p_map`), `engine/host/nvn_native.c` (`map_on`, `map_note`, `cmd_rec.tag/call`,
  the call sites in `BeginRecording` and `inline_recording`), `engine/gpu/vk/vk_replay.cpp` (the record's case, the pass-ops list),
  `vk_draw.cpp` (`PmapDraw`, `PmapAgg`, `pmap_report`, `DirectPass`), `vk_internal.h`, `vk_memory.cpp` (`memory_sync_totals`),
  `vk_ubo_check.cpp` (per-recorder and per-pass attribution), `vk_thread_cpu.cpp`.
- Builds: `build/s5/bin/step2p-map3` (main PC, PGO); the same exe and dll are on the PC 3050 in `C:\OOT\builds\step2p\` (a PGO
  build of the main PC's, copied: `pc.sh build` could not be used, `C:\OOT\w63blk` (the lifted work folder `hlbuild_inner.bat` names)
  was not there on 21 Nov, 20:23-21:30). On the 3050: `HL_DIRECT_PASS_MAP=1 RX_VK_PARALLEL=0 RX_VK_PROF_FINE=1` for the map,
  `HL_DIRECT_PASS=647395d4,c9e43b88,ef317a54` for the ceiling; the pass keys are those of the 3050's own profile
  (`gpu-pass-cost.md` B3), so no re-keying.
- Logs and parsing (local, not in git): `build/s5/s2p-map2`, `s2p-ubo2`, `s2p-x-var1`, `s2p-x-pt2`, `s2p-m-*`; `E:\OOT\scratch-step2p\`
  (`pmap.py`, `avg.py`, `topn.py`, `ubo_rec.py`, `sumfps.py`, the function-start index).
- Not verified: the parallel-replay ceiling (the skip counts doubled: cause not found, probably a segment boundary or a second walk of
  the same pass); one run a condition for the single-pass ceilings (two for base and the three together); the 3050's own numbers (only
  the logs of STEP0 and the exe copy); the writer of the per-draw blocks; `HL_GFX_VAR=1`'s picture on the main PC for this pass (its
  run was slow, 23 fps, with the map's serial replay on, not understood: not a validation run). Tests: the switch-list check, the 54 tests
  that read the touched files as text, and a focused set of 22 (`test_native_engine`, the replay, draw, capture, NVN and descriptor
  checks) pass after two were updated (`test_accessor_once`: `draw()` still asks `pass()` once; `test_nvn_host_tables`: the command
  buffer table's typedef line). The full suite was not run: the machine was under timing leases from 21:02 on, and its compiles
  would have disturbed them.
