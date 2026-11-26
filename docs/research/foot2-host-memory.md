<!-- Copyright (C) 2026 Sacrappy -->

# FOOT2 (23 Nov 2026): the host's 18 GB "other" private commit, named

Branch perf/foot2 (worktree E:\OOT\HeyListen-wt\foot2, from origin/main 4b599eb04). Data: FOOT1's tour run f1-A1
(build/s5/f1-A1/game_log.txt, HL_MEM_ACCOUNT=30, HOS_HOST_SPLIT=40,30, RX_VK_LEDGER=30), then FOOT2's own runs (section 4).

## Summary (23 Nov 2026, FOOT2)

- The 18.4 GB "other": 8-9 GB of it is the NVIDIA driver's charge for the VRAM in use (its 64 and 128 MB blocks), which the
  ledger now names ("the driver's blocks for VRAM"); the host's own part is 9.8-9.9 GB in the A arms.
- `RX_VK_PCACHE_RELEASE=1` (off by default) meets the brief on its own: host side 9,764 -> 4,998 MB, no fps loss
  (103.4 -> 116.6 fps), page faults 17.10 -> 15.09 M (-11.8%), page-fault stutters over 50 ms 76 -> 73 (section 4b).
- `HL_MEM_TRIM_ARENAS=<s>` (off by default) takes the driver's arenas out of the working set: working-set mean
  16.3 -> 11.8 GB and RAM available min 911 -> 3368 MB on foot2b (section 3), at about +1.9 M soft faults (the driver touches
  the pages again).
- `RX_VK_BC_CACHE_IDLE_S=<s>` (off by default) is not worth 120 s in a ten-minute tour: it re-transcoded 6.8 GB more than it
  saved and cost 1.2 k more re-transcodes, for 50 MB (section 4).
- Pictures at all sixteen zone changes, cuts arm against the A arm: identical (section 6). Checks: 503 pass, only the three
  known failures (section 7).
- Under a fixed memory hog (3,456 MB in both arms) the release still wins: 101.0 -> 104.6 fps, page faults 16.35 -> 15.26 M
  (-6.6%), page-fault stutters over 50 ms 111 -> 88, host side 9.2 -> 6.3 GB by the driver's 16-64 MB family (section 5b).
  The first hog pair (T8) was invalid: memhog.py's target-free mode gave the release arm a hog twice the size (section 5a).
- **Can the release be on by default? Yes (FOOT3, section 8).** What a tour session builds beyond the precompile, once the notes
  hold the tour, is 378 pipelines (102 graphics + 276 compute) and only 18 of them are compiles the 2.1 GB file did not hold;
  the release's empty cache makes 99 of 383 compile in play (f3n-S1), and FOOT3's play file keeps them (f3n-S2: 25 of 312; 4 of 279
  when the notes have matured), at 20-26 MB a save - a file small enough for this machine's save gate, where the 2.1 GB file's is
  not. The second session's hitches are no worse than the switch-off one's (539/150/4 against 879/283/15 frames over 50/100/500 ms
  in the 60-s warp windows, one 0.2 ms waits block against none). Gameplay does not move in any of the five pairs with frames
  measured (the 20..40 s after each warp: 92.7 against 96.7 fps and 9.52 against 9.46 ms median in the same-hour pair, section 8c);
  the tour's whole-play fps does, both ways (+12.8% release in f4, -5.3% at 05:12 against 05:35), because it counts the loading
  seconds: the switch leaves the play untouched and changes what the loads draw. One release session froze (1 of 7, section 8d).

## 1. What the 18.4 GB "other" is made of (f1-A1 end of tour, and FOOT2's f2-A1/f2-A2 with the allocations named)

| part | commit MB | in RAM MB | owner (how it was named) | verdict |
|---|---|---|---|---|
| nvoglv64 arenas: five private allocations, one of 2 GB and four of 1 GB (the ">= 1 GB" family) | 6040-6100 | 5800 at 41 s, 800-1100 at 600 s (Windows trims them under pressure) | the NVIDIA driver: pointers into nvoglv64.dll inside, high-entropy data (pipeline binaries). The start-up precompile loads mkw_vk_pipelines.bin (2,126,052 KB) as the VkPipelineCache's initial data and builds 8,569 graphics pipelines (2.8 s); the driver keeps the file's data (the 2 GB arena) and every pipeline it made (the 1 GB ones) in host memory for the session. Written whole in the first 40 s, not read again (the GPU runs from VRAM). No call site of ours allocates them (no HeapCreate, no VirtualAlloc of that size in engine/) | needed only while pipelines are made. Oversized and never given back: the biggest RAM item of the host side (5.8 GB of the 8.3 GB host working set at 225 s) |
| the driver's blocks for VRAM (the "32-64 MB" family: 252 allocations, and part of the 64-256 MB ones) | 8100 + ~2000 | 80 + 540 | measured with a probe (below): the NVIDIA driver on Windows charges commit for every device-local VkDeviceMemory | the price of VRAM in use (8.9 GB at the end: textures 3283, live mirrors 2135, free in VMA blocks 2124, write-back shadows 340, scratch 160). Not cuttable except by using less VRAM (FOOT1's block reclaim / image generations) |
| BC cache, 28 blocks of 64 MB, host-cached (tagged "vk BC cache") | 1023 | 1023 | RX_VK_BC_CACHE_MB=1024 | useful (19,224 textures served, 16.8 GB copied) but never shrunk by age |
| captures (tagged, 21-25 kept) | 322-366 | 322 | | needed |
| staging, BAR (tagged) | 268 | 268 | | needed |
| job trace ring (tagged) | 128 | 128 | HL_STALL_WATCH only | not in a player's run |
| the rx page tables (page_seq 1 GB, gpu_pages 128 MB, rx_buffer.cpp) | 0 | 0 | the WebGPU renderer's, never made by the Vulkan back end | not allocated (checked: lazy commit of them changed nothing; dropped) |
| C heap 0 | 1209 | 950 | | |

Contrary to the brief's guess there is no mirror of guest memory, write-back shadow or readback ring in the 1 GB family: the mirrors (2135 MB) and shadows (340 MB) are in VRAM (the ledger), and their commit is in the "32-64 MB" family.

### The probe (E:\OOT\scratch-foot22.c, v4.c; RTX 5070, driver 617.42)

