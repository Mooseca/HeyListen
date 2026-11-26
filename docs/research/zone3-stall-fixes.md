<!-- Copyright (C) 2026 Sacrappy -->

# ZONE3 (23 Nov 2026): the 600-present stall, the 30 s tick, zone-entry fixes

## Summary of this session (23 Nov, build zone3b)

**Neither stall is in a default run.** The 60-250 ms stall every 600 presents is `HeapSummary` in `memory_res_log()`, reached
only with `RX_VK_RES_LOG` or `RX_VK_LEDGER`; the 100-280 ms tick every 30 s is `HL_MEM_ACCOUNT=<s>`'s whole-address-space
`VirtualQuery` + `K32QueryWorkingSet` pass and `HOS_HOST_SPLIT`'s census, both off unless set. Measured on castle-move with
the same build: default = no frame over 100 ms (longest 46 ms); `RX_VK_LEDGER=30` = no frame on the 600 grid over 13.8 ms (the
handover's walk gave 12 hits of 63-83 ms); `HL_MEM_ACCOUNT=30 HOS_HOST_SPLIT=40,30` = two 133/137 ms frames, **30.6 s apart**.

The walk is now also opt-in (`RX_VK_RES_LOG_HEAPS=1`, commit 9063b51af) and, with it on, one heap a dump on a worker (the
residual: `HeapSummary` still holds a heap's lock for the tens of ms it walks it, so the 600 grid's worst frames are 42-73 ms
with that switch on). The default-on 600-present work (the texture stats block and one `K32GetProcessMemoryInfo`) measures
+0.2-0.4 ms on the grid frame (median 3.7 ms vs 3.45 ms at 290 fps): nothing to move.

Behind switches, all off by default: `HL_MEM_COLD_ZONE_QUIET=<s>` (no cold-page trim while a map loads and s seconds after),
`HL_SLEEP_STREAK_MS=<ms>` (a thread whose short sleeps follow each other waits on the timer instead of yielding in a loop),
`HL_PT_PREFETCH=1` (one `PrefetchVirtualMemory` before the renderer's first read of a texture's guest bytes; now also the BC1
alpha scan). On this build the tour A/B shows **no gain beyond run-to-run noise** for any of the three (back-to-back control
`t-def2` 127.2 fps / 15 hitches / 3.5 s against `t-q2` with the quiet switch 132.1 / 16 / 3.6; `t-s` and `t-p` in the same
band), and the castle runs show the quiet switch's page-level effect (a tenth of the pages coming back) without a frame-level
one.

## State (23 Nov 2026, 19:50; session finished, machine left clean)

Branch perf/zone3, base origin/main 968b39fbe (main has moved on to b6d20c1ae meanwhile; the three earlier commits plus three
new ones: `9063b51af` perf(vk) heap walk one heap a dump on a worker + astc_storage_alpha prefetch, `a056c7470` test(host)
short-sleep fixture models the streak, `c0d29fa38` docs(switches) regenerated, plus the research doc commits). Nothing pushed.

- **Build zone3b** (18:43, 253 s, BLOCK + PGO profile; `mkg.ps1 -Owner zone3` under its own build lease; log
  `E:\OOT\scratch-zone3\logs\build-zone3b.log`), the build every number below is from.
- **Tests**: `python -I -B tests/run_all.py` (llvm-mingw first on PATH, temp on E:) — after the two fixes, the suite fails only
  four: the known test_nup_paths, test_nup_read_name, test_renderer_new_handler, and `test_parallel_rb_refresh`, which fails on
  main HEAD too (b6d20c1ae: its fixture's cut of `gpu_buffer_bind` pulls `rbring_test_direct`/`mem_rec_value` without their
  declarations). Log `E:\OOT\scratch-zone3\logs\run_all.log`.
- **Lease**: `20261123-184944-zone3-slot-6f8d` (slot a, 90 min + 10), the castle series and the tour A/B under it; slot a's own
  exe/dll restored at 19:46 from `E:\OOT\scratch-zone3\slot-bak\a` and the lease released at 19:46. No helper process left.
- Tools (not in the repo): `E:\OOT\scratch-zone3\z3m.py` (fps and hitches from play+10 s), `z3tick.py` (long frames, spacing,
  mod 600), `z3dump.py` (the mod-600 frame's cost), `z3thirds.py` (fps per third), `scripts/*.sh` (slot swap, series, reports).

## The two stalls: the code

**600 presents, on the presentation thread.** `vk_replay.cpp:6945` calls `texture_frame(completed())` from the present path
(`vk_texture.cpp:5375`). Every 600 frames:
- line 5439: `K32GetProcessMemoryInfo` (one call) — default-on;
- line 5739 (`if (frame_no % 600 == 0)`): `vma_log_heaps()` (`vmaGetHeapBudgets`), `reap_report`, `vma_log_image_blocks`
  (`vmaCalculatePoolStatistics` per pool), the ASTC aggregation over every texture in `textures` (`std::map` insert per
  texture, two sorts) and its `logf` lines — default-on, and measured at +0.2-0.4 ms median on the grid frame (below);
- line 5836: `memory_res_log()` — **only when `res_log_on()`**, i.e. `RX_VK_RES_LOG` or `RX_VK_LEDGER`. Inside it
  (`vk_memory.cpp:8579`) `K32GetProcessMemoryInfo`, `GetProcessHeaps`, then `HeapSummary` for every heap: that walk is the
  60-250 ms. Now `RX_VK_RES_LOG_HEAPS=1` opts the walk in and it runs one heap a dump on a `jobs_push` worker (cache summed
  by the line); off, the figures read 0. `mem_kinds_log()` (`vk_vma.cpp:70`, the allocation map under `acct_mu`) follows, also
  only with the switch.
So: **the 60-250 ms stall needs a diagnostic switch**; a default run's only 600-present work is the stats block above, measured
at a fraction of a millisecond.

**Every 30 s.** `hl_mem.c:821` starts `account_main` only when `HL_MEM_ACCOUNT=<s>` is set (line 823); it sleeps s seconds
(346), then `VirtualQuery` over the whole address space (millions of regions; the address-space lock held per call), a qsort of
the private allocations, `K32QueryWorkingSet` over every resident page (holds the working-set lock, so every thread's page
faults wait), `K32GetProcessMemoryInfo`, `GlobalMemoryStatusEx` and `NtQuerySystemInformation` — the 100-280 ms the tick shows.
`HOS_HOST_SPLIT=<s>[,<every>]` (`host/hos_hostsplit.c`) starts its census thread only with its variable and walks the process's
11,866 regions (~684 ms); it is the second part of the tick. `HL_FAULT_WATCH` (also off by default) has a 30 s summary line of
its own (`hl_mem.c:798`).

## Castle-move runs (23 Nov 19:08, build zone3b, slot a)

`build/s5/z3b-*`, fps and hitches from `play: began` + 10 s (`z3m.py`), on `present_trace.csv`:

| arm | env | fps | >100 ms | >500 | longest |
|---|---|---|---|---|---|
| z3b-w (warm-up) | - | 107.8 | 0 | 0 | 81 ms |
| z3b-def | - | 109.7 | 0 | 0 | 46 ms |
| z3b-led | RX_VK_LEDGER=30 | 91.6 | 2 (0.3 s) | 0 | 153 ms |
| z3b-ledh | RX_VK_LEDGER=30 RX_VK_RES_LOG_HEAPS=1 | 88.3 | 2 (0.3 s) | 0 | 142 ms |
| z3b-acc | HL_MEM_ACCOUNT=30 HOS_HOST_SPLIT=40,30 | 111.6 | 2 (0.3 s) | 0 | 137 ms |
| z3b-q | HL_MEM_COLD_ZONE_QUIET=10 | 113.5 | 0 | 0 | 33 ms |
| z3b-s | HL_SLEEP_STREAK_MS=3 | 107.3 | 1 (0.1 s) | 0 | 100 ms |
| z3b-p | HL_PT_PREFETCH=1 | 108.7 | 0 | 0 | 100 ms |

- **The 600-present stall is gone with RX_VK_LEDGER=30**: no frame on the 600 grid over 13.8 ms (`z3dump.py`: at 0 mod 600
  median 3.0 ms, max 11.0; at 599 max 13.8), against the handover's 12 hits of 63-83 ms. `z3b-def`'s grid frames are 3.6-3.7 ms
  median (max 10.8) at a 3.45 ms run median — the default-on dump's cost.
- **With RX_VK_RES_LOG_HEAPS=1** the walk is on a worker but `HeapSummary` still holds a heap's lock while it walks it: the 600
  grid's worst frames are 42.6 ms (the first dump, before the worker finished), 56.5 and 73.2 ms (one heap each; the 12 heaps
  hold 651 MB in the first, so each walk is tens of ms and an allocating presenting thread waits). Better than every dump on
  the presenting thread, and this switch is a one-off diagnostic; with `RX_VK_LEDGER` alone nothing is walked.
- **The 30 s tick reproduced and named**: `z3b-acc` has exactly the tick: two >100 ms frames, 133 and 137 ms, **30.6 s apart**
  (`z3tick.py`, 23.3 s and 53.9 s after play began), nothing on the 600 grid. `z3b-def` (no switch) has no frame over 100 ms
  at all and no 30 s spacing.
- **HL_MEM_COLD_ZONE_QUIET=10 did what it says in the cold-page counters** (`hl mem: cold` in each `game_log.txt`): the quiet
  arm took out 1830 MB of pools / 615 MB of heaps and got back 115 MB / 70 MB, against the default arm's 2083 / 856 taken and
  1071 / 193 come back — a tenth of the soft faults back on the pools (the runs differ in length: 110 s quiet, 180 s default,
  and the default ran first after the warm-up).

## Tour A/B (23 Nov 19:46, build zone3b, slot a; 300 s arms, 7 warps each)

`build/s5/t-*`, fps and hitches from `play: began` + 10 s (`z3m.py`); every arm warped the same 7 maps (Market, HyruleField,
Kakariko, DeathMountainTrail, Goron, Dodongo, Market, from each `game_log.txt`). Warm-up first.

| arm | env | fps | >100 ms | >500 ms | longest |
|---|---|---|---|---|---|
| t-w (warm-up) | - | 133.9 | 17 (4.2 s) | 3 | 599 ms |
| t-def | - | 106.4 | 59 (13.5 s) | 4 | 748 ms |
| t-def2 | - | 127.2 | 15 (3.5 s) | 1 | 579 ms |
| t-q | HL_MEM_COLD_ZONE_QUIET=10 | 125.0 | 20 (4.5 s) | 2 | 712 ms |
| t-q2 | HL_MEM_COLD_ZONE_QUIET=10 | 132.1 | 16 (3.6 s) | 1 | 626 ms |
| t-s | HL_SLEEP_STREAK_MS=3 | 131.5 | 35 (10.1 s) | 3 | 1635 ms |
| t-p | HL_PT_PREFETCH=1 | 126.7 | 12 (2.9 s) | 1 | 546 ms |

- **t-def is an outlier, not a switch effect**: its first two thirds ran 122.4 and 128.6 fps with 1.4 and 1.7 s of long
  frames, its last third 68.3 fps with 43 frames over 100 ms (10.4 s, `z3thirds.py`); it stalled in a band from 155 to 190 s
  that no other arm has. The machine is the owner's desktop and other streams' games/builds shared it. `t-def` is left out of
  the comparison; **`t-def2` (back to back with `t-q2`) is the baseline: 127.2 fps, 15 frames over 100 ms (3.5 s), one over 500.**
- **HL_MEM_COLD_ZONE_QUIET=10 shows no tour gain**: q2 against def2 is 132.1 vs 127.2 fps and 16 vs 15 long frames (3.6 vs
  3.5 s), the same longest frame; the first q arm (125.0 / 20) is inside the same spread. Its cold-page counters in this pair
  were level too (2285 MB of pools taken out, 1387 back, against 2359 / 1222 in def2), unlike the castle runs above.
- **HL_SLEEP_STREAK_MS=3**: 131.5 fps but 35 long frames (10.1 s, 3 over 500) in its one run, its worst a 1635 ms frame at
  228.7 s; no gain shown, and its run may carry an unrelated end-of-run event (its first two thirds are 118.8 / 147.2 fps).
- **HL_PT_PREFETCH=1**: 126.7 fps, 12 long frames (2.9 s), 1 over 500, longest 546 ms — the best of the switch arms but inside
  the baseline's spread (12-20 long frames across the default and quiet arms).
- The 600-present grid is clean in every arm (`z3dump.py`: the frames on 0/599 mod 600 are 1.4-16.3 ms), and no arm has a 30 s
  rhythm: the long frames sit at the warps, ~40 s apart.
- So on this build and machine the three switches are **not shown to help** the warp tour; they are off by default and show no
  regression either. A cleaner A/B needs the machine to itself (a speed lease, `foot1_tour.sh`'s own lease).

## Handover notes (23 Nov 2026, 18:30; work stopped by the coordinator, kept for the record)

Branch perf/zone3 (from origin/main 968b39fbe), 2 commits at the handover. Nothing pushed. Leases released.

**600-present stall: found, it is an instrument.** `memory_res_log()` (vk_memory.cpp) calls `HeapSummary` on every process heap, on the
Presentation_Thread, every 600 presents (from `texture_frame`). `res_log_on()` is true only with `RX_VK_LEDGER` or `RX_VK_RES_LOG`. Stack samples
(`HL_STALL_WATCH_STACK`) of the 70-80 ms gaps: `ntdll heap walk <- KERNELBASE+0x1933ac (HeapSummary) <- memory_res_log+0x137 <- texture_frame`.
Bisect on castle-move, 110 s, build zone3a, `HL_HITCH_LOG=rel:8` plus: nothing (default): no stall at present 599 mod 600 (17,098 frames);
`HL_STALL_WATCH` + stack: none; `HL_MEM_ACCOUNT=30`: none; `HOS_HOST_SPLIT=40,30`: none; `HL_FAULT_WATCH=10`: none; `RX_VK_LEDGER=30`: yes
(12 hits of 63-83 ms at 599 mod 600); all five: yes (9 hits). **A default run does not have it** (also the 5-minute tour z3t-def: one 88 ms frame at 7199 only).

**30 s tick: not bisected at the handover. Not in a default run.** Cause by inspection: `HL_MEM_ACCOUNT` runs `K32QueryWorkingSet` over the whole process (millions of entries,
it holds the working-set lock, so every thread's page faults wait) plus a full VirtualQuery sweep; `HOS_HOST_SPLIT`'s census walks 11,866 regions.
Both are off unless set. In the default 5-minute tour (z3t-def) the stalls cluster after the warps, none on a 30 s grid. (This session reproduced
the tick at 30.6 s spacing with both switches on, see above.)

**Stack samples (task 4): `HL_STALL_WATCH_STACK=1`** (committed, built in zone3a, works). 4-minute tour z3t-sw (`HL_STALL_WATCH=100`): resolve with
`E:\OOT\scratch-zone2\z3res.py` / `z3idle.py` (maps in build/s5/bin/zone3a: HeyListen.map and hookshot_vk.map). Names found:
- `sead::MainThread` (the game main) blocked in `WaitLightEvent`: via `hl::bridge::Stages::await_done` / `loop::sleep_on_event` (a job group waiting for its workers),
  or `f_81207a50` event_wait (the lr 0x81207a6c event). The thread it waits for is busy or faulting: the loaders (`ARes_Loading_*`, page-fault storms),
  `host:mkw_vk_order` (370k faults, 1 s gap), `MovieOperateThread`, or the renderer on the "Presentation_Thread": `astc_bc_batched`, `upload_inner` /
  `bcc_bytes_hash` / `Tegra::Texture::UnswizzleTexture` (first-touch reads of guest texture pages), `create` -> `vmaCreateImage`,
  `graphics_pipeline` -> shader translation `Shader::Ampere::LowerToMaxwell` (a pipeline compiled at the zone entry), `ParLock` contention.
- Main also blocks in `sync_settle` mutex and `wait_recorded` -> `late_fix_wait_unlocked` -> `vk_timeline_wait_sent` (GPU/late-page waits).
- Only 2 of 20 gaps >= 100 ms had no thread busy at all (both the guest present thread in `SleepThread`); the "idle" class of ZONE2 is mostly a wait on a busy or faulting thread.
- The thread the game calls "Presentation_Thread" is a guest thread that also runs the renderer's replay inline.

**Switches added at the handover, off by default** (all built and run this session, see the tables):
- `HL_MEM_COLD_ZONE_QUIET=<s>` (hl_mem.c, hos_main.c: no trimming while Sequence_IsLoadingBanc and s seconds after).
- `HL_SLEEP_STREAK_MS=<ms>` (hos_thread.c: a thread's short sleeps that follow each other go on the timer for the rest of the streak).
- `HL_PT_PREFETCH=1` (vk_texture.cpp `prefetch_guest`, PrefetchVirtualMemory on the texture's source bytes before the read; this session
  also covered the BC1 choice's `astc_storage_alpha`).