| call | private commit | working set |
|---|---|---|
| vkAllocateMemory device-local, 64 x 32 MB, or 8 x 256 MB | +2052 MB | +0 |
| VK_EXT_external_memory_host import of 256 MB or 1 GB already committed, with and without the device-address flag, a buffer bound to it, CPU fill after | +0 | the whole range is made resident by the import (+256 MB / +1 GB) |
| vkAllocateMemory host-visible, 256 MB / 1 GB | +size | +0 until touched |

So the driver's own arenas are not explained by memory imports or VRAM allocations; they follow the pipeline cache and the precompile.

## 2. The cuts (all behind switches, off by default)

| switch | what | effect on the tour |
|---|---|---|
| `RX_VK_PCACHE_RELEASE=1` | after the start-up precompile (not the background one), the VkPipelineCache holding the file's data is destroyed and an empty one takes its place; nothing is saved from the empty one (the file on disk stays, the next start's precompile builds from it again) | the 2.1 GB data arena and the driver's copy of it are gone: arenas 6040 -> 3348 MB commit on foot2b, 6045 -> 2549 on foot2c (f4-REL2); host side 9.8 -> 5.0 GB; page faults -2.0 M |
| `HL_MEM_TRIM_ARENAS=<s>` | a thread takes the committed pages of untagged private allocations of 512 MB and more (outside the guest window) out of the working set every <s> seconds (VirtualUnlock on a range that is not locked, as the cold pass does) | arenas in RAM: 5800 -> 6-50 MB; 5.6 GB taken out in the first pass; working set mean -4.5 GB, RAM available min +2.4 GB, at about +1.9 M soft faults |
| `RX_VK_BC_CACHE_IDLE_S=<s>` | a BC cache entry not served for <s> seconds goes | at 120 s in a ten-minute tour: 50 MB saved (1022 -> 972), 6.8 GB more copied back from the transcoder and 1.2 k more re-transcodes - not worth it; over a long session it would be |
| `hos_mem_tag` names for the rx page tables and the rx recording streams; the HL_MEM_ACCOUNT lines name each large allocation (tag, regions, resident slices) | diagnostics | |

## 3. Tour numbers (foot2_tour.sh, build foot2b, one lease T2, interleaved, HL_HITCH_LOG=rel:8, fps from play+10 s)

| arm | fps | frames >50 ms | page-fault stutters >50 ms | private end MB | "other" end MB | arenas commit / RAM MB at end | working set mean MB | RAM available min / median MB | page faults, whole run |
|---|---|---|---|---|---|---|---|---|---|
| A2 (no switch) | 97.1 | 288 | 78 | 30,699 | 18,655 | 6038 / 1664 | 16,322 | 911 / 2584 | 16.9 M |
| TR (trim arenas) | 95.0 | 303 | 91 | 29,395 | 17,241 | 6050 / 49 | 11,832 | 3368 / 3943 | 18.8 M |
| ALL (trim + pcache release + BC idle 120 s) | 100.3 | 274 | 78 | 27,078 | 14,724 | 2529 / 6 | 11,626 | 3725 / 4566 | 18.5 M |

(The faults of the whole run include those the HL_FAULT_WATCH sampler makes itself; they went up 10% with trimming: soft faults of pages the driver touched again. The stutters did not.)
Target "other under 8 GB" is not reached on that build: 14.7 GB. What is left is the VRAM's commit (8.1-9 GB: not cuttable), the BC cache, the driver's remaining arenas (2.5 GB) and the heaps - section 4 separates the VRAM's share from the host's, and the host's own part is what the target is about. Host RAM (not commit) fell from 4.1 GB to about 1 GB of arenas, and the working set mean by 4.7 GB.
Earlier tour runs on the same build family (f2-A1 53.7 fps, avail median 1.85 GB; f2-C1 104.6 fps, avail 3.7 GB) show how the other programs on the PC move the fps by 2x; only the interleaved arms above are compared.

## 4. The host/VRAM split, and the second round on build foot2c (T6, 23 Nov 19:46-20:09)

The ledger now names it (`vk_ledger.cpp`): "the driver's blocks for VRAM N MB (the device-local heaps' blockBytes, the process's
private commit for them)". The probe in section 1 measured the same charge (+2052 MB of commit for 64 x 32 MB of device-local
memory, nothing in the working set), so:

    host side = HL_MEM_ACCOUNT's "other" - the driver's blocks for VRAM

| arm (build foot2c, one lease T6, back to back) | fps | frames >50 / >100 / >500 ms | page-fault stutters >50 ms | private end MB | "other" end MB | driver's blocks for VRAM MB | host side MB | arenas commit / RAM MB | working set mean MB | RAM available min / median MB | page faults, whole run |
|---|---|---|---|---|---|---|---|---|---|---|---|
| f3-A2 (no switch) | 91.7 | 438 / 200 / 11 | 76 | 29,666 | 17,607 | 7,696 | 9,911 | 6040 / 817 | 15,194 | 329 / 1384 | 15.51 M |
| f3-REL (`RX_VK_PCACHE_RELEASE=1 RX_VK_BC_CACHE_IDLE_S=120`) | 95.4 | 306 / 141 / 6 | 95 | 27,577 | 13,402 | 8,466 | 4,936 | 2545 / 909 | 13,939 | 898 / 3527 | 17.66 M |

- The host side is under the 8 GB target in the cuts arm: 4,936 MB against 9,911 MB (the "other" line falls 4.2 GB, the driver's
  blocks for VRAM rise 0.77 GB because the arm kept more VRAM in use, and the process's private end falls 2.1 GB).
- No fps loss: 91.7 -> 95.4 (the arms are 20 minutes apart; the machine's other work moves this by more, see section 3). Frames
  over 50/100/500 ms fell (438/200/11 -> 306/141/6); the page-fault stutters rose (76 -> 95), which the T7 pair puts on the BC
  cache's idle trim, not on the release (section 4b).
- Page faults went UP in that pair: 15.51 M -> 17.66 M (+13.9%), the whole difference after ~360 s of play. The BC cache did
  more work in the cuts arm (20,781 textures served for 19,486 MB copied against 19,170 for 12,663 MB; re-transcodes 6,514 against
  5,278): the idle trim let go of entries the tour came back to. T7 (below) has the release alone.
- The start-up precompile is not slowed by the release: 8,591 graphics pipelines in 10.8 s (A2) and 8,592 in 14.5 s (REL) - the
  difference is the machine's other load (the second arm ran while another agent's build finished).
- f3-ALL (release + BC idle + trim) was refused by runguard (rc 11: another agent's clang.exe ran in my speed lease), so the
  trim has no arm on foot2c. Its numbers stand from foot2b (section 3).

### 4b. The release alone (T7, build foot2c, lease 20:37-21:01, back to back)

| arm | fps | frames >50 / >100 / >500 ms | ms in frames >50 ms | page-fault stutters >50 / >100 ms | private end MB | "other" end MB | driver's blocks for VRAM MB | host side MB | arenas commit / RAM MB | working set mean MB | RAM available min / median MB | page faults, whole run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| f4-A2 (no switch) | 103.4 | 347 / 158 / 3 | 40,398 | 76 / 51 | 30,639 | 18,476 | 8,712 | 9,764 | 6045 / 929 | 14,499 | 458 / 3254 | 17.10 M |
| f4-REL2 (`RX_VK_PCACHE_RELEASE=1`) | 116.6 | 423 / 200 / 4 | 51,881 | 73 / 46 | 27,244 | 13,163 | 8,165 | 4,998 | 2549 / 886 | 14,797 | 814 / 1224 | 15.09 M |

`RX_VK_PCACHE_RELEASE=1` alone is the switch the brief's three conditions hold for:

- host side 9,764 -> 4,998 MB (under 8 GB), arenas 6.0 -> 2.5 GB of commit, the process's private commit at the end 3.4 GB lower;
- no fps loss: 103.4 -> 116.6 (the second arm ran in a faster stretch of the machine: 91.7-116.6 fps is the range of the same
  arm across the evening, and the cuts arms are never the slower one);
- fewer page faults: 17.10 M -> 15.09 M (-11.8%), the mechanism being that nothing is saved from the empty cache in play, so
  the 1-2 GB of mapped writes the cache's saves made (and their faults) are gone;
- the page-fault stutters fall (76 -> 73 of >50 ms, 51 -> 46 of >100 ms, 13.2 -> 13.8 s in all); frames over 50 ms in all are a
  little more (347 -> 423, 0.55% -> 0.59% of the frames) because the second arm drew 13% more of them.

## 5. Under a memory hog: the pair that holds and the one that only looked like one (T8, T9)

Two hog pairs on foot2c, `foot2_table.py`'s rows, fps from play + 10 s. The hog is the machine's way to be short of RAM while
another program (the game) runs: it allocates and touches memory of its own.

### 5a. T8 (21:29-21:52): memhog.py's target-free mode makes the pair incomparable

memhog.py (`E:/OOT/scratch-foot1/memhog.py`, the one T3 used) sizes itself to bring the system's *free* RAM to a target: the
more RAM an arm frees on its own, the bigger the hog it gets. The A arm got a 2,560 MB hog, the release arm a 4,992 MB one
(the release had that much more free), and the hog rewrites its whole footprint every 0.5 s, so the larger hog also takes more
bandwidth.

| arm | fps | frames >50 / >100 / >500 ms | ms in frames >50 ms | page-fault stutters >50 / >100 ms | private end MB | "other" end MB | host side MB | working set mean MB | RAM available min / median MB | page faults | the hog |
|---|---|---|---|---|---|---|---|---|---|---|---|
| f5-hA (no switch) | 94.6 | 561 / 228 / 12 (0.97%) | 72,352 | 101 / 60 | 30,550 | 18,358 | 9,805 | 11,605 | 177 / 1,097 | 17.08 M | 2,560 MB |
| f5-hREL (`RX_VK_PCACHE_RELEASE=1`) | 81.4 | 619 / 248 / 23 (1.25%) | 90,893 | 108 / 56 | 27,297 | 12,259 | 4,173 | 9,330 | 372 / 1,177 | 17.85 M | 4,992 MB |

The 13 fps gap is the size of the same arm's spread across runs (f2-hA 83.0 fps on foot2b, f5-hA 94.6 on foot2c) and the hog
sizes differ by exactly the memory the release saves - the pair says nothing about the release. Lesson: a hog for an A/B pair
must hold a fixed size.

### 5b. T9 (22:57-23:21): a fixed hog of 3,456 MB in both arms

`E:/OOT/scratch-foot2/memhog_fixed.py` allocates once, keeps every page resident, and is the same size for both arms; the tour
is the same as 4b's (`E:/OOT/scratch-foot2/tour_fixed.sh`).

| arm | fps | frames >50 / >100 / >500 ms | ms in frames >50 ms | page-fault stutters >50 / >100 ms | private end MB | "other" end MB | driver's blocks for VRAM MB | host side MB | arenas commit / RAM MB | working set mean MB | RAM available min / median MB | page faults, whole run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| f6-A (no switch) | 101.0 | 450 / 183 / 5 (0.73%) | 53,464 | 111 / 57 | 30,261 | 18,132 | 8,383 | 9,749 | 6070 / 829 | 11,541 | 336 / 971 | 16.35 M |
| f6-REL (`RX_VK_PCACHE_RELEASE=1`) | 104.6 | 472 / 197 / 8 (0.77%) | 57,524 | 88 / 48 | 27,301 | 14,717 | 5,339 | 9,378 | 2507 / 695 | 11,648 | 53 / 1084 | 15.26 M |

- The release holds under pressure: fps 101.0 -> 104.6, page faults 16.35 -> 15.26 M (-6.6%), page-fault stutters >50 ms
  111 -> 88 (-21%). Frames over 50 ms are 0.73% -> 0.77% of the frames (the two arms drew 62,036 and 61,554 play frames).
- It gives the arm 3.9 GB more free RAM early (8,407 MB at 30 s against 4,524), which the hog and the tour's own growth then
  spend: the release arm's lowest available RAM is 53 MB at 300 s against 336 MB in the A arm at 270 s.
- The subtraction (host side = "other" - the ledger's blocks for VRAM) is not usable in this pair: the engine's VRAM in use is
  far lower at the end than in 4b (textures 3,919 -> 1,478 MB, live mirrors 2,001 -> 128, free in VMA 3,391), the live
  device-local blockBytes fall to 5,339, but the driver's 16-64 MB family stays at 8,438 MB committed (f4-REL2: 8,373 against
  blocks 8,165; f6-A: 8,956 against 8,383). That family is the driver's host-side memory and it does not follow the VRAM down,
  so the subtraction reads
  9.4-9.7 GB here where the families give 14,717 - 8,438 = 6,279 MB for the release arm and 18,132 - 8,956 = 9,176 MB for the
  A arm. Under the hog the host side is still under 8 GB in the release arm, 2.9 GB lower than the A arm's.
- The start-up precompile built 8,592 pipelines in 5.8 s (A) and 15.5 s (REL) - the machine's load, as in 4a; play's numbers
  are counted from play + 10 s and do not include it.

## 6. Pictures at the zone changes (slot lease pic, 23 Nov 20:13-20:39, build foot2c, RX_VK_SHOTS/RX_VK_SHOT_EVERY=900)

Two arms of the same tour, `p3-A2` (no switch) and `p3-ALL` (`RX_VK_PCACHE_RELEASE=1 RX_VK_BC_CACHE_IDLE_S=120
HL_MEM_TRIM_ARENAS=20`), 55 and 80 shots of 1280x720 in E:/OOT/scratch-foot2/shots/p3-A2 and /p3-ALL, contact sheets
sheet-A2.png and sheet-ALL.png beside them. Every zone change of the tour is there (Market, HyruleField, Kakariko,
DeathMountainTrail, GoronCity, Dodongo, Market, Kokiri, LostWood, HyruleField, ZoraRiver, ZoraDomain, Lake Hylia, GoronCity,
Dodongo, Market) and the two arms show the same picture at the same point of the tour: no texture lost or blacked by the BC
cache's idle trim, no pipeline gone or wrong from the release, no zone drawn differently. The only black frames are the ones
the game itself shows while a map loads (both arms, same places). (The A2 arm's first shots are missing: its directory did not
exist for the first 2.5 minutes - the renderer writes straight into the directory, it does not create it, and RX_VK_SHOTS was
given a leaf that did not exist yet.)

## 7. Tests

`python -I -B tests/run_all.py` from engine/ with E:\OOT\rl-devbuild\tools\llvm-mingw\bin first on PATH: **503 passed, 3
failed, 53 skipped in 156 s**, the three failures the ones known here (`nx2/test_nup_paths.py`: symlinks need a privilege this
account lacks; `nx2/test_nup_read_name.py`: no zstandard module; `tests/test_renderer_new_handler.py`).

The branch had broken a fourth: `tests/test_pipeline_cache_save.py` cuts `pipeline_cache_save` out of vk_draw.cpp and compiles it
against stubs, and the release's `pcache_released` was not among them. Fixed in `engine/tests/pipeline_cache_save_test.cpp` (one
stub line: `std::atomic<bool> pcache_released{false}`), and the check then passes (12 tests, 1 skipped). `list_switches.py
--check` passes for the three new switches.

(FOOT3, 24 Nov) The fix adds a second fetch of the cache's data (the play file's save), which `tests/test_pcache_fetch_lock.py`
counts, and regenerates the switch lists; both checks are updated (`503 passed, 3 failed` again, `scratch-foot3\tests2.log`), and
`list_switches.py --check` passes.

(FOOT3, 24 Nov 06:36) The branch's last run, after this round's log line and the regenerated lists: **503 passed, 3 failed, 53
skipped in 124 s** (`scratch-foot3\tests3.log`), the same three known failures, and `list_switches.py --check` passes. Build
`foot3c` (mkg.ps1 -Block -Owner foot3, the same source) built under a build lease in 39 s (`scratch-foot3\foot3c-build.log`) and
has the fixed release line; it was not run (the round's numbers are foot3b's, and the change touches only a log statement).

## 8. Can the release be on by default? (FOOT3)

### 8a. What a session builds after the precompile, and whether it is in the file

The tour of section 4b, read from its own log (`build/s5/f4-A2/game_log.txt`, switch off):

- The precompile builds 8,592 graphics pipelines from 8,592 notes ("precompile: 8592 graphics (8592 made, 0 not) ... in 12362 ms").
- At the end of the run the 120-frame line reads "8869 pipelines (26734 ms)": 277 more creations than the precompile's 8,592.
- In that run none of them is a graphics pipeline: the `pipelines` map stays at 8,592 for the whole run ("vk: pipelines: 8592
  graphics made, 3876 pipelines bound so far") and the notes file did not grow across the four FOOT2 tour runs (8,593 records,
  246,172,304 bytes, read before this round). The 277 are **compute** pipelines: the lazy compute programs ("precompile: the compute
  programs stay on disk until dispatched"), one per program a zone first dispatches, built inline on the dispatch thread (277
  compute shader modules let go, 11 more found in the cache: "compute pipelines built in play: 11 from the pipeline cache (or under
  30 ms), 0 compiled").
- That run's notes already held every **graphics** pipeline the tour draws. A session whose notes do not builds them in play as
  well: FOOT3's f3o-A (slot c's 675-record notes) ended at 3,897 creations against the precompile's 698 - **2,924 graphics + 275
  compute** ("pipelines: 3622 graphics made, 3785 pipelines bound so far; 275 compute shader modules let go") - of which 254 were
  compiles the 2.1 GB file did not hold (`pcache_new_total` 66 -> 320). Once a session has noted them (f3o-S2, 3,622 notes) the
  steady state is **102 graphics + 276 compute = 378** per tour, of which 18 are compiles (section 8b).
- Nothing notes a compute pipeline into hookshot_pipelines.bin, and any pipeline reaches a cache file only when a save in play
  writes it (RX_VK_PCACHE_PLAY_SAVE's rule: `2 * cache + 4096 MB` free, 8.2 GB with the 2.1 GB file). No switch-off tour run saved
  the file (0 saves in f3o-A and f3o-S2; the machine had 0.5-0.8 GB free during play). **On this PC the switch-off arm loses its
  play-built pipelines too**, so the release's risk as measured here is not the difference between saving them and not, but between
  an empty cache and the driver's own cache (nv_shader_cache) for them - and, with FOOT3's fix, a play file small enough for the
  save gate (section 8b).

### 8b. The two-session pairs

Every session is the same 10-minute warp tour (15 warps at 15..575 s after "play: began", `scratch-foot3/tour_live.sh`), run with
`RUN_S=800`/`LIMIT_S=900` so that a slow start still leaves the whole tour; the run dirs are `build/s5/<tag>` and the numbers below
come from `scratch-foot3/row.py` over them (fps: play + 10 s over present_trace.csv; the warp windows: 60 s after each warp, and the
40 s between warps; the waits: the 120-frame blocks' "waits for shaders or pipelines"). Each session's three cache files are
snapshotted when it ends, so a pair starts from exactly the state its session 1 left.

| arm (build foot3b) | what it started from | fps | frames | >50 / >100 / >500 ms | 60-s warp windows >50 / >100 / >500 | 40-s >50 / >100 | waits | play built | new to the file (start / end) | host side MB | private end MB | avail min MB | faults |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| f3o-A (off, 02:58) | 675 notes, file P0 | 112.7 | 83,346 | 828 / 284 / 32 | 1,122 / 354 / 45 | 699 / 210 | 2 blocks, 0.4 ms | 3,199 | 66 / 320 | 7,991 | 28,294 | 563 | 16.58 M |
| f3o-S2 (off, 03:14) | f3o-A's (3,622 notes) | 113.1 | 83,799 | 611 / 207 / 9 | 879 / 283 / 15 | 546 / 172 | 0 | 378 | 320 / 338 | 8,028 | 28,010 | 536 | 16.86 M |
| f3n-S1 (release, 03:49) | f3o-A's (3,622 notes), no play file | 99.1 | 75,076 | 316 / 158 / 3 | 427 / 203 / 6 | 266 / 125 | 2 blocks, 0.4 ms | 383 | 320 / 419 | 5,550 | 25,778 | 1,628 | 18.09 M |
| f3n-S2 (release, 04:04) | f3n-S1's (3,728 notes, 20,852,069-byte play file) | 101.4 | 76,849 | 385 / 112 / 3 | 539 / 150 / 4 | 324 / 88 | 1 block, 0.2 ms | 312 | 338 / 363 | 5,472 | 25,634 | 1,050 | 17.20 M |

- The session-2 pair (f3o-S2 against f3n-S2, both from one session's notes over the same 2.1 GB file): the release arm has **fewer
  frames over 50/100/500 ms** (611/207/9 against 385/112/3, and in the warp windows 879/283/15 against 539/150/4), one "waits" block
  with 0.2 ms against none, and 312 play builds against 378.
- By kind (the logs' own counters: the 120-frame line's "N pipelines (ms)" and "pipelines: N graphics made ...; M compute shader
  modules let go", the compute line's "N from the pipeline cache (or under 30 ms), M compiled"): f3o-S2 102 graphics + 276 compute,
  f3n-S2 30 + 282, f3n-S1 106 + 277. All compute came from the cache or under 30 ms in every arm (0 compiled), so what the release
  can lose is graphics compiles: "new to the file" (`pcache_new_total`: creations the cache did not hold) goes 320 -> 338 in f3o-S2
  (18 in play), 320 -> 419 in f3n-S1 (99) and 338 -> 363 in f3n-S2 (25). The released file's blobs are the 18 -> 99; the 20 MB play
  file takes it back to 25, and with the notes matured (3,772 in f3p-R2, where play built 279) the count falls to 4.
- Its fps is **lower** (101.4 against 113.1), and the two sessions are 50 minutes apart - but that is the whole-play fps, which
  counts the loading seconds; the gameplay after each warp is equal, and so it is in FOOT2's f4 (where the release reads 12.7%
  *higher*, not lower). Section 8c splits the frames and settles it.
- The release arm's memory is the point: host side 8,028 -> 5,472 MB, private commit at the end 28.0 -> 25.6 GB, free RAM at its
  lowest 536 -> 1,050 MB. The file on disk is untouched (2,177,301,359 bytes before and after both release sessions).
- The play file works: f3n-S1 (release, empty cache) wrote 20,852,069 bytes in two saves (14 MB in 4 ms, 19 MB in 33 ms; 34 then 46
  pipelines new, 400 in all), and f3n-S2 started with "the play pipeline cache ... (20363 KB)" and read it into its empty cache at
  the release (its release line's "0 KB ... taken in" is that size printed after the buffer was let go - a log bug fixed in the
  branch after these runs; the "(20363 KB)" line at startup is the real size). Its compute builds are therefore found, not compiled:
  282 of 282 under 30 ms, 0 compiled ("compute pipelines built in play: 282 from the pipeline cache (or under 30 ms), 0 compiled").
- The switch-off arm saved nothing in either session (the save in play wants 2 x 2.1 GB + 4 GB free; the lowest free RAM was
  536-563 MB), so on this PC its 18 compiles come back every session; the release's 20 MB file does not have that problem (gate 168 MB).

### 8c. The same-hour pair, and what the tour's fps counts (T16, T17, and five pairs)

Section 8b's fps looked like a release cost, so the pair was repeated at one hour from the same state (f3p-O 05:12, f3p-R2 05:35)
and the frames were split: the 20..40 s after each warp (gameplay, clear of the load) against the 0..10 s (the warp's load and
transition). `scratch-foot3/gameplay.py` and `loadgame.py` over the same traces.

| pair (same build) | round | fps play+10 | gameplay 20..40 s, mean of 15 warps | median frame | 0..10 s windows (frames per tour-s) |
|---|---|---|---|---|---|
| f4-A2 / f4-REL2 (foot2c) | T7, 20:37-21:01 | 103.4 / 116.6 | 91.8 / 92.6 | 9.96 / 10.00 ms | - |
| f3-A2 / f3-REL (foot2c) | T6, 19:46-20:09 | 91.7 / 95.4 | 82.4 / 85.9 | 10.34 / 10.66 ms | - |
| f6-A / f6-REL (foot2c, hog) | T9, 22:57-23:21 | 101.0 / 104.6 | 81.7 / 81.0 | 10.52 / 10.63 ms | - |
| f3o-S2 / f3n-S2 (foot3b) | T12 / T13, 03:14 / 04:04 | 113.1 / 101.4 | 95.6 / 96.0 | 9.43 / 9.54 ms | 45.6 / 37.8 |
| f3p-O / f3p-R2 (foot3b) | T16 / T17, 05:12 / 05:35 | 118.0 / 111.8 | 92.7 / 96.7 | 9.52 / 9.46 ms | 50.0 / 43.7 |

- **Gameplay does not move.** In all five pairs the 20..40 s windows agree within 4% (92.7 against 96.7; 95.6 against 96.0; 81.7
  against 81.0; 91.8 against 92.6; 82.4 against 85.9) and the median frame interval within 3% (9.46 against 9.52 ms in the same-hour
  pair, 9.96 against 10.00 in f4). The whole-play fps moves both ways across the pairs (+12.8%, +4.0%, +3.6%, -10.3%, -5.3%), and
  the difference sits in the seconds after each warp: the 0..10 s windows hold 50.0 against 43.7 frames per tour-second in the
  same-hour pair (45.6 against 37.8 in T13) - the switch changes what the loading and transition seconds draw (in T13's warp-95
  window the off arm spent +2..+12 s on the 250-320 fps load screen, the release +2..+8 s and then played), not the play.
- The same-hour pair, numbers: host side 8,073 -> 5,285 MB, private end 28,551 -> 25,392 MB, free RAM's lowest 709 -> 827 MB,
  frames over 50/100/500 ms 769/210/17 -> 534/145/5 (60-s warp windows 1,080/283/15 -> 792/212/6), waits 0 -> 0. Play built 279
  pipelines (4 graphics + 275 compute), 4 new to the file, **0 saves** (nothing owed: the notes now hold the tour's graphics).
- So the earlier 10% is not pipeline compiles: with the notes at 108 MB (3,772 records) the release compiles 4 pipelines in play, and
  its whole-play fps is still 5.6% lower. The load seconds are the switch's own effect on the driver (empty cache, arenas gone),
  unexplained but confined to the loading screens; f3o-O1 (05:00, off, the same state) reads 140.7 fps in 10..600 s (gameplay 98.1,
  median 9.33 ms), the machine's own swing across 20 minutes being larger than any arm effect in that metric.

### 8d. The one session that froze (f3i-R)

- f3i-R (T14, release, 04:31-04:42, from f3n-S2's state with its 20 MB play file) stopped presenting at play+625 s: the trace ends at
  frame 87,840, the log's last line is an ordinary 20-25 ms stallwatch block, and the process then used no CPU for minutes (140
  threads, its window still answering, no present). The harness's `taskkill /F` at 04:44:23 did not take; the process was gone some
  minutes later. No TDR in the System log and no Application Hang event; 239 GB free on E:; its mem.csv shows no page-file pressure.
- Everything before that is normal: 3,758 graphics precompiled (18.6 s - the disk was busy, a duplicate FOOT3 tour was copying 2.1 GB
  into slot c at the same time), play began at 75.4 s, 4,127 pipelines and 4,670 textures at the last line, 100.4 fps over 10..600 s
  (play_s 625), 321/133/3 frames over 50/100/500 ms, one 24 MB play-file save at 04:36.
- It is the only freeze in the seven release sessions of this round and FOOT2 (f3-REL, f4-REL2, f6-REL, f3n-S1, f3n-S2, f3i-R,
  f3p-R2) and in the switch-off sessions of the same rounds (f3-A2, f4-A2, f6-A, f3o-A, f3o-S2, f3o-O1, f3p-O). The signature (a wait
  no TDR broke, the UI alive, no compile or save in the log) is not the pipeline cache; it is not used in any comparison. A longer
  soak of either arm is what would find it again.

## State

**FOOT3 (4th agent), 24 Nov 06:40: done and stopped; the verdict is in the Summary.** No lease, ticket or command of mine is
left: T17's speed lease was released by its tour at 05:49 and its tour put slot c's exe/dll back from `scratch-foot3\slot-bak`
(another agent's tour has copied its own build in since - slot c is shared and none of it is mine to keep); the build lease of
06:34 was released at 06:37 after the suite and the `foot3c` build. The question was
whether `RX_VK_PCACHE_RELEASE=1` can be on by default, given that what play builds after the release is not saved: **yes**, with the
play file (sections 8b-8d). What the runs showed, in short:

- What a tour session builds beyond the precompile (section 8b): 378 pipelines (102 graphics + 276 compute) once the notes hold
  the tour, of which 18 are compiles the 2.1 GB file did not hold (f3o-S2); 3,199 of which 254 are compiles when the notes are a
  675-record subset (f3o-A); 383 of which 99 when the cache is empty after a release and there is no play file (f3n-S1); 312 of which
  25 with the play file (f3n-S2); 279 of which 4 when the notes have matured (f3p-R2). All compute was served (under 30 ms, 0
  compiled) in every arm - the release's loss is graphics compiles, and the play file keeps them.
- The fix (behind the same switch) writes them to `mkw_vk_pipelines_play.bin` (20-26 MB; 2 saves in f3n-S1, 1 in f3i-R) and the
  next start makes the empty cache from it (f3n-S2 took 20,363 KB in). Its save gate (2 x its size + 128 MB, 168 MB) fits this
  PC where the 2.1 GB file's (8.2 GB) never did.
- The second session is no worse: f3n-S2 has fewer frames over 50/100/500 ms than f3o-S2 (539/150/4 against 879/283/15 in the 60-s
  warp windows) and one 0.2 ms waits block against none; the same-hour pair is 534/145/5 against 769/210/17 and 0 waits in both.
- The fps question: the whole-play fps falls 5.3% in the same-hour pair (118.0 off against 111.8 release) and 10% in T13, but the
  gameplay after each warp does not move in any of the five pairs (92.7 against 96.7 fps, medians 9.52 against 9.46 ms; f4 91.8
  against 92.6, medians 9.96 against 10.00). The whole-play metric counts the loading seconds, where the switch draws fewer frames
  (0..10 s after a warp: 50.0 against 43.7 per tour-second); it is not a gameplay cost, and it is not the play-time compiles (4 in
  the same-hour release session).
- One release session froze at play+625 s (f3i-R, section 8d): one of seven release sessions, not reproduced, not attributable to
  the cache (no compile or save in its last minute, no TDR, the UI alive). Open: a longer soak would tell whether it recurs.

- A tour session builds more than the start-up precompile: the 120-frame lines of f4-A2 (8,592 notes) end at 8,869 creations, all
  extra ones **compute** (the lazy compute programs, one per program a zone dispatches); a session whose notes do not hold the
  tour's graphics builds those in play too (f3o-A: 2,924 graphics + 275 compute, and the notes grow to hold them). Section 8a has
  the counts and what is new to the file.
- The switch-off runs did not save the file at all (no `pipeline cache saved` line in f4-A2, f4-REL2, f6-A, f6-REL): the save in
  play is gated on `2 * cache + 4096 MB` free (8.2 GB here with the 2.1 GB file), which this machine never has during the tour, and
  no save runs at exit (a run cut by the harness does not get there; the game's own close does not force one either). So on this PC
  the switch-off arm loses its play-built pipelines too; the series runs both ways.
- `waits for shaders or pipelines` is 0.00 in every 120-frame block of the four FOOT2 tour runs (a compute pipeline built on the
  dispatch thread is a skipped draw, not a wait); the first session with many play builds does wait (f3o-A: 17 blocks, 4.1 ms in
  all, 1.6 ms the worst), the second sessions 0 (f3o-S2) and 0.2 ms (f3n-S2). The session-2 comparison therefore rests on the
  frame times and on the builds' own times (FOOT3 logs them).
- Fix written (behind the same switch): after the release the empty cache is created from a small file of its own
  (`mkw_vk_pipelines_play.bin`), and what play builds is written back to it in play (its own room gate, 2 x its size + 128 MB, every
  120 s) and on a forced save. Counters added: pipelines new to the file (graphics and compute), and the dispatch thread's compute
  build times. Tests: 503 pass, the 3 known failures (tests2.log); `test_pcache_fetch_lock` and `test_switches_documented` were
  updated for the two new fetches and the regenerated lists.
- **Smoke test (T9, build foot3a, 2 x 240 s runs, not part of the comparison) found two things.** The fix works: the release created
  its empty cache from the (absent) play file, play built 2,073 graphics pipelines of a first start, and the play file written at
  play+~4 min was 76,380,566 bytes; the second session took it (log: "0 KB of the play file's data taken in" for the first, none
  for the second) and precompiled 2,073 notes. But session 1 precompiled **0** pipelines: changing `vk_draw.h` (the two log
  accessors) changes `HOOKSHOT_STATE_STAMP` (nx2/build.py hashes vk_state.h, vk_api.h, vk_draw.h, rx_nvn.h), which starts every
  notes file over: slot c's 8,593 notes (246 MB) were rewritten to 2,161 (61.9 MB) and `hookshot_compiled.bin` reset. So the header
  is left alone now (the accessors are declared in vk_replay.cpp instead) and the build restarted to put the branch's stamp
  (0xb56fb34745ab3c15) back; slot c's notes are restored from slot a's file (10,138 records, the same state and translator stamps;
  the old slot c file is gone, a copy of what the smoke run left is in `scratch-foot3\notes-c-after-smoke.bin`).
- Build `foot3b` (mkg.ps1 -Block -Owner foot3, no -Lift: the lift is unchanged, the stamp is back) built at 01:23 (54 s); its dll has
  the new log strings. The first build attempts failed to link (the counters' accessors were declared either in vk_draw.cpp's unnamed
  namespace or in vk_replay.cpp's: both are out of them now, commit `fix(vk): the pipeline cache's counters are declared where they
  are logged, not in vk_draw.h`).
- Backups: `E:\OOT\scratch-foot3\P0.bin` (slot c's `mkw_vk_pipelines.bin`, 2,177,301,359 bytes, as before the first session);
  the slot's exe/dll to `slot-bak\` by the tour script, which restores them at the end.
- Series (4-5 sessions of the same 10-minute tour, one speed lease per 2-3 sessions of 45 min): `series1.sh` = f3o-S1 (off, file
  P0), f3o-S2 (off, file as left), f3n-S1 (release, file P0, no play file); `series2.sh` = f3n-S2 (release, its play file), f3x-S2
  (release, play file removed: the switch before this fix). The speed lease for series 1 was queued at 01:24 (prio 2) behind env-p3c's
  and pipe3's leases; it is granted when they end (pipe3's slot a by 02:48 the latest). Nothing of mine is held while it waits: the
  ticket renews itself every 9 s.
- **Series 1 (T10, 01:56-02:34, the run that found the stamp problem) is not used for the comparison**: its sessions precompiled
  0/3,753/3,800 pipelines (no usable notes), so their starts and play lengths differ. Its numbers, in `build/s5/f3o-S1`, `f3o-S2`,
  `f3n-S1`, are the fix's first proof: `f3n-S1` (release, empty cache) wrote `mkw_vk_pipelines_play.bin` 19,814,390 bytes with one
  save ("play pipeline cache saved: 18 MB in 205 ms ...; 88 pipelines new to it, 445 in all since the start"), the main file
  unchanged, and built 267 compute pipelines in play **all under 30 ms, 0 compiled** ("267 from the pipeline cache (or under 30 ms),
  0 compiled; the dispatch thread's 0 in all"): the driver's own cache serves them, so the release did not turn them into compiles
  on this machine.
- **Series 4-7 (T14-T17, 04:28-05:49)**: the duplicate-instance accident and what survived. The orchestrator's restart ran a second
  instance of this same agent (foot3-ds2) beside the first; two `tour.sh` runs competed for slot c and one of them copied a 2.1 GB
  main file into the slot while the other's game read it. The second instance's T15 pair (f3o-O1, f3n-R1) was stopped at 05:08 and
  its lease released; f3o-O1 kept its own numbers (its log shows the game read a full cache, "pipeline cache ... (2126270 KB)", and
  3,724 notes - the 396,623,872 bytes its `files before` saw were the concurrent copy's mid-write; it is the 05:00 off-arm point of
  8c). The first instance's T16 ran `f3p-O` (off, 05:12) and had `f3p-R` refused (runguard rc 11: build scripts in the machine),
  so this agent ran the same arm as `f3p-R2` (T17, 05:35) from exactly `f3p-O`'s state. `f3i-R` (T14, release, 04:31-04:44) is the
  session of section 8d: it presented until play+625 s and froze; its numbers are not used.
- **Series 3a** (T12, 02:54-03:31, RUN_S=800 so every session played the whole tour): **f3o-A** (off, the 675-record notes, P0):
  precompile 698 graphics (66 of them new to the file), play began at 52.75 s, 15 maps, fps 112.7, frames >50/100/500 ms
  828/284/32, in the 60-s warp windows 1,122/354/45 (40-s exclusive: 699/210/26), no waits; play built 3,199 pipelines (254 new to
  the file), notes after 103,763,096 bytes (3,622 records). **f3o-S2** (off, exactly f3o-A's files): precompile 3,622 (320 new to
  the file), play began 54.87 s, 15 maps, fps 113.1, frames >50/100/500 ms 611/207/9, warp windows 879/283/15 (exclusive
  546/172/8), waits 0; play built 378 pipelines (18 new to the file); **0 saves in play, the file unchanged** (2,177,301,359 bytes
  before and after). **T13's release pair**: f3n-S1 (release, f3o-A's state, no play file) 99.1 fps, 316/158/3, 427/203/6 (40-s
  266/125), 2 blocks 0.4 ms, play built 383 (106 graphics + 277 compute), 99 new to the file; f3n-S2 (release, f3n-S1's state with
  its 20 MB play file) 101.4 fps, 385/112/3, 539/150/4 (40-s 324/88), 1 block 0.2 ms, play built 312 (30 + 282), 25 new to the file.
- Source this round: `fix(vk): the release's log prints the play file's size before the buffer goes` (vk_draw.cpp: the KB count is
  taken before the clear and the swap; the foot3b logs of 8b/8c print "0 KB" there), and the declarations of
  `pcache_new_since_start/save` moved to the top of vk_replay.cpp (no behaviour - the commit of 01:23's `fix(vk)` had them beside
  their definitions). No switch changed; the regenerated lists shift the read-at lines (`docs(switches)`). Checks after both: 503
  passed, 3 known failures, 53 skipped in 124 s (tests3.log, 06:36) and the build `foot3c` under a build lease (39 s,
  foot3c-build.log, 06:37); it was not run, the round's numbers are foot3b's.
- Scratch, all under `E:\OOT\scratch-foot3`: `tour.sh` (one lease, N sessions, the three caches per session), `tour_live.sh` (the 15
  warps), `row.py`, `fixedwin.py`, `warpfps.py`, `gameplay.py`, `loadgame.py`, `winsec.py`, `waitblocks.py`, `texseries.py`,
  `sampler.py`, `series1-7.sh`, logs `T9.log`-`T17.log`, `tests3.log`. Backups: `P0.bin` (the slot's 2.1 GB cache), `slot-bak\`
  (its exe/dll), `notes-c-after-smoke.bin`.

**FOOT2 (3rd agent), 23 Nov 23:30: the hog question is answered and stopped.** No lease, ticket or command of mine is left:
T8's speed lease was released at 21:52, T9's at 23:21 (both requested and released by the tour scripts), no game, hog or
sampler of mine runs, slot c is back to its own exe/dll (checked against build/s5/foot2-bak).

- This round: read and checked T7 (section 4b numbers all stand against `build/s5/f4-*.mem.csv`/`bench.json`), then the two hog
  pairs - T8 (`f5-hA`, `f5-hREL`, target-free hog; invalid, section 5a) and T9 (`f6-A`, `f6-REL`, a fixed 3,456 MB hog in both
  arms; the result, section 5b): release 104.6 fps against 101.0, page faults 15.26 M against 16.35 M (-6.6%), page-fault
  stutters >50 ms 88 against 111, host side 6.3 GB against 9.2 GB by the driver's 16-64 MB family. It is in the Summary too.
- New files this round, all scratch, none in the repo: `E:\OOT\scratch-foot2\memhog_fixed.py` (fixed-size hog),
  `tour_live_fixed.sh` and `tour_fixed.sh` (the tour with that hog), `run_t8.sh`, logs `T8.log`, `T9.log`.
- Branch: this document's commit is the only change since 2c29ecab1; no source change in this round, so the tests of the 2nd
  agent (503 passed, 3 known failures) still stand; `list_switches.py --check` untouched (no new switch).
- Still open (all optional, the brief's three conditions are met by `RX_VK_PCACHE_RELEASE=1` alone): a trim arm on foot2c; the
  pressure-gated trim idea; and the question the T9 ledger raised - the driver's 16-64 MB family keeps ~8.4 GB committed while
  its live blockBytes fall with the VRAM under pressure (section 5b), so the subtraction "other - blocks for VRAM" needs the
  family as the charge when VRAM has been reclaimed.

**Previous state (2nd agent), 23 Nov 21:08: done and stopped.** No lease, ticket or command of mine is left: T7's speed lease was
released at 21:00, the picture slot lease at 20:39, slot c and slot a were restored by their scripts (the tour's backup is
build/s5/foot2-bak, the pictures' build/s5/foot2-bak-pic), no game of mine runs.

- Built and measured on `build/s5/bin/foot2c` (mkg.ps1 -Name foot2c -Block -Lift -Owner foot2 -Root
  E:/OOT/HeyListen-wt/foot2/engine, SLOT_PRIO=1, "built foot2c after 490 s", log build/s5/foot2c-build.log).
- Rounds: T6 (f3-A2, f3-REL; f3-ALL refused by runguard), T7 (f4-A2, f4-REL2 = the release alone), the picture pair
  (p3-A2, p3-ALL), the checks (tests2.log: 503 passed, 3 known failures).
- Source: the three switches (section 2) + the ledger line naming the driver's blocks for VRAM (section 4). Commits on top of
  4b599eb04: `perf(vk): the VRAM census names the driver's blocks for VRAM`, `docs(switches): the three FOOT2 memory switches
  in the lists`, `test(pipeline): the cache-save check stubs the release flag the branch added`, and this document.
- The verdict the owner asked for is in the Summary at the top: `RX_VK_PCACHE_RELEASE=1` alone gives host side 9.8 -> 5.0 GB,
  no fps loss and 11.8% fewer page faults (section 4b); the trim is the RAM-under-pressure switch, with its faults
  (section 3); the BC idle at 120 s is not worth it (section 4).
- Left for the next agent: the hog pair (T3's f2-hA stands at 83.0 fps, 387 frames over 50 ms, 91 page-fault stutters,
  avail min 430 MB); a trim arm on foot2c (T6's `f3-ALL` was refused: another agent's clang.exe ran in my speed lease - a
  lesson: another agent's unleased checks can spoil a speed arm, so check `machine.sh status` and keep an eye on
  clang.exe right before and during one); and one idea not tried: make `HL_MEM_TRIM_ARENAS` fire only when available RAM is
  under a line (e.g. 3 GB), which would keep its fault cost away from a machine that is not under pressure.
- All three switches stay OFF by default, as the brief asks.

**Previous stop 23 Nov 18:35 (weekly limit).** All commands stopped, no lease or ticket held, slot c restored from build/s5/foot2-bak.

- Branch perf/foot2 (worktree E:\OOT\HeyListen-wt\foot2): 4 commits on origin/main 4b599eb04 at that stop. Build tested: `build/s5/bin/foot2b` (mkg.ps1 -Block -Lift -Owner foot2 -Root E:/OOT/HeyListen-wt/foot2/engine, SLOT_PRIO=1, 696 s). It still holds the lazy rx page table (RX_PAGE_TABLE_LAZY, useless, removed from the source since); behind its off-by-default switch it changes nothing.
- Done then: allocations named (section 1); three cuts behind switches (section 2); the interleaved tour A2 / TR / ALL (section 3).
- Not done then: the pair under memhog. T3 gave f2-hA (hog 1750 MB, no switch): 83.0 fps, 387 frames over 50 ms, 91 page-fault stutters, avail min 430 MB. The ALL arm was refused by runguard (rc 11, a build started), and T4 (f2-hALL, f2-hA2) was cancelled right after its lease was granted: no data. Pictures at the zone changes were not checked (no shots taken); no unit tests run; no switch list regenerated for the new switches.
- Open then, still open: RX_VK_PCACHE_RELEASE costs the in-play pipelines' persistence (nothing is saved after the release).
