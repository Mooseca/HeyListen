<!-- Copyright (C) 2026 Sacrappy -->

# ZONE4 (23 Nov 2026): read a zone's pages ahead when its map loads again

Stream zone4, branch `perf/zone4` (worktree `E:\OOT\HeyListen-wt\zone4`, from `origin/main` 0e5db2102).
Scratch: `E:\OOT\scratch-zone4`. Lease name: zone4. Nothing pushed.

## Summary

`HL_ZONE_PREFAULT=1` (off by default) records, per map, the pages a zone load first touches, and reads them back on a
low-priority worker when that map loads again. It works as designed: 0.07-0.34 GB a map, 200-230 MB/s, and the loaders'
own page-ins in the load windows fall 9-27 %. **It is not shown to help**: over two pairs on one build (off/on/off/on,
300 s warp tours) the seconds of frames over 100 ms in the map windows went 6.12 → 6.02 s and 7.16 → 4.51 s, and fps went
143.2 → 139.4 and 146.5 → 132.8 (the switch arms are the two lower ones); the two pairs disagree by more than either
difference. Two causes are in the logs: (1) the `map:` line comes 3-6 s after the load starts, so the read-ahead runs
alongside the loaders, not ahead of them; (2) this machine has 0.34-0.75 GB of RAM free during play (a 16-17 GB working
set), so what is read ahead is partly taken out again and faulted back — in the second pair the total page-ins rose by
about the volume read ahead. A memory-hog pair was attempted and is not usable (see below: the off arm's start-up took
140 s against the on arm's 62 s, so the arms warped 5 and 7 maps). Recommended next step: trigger on the *region* the
load allocates (`hos_region_alloc`), which exists earlier and also on a first visit, and only read ahead when the free
RAM is really there.

## State

- 00:30 — done. Series 2 (the A/B) and the memory-hog attempt are in the notes below; the notes' numbers are from build
  z4 of 21:28:43. Branch `perf/zone4`: `5f9d44f7c` (the feature), `3e4387175` (the copy-size fix and the RAM
  budget), `5dcd67c85` (init hardening), `21abd04c7` (this study), `b83df5064` (switch reference). Nothing pushed.
  Leases released (`20261123-202102-zone4-speed-3854`, `20261123-213012-zone4-speed-1c8d`,
  `20261123-222020-zone4-speed-2194`); no game and no helper of this session is running; slot c holds its own binaries
  again (22 Nov 08:42, from `E:\OOT\scratch-zone4\slot-bak`).
- Tests at the end: `python -I -B tests/run_all.py` — **505 passed, 3 failed**, the three known (`test_nup_paths`,
  `test_nup_read_name`, `test_renderer_new_handler`). Log `E:\OOT\scratch-zone4\logs\run_all3.log`.
- 21:35 — first A/B series (21:01-21:20, speed lease `20261123-202102-zone4-speed-3854`): the **warm-up and on1 arms
  crashed** — `zp_close`'s page copy used `sizeof pages[0]` (8, a pointer) where the element is 4 bytes, so `memcpy`
  over-read the recorder's buffer; 6 would-be maps were recorded but only 1 reached the file. Fixed in `3e4387175`
  (also: the free-RAM floor is now a budget — the playback reads what is available above 512 MB instead of nothing when
  free RAM is low, which is what stopped the repeat Market warp in on2; and `HOS_GUEST_PAGES` / `HOS_POOL_TRAP` pages
  are left alone). Rebuilt (21:28:43, the build the tables below come from), then `5dcd67c85` hardened the init (one
  thread reads the switches; every recorder buffer is checked) — that one is in HEAD but not in the measured binary;
  it changes no path a normal run takes.
- Series 2 (21:30 on, clean `COMMON`: `HL_HITCH_LOG`, `HL_STALL_WATCH`, `HL_FAULT_WATCH` only — no `HL_MEM_ACCOUNT`,
  `HOS_HOST_SPLIT` or `RX_VK_LEDGER`, whose 30 s and 600-present passes are ~20 s of instrument stalls a tour and would
  drown a few-second effect): warm-up then `z4c-off1 z4c-on1 z4c-off2 z4c-on2`.
- 20:20 — the feature is written, tested and committed (`perf(host): read a zone's pages ahead when its map loads again
  (HL_ZONE_PREFAULT, off by default)`, `5f9d44f7c`): `engine/host/hos_zoneprefault.c` (new), declarations in
  `engine/host/hos.h`, the two hooks in `engine/host/hos_main.c` (`map:` line, `Sequence_IsLoadingBanc`), the page feed
  in `engine/host/hl_mem.c` (`HL_FAULT_WATCH`'s thread is the one reader of the kernel's list),
  `engine/tests/test_zone_prefault.py`, and the regenerated switch reference (`docs/SWITCHES.md`,
  `engine/docs/switches.json`).
- Build z4 (BLOCK + PGO, `mkg.ps1 -Owner zone4 -Root E:/OOT/HeyListen-wt/zone4/engine`), rebuilt after each change; the
  binary measured is named in the table.
- Tests: `python -I -B tests/run_all.py` (llvm-mingw first on PATH, temp on E:) — 504 passed; only the known
  `test_nup_paths`, `test_nup_read_name`, `test_renderer_new_handler` fail. Log `E:\OOT\scratch-zone4\logs\run_all2.log`.

## What ZONE2 and ZONE3 found (the brief this follows)

`docs/research/zone2-zone-entry-stalls.md` (in the zone2 worktree): 52-56 % of the stall time around a zone entry is
page faults — the loaders (`ARes_Loading_0/1`, `Resource_Memory`) first-touching fresh guest memory while they read and
ZSTD-decompress (20-30 %), the renderer (`Presentation_Thread`, `mkw_vk replay worker`) first-touching guest GPU pools
and host buffers (26 %). Stalls fall 2-10 s after a warp, and the game's main thread is then waiting at `WaitLightEvent`
for the busy or faulting thread. Its rank-1 fix: record per map what a load first touches, and touch it ahead on a
worker at the next load — one helper, two callers (loaders and renderer).

`docs/research/zone3-stall-fixes.md` (in the zone3 worktree): the 600-present and 30 s stalls are the diagnostic
switches themselves, not the zone entry; three switches (`HL_MEM_COLD_ZONE_QUIET`, `HL_SLEEP_STREAK_MS`,
`HL_PT_PREFETCH`) showed no gain beyond run-to-run noise on one build; a cleaner A/B needs the machine to itself under a
speed lease.

## The design (as built)

See the comment at the top of `engine/host/hos_zoneprefault.c` for the full text; the short form:

- **Recording**: the kernel's list of the pages added to the working set (`K32GetWsChangesEx`, the list
  `HL_FAULT_WATCH` reads) is drained every 100 ms while a load runs. When `HL_FAULT_WATCH` is set (it is in
  `foot1_tour.sh`'s common environment) its thread feeds the pages to the recorder, so there is one reader, not two.
  Guest pages at or above the heap are kept by class (address regions, GPU pools, heap), plus pages of tagged host
  ranges; the rest of the host's memory is not a zone's. First-touch order is kept, per-class caps: 512 MB in all
  (5/8 regions, 3/16 pools, 1/16 heap, 1/8 host).
- **Window**: opens when `Sequence_IsLoadingBanc` rises (polled at 500 ms by `oot_inventory_refresh`), closes
  `HL_ZONE_PREFAULT_SECS` (15) s after the `map:` line changed, or 40 s after it opened with no map named.
- **Playback**: at the `map:` line, the pages of that map's last visit are read on a `THREAD_PRIORITY_LOWEST` worker,
  class by class in address order, with `PrefetchVirtualMemory` per run and one byte read of every page (a reserved
  guest page is committed by the engine's own first-touch handler, `mkw_glue.c commit_on_touch`, as the game's own
  touch would be). 10 ms of work, then `Sleep(1)`; it stops on the next map, at the cap, or under
  `HL_ZONE_PREFAULT_LOWMEM_MB` (2048) MB of free RAM.
- **Table**: in memory for the session; `HL_ZONE_PREFAULT_FILE=<path>` keeps it in a small text file between runs (so
  the second visit to a zone is the one that reads ahead). Off by default (`HL_ZONE_PREFAULT=1`).
- **`HL_REGION_KEEP`** (20 s by default, `host/hos_regionkeep.c`): a region freed and re-allocated within those 20 s is
  still resident and zeroed on the caller's thread, so the read here is a load, not a fault — the two are compatible and
  `HL_REGION_KEEP` covers a shorter gap than this does. `HL_MEM_COLD` can take pool pages out again between the read and
  the loader's use.

## Method

Same build, same slot, `HL_ZONE_PREFAULT` off against on, two pairs (A B A B), the warp tour of `foot1_tour.sh`
(copied to `E:\OOT\scratch-zone4\z4_tour.sh`, arms shortened to fit one speed lease; same arms, sampler, run guard and
common instruments). Numbers: fps from `play: began` + 10 s, frames over 100 and 500 ms, longest frame
(`E:\OOT\scratch-zone4\z4m.py` on `present_trace.csv`); page faults from the sampler's `build/s5/<tag>.mem.csv` and
from the log's own `hl fault` lines (with the `hl pf` lines counting what was recorded and read ahead). Per map:
`E:\OOT\scratch-zone4\z4w.py` sums the frames over 100 ms in the 6 s before and 12 s after each `map:` line — the load's
stall band, and the same warps in the same order in every arm.

A warm-up arm (200 s, `HL_ZONE_PREFAULT=1`, the table file) runs before the four arms and fills the table, so the arms
are not first visits: the question this feature answers is "the map was visited before", and the tournament's cold first
visit is its no-op case. The off arms carry the same table file path but not the switch, so they neither read nor write
it.

## Known limit of this build

The read of a page is guarded by `VirtualQuery` (committed, readable, no guard page) and by nothing else: with
`HOS_POOL_TRAP` or `HOS_GUEST_PAGES` on, a page can be made `PAGE_NOACCESS` between the query and the read, and
`mkw_glue.c commit_on_touch` then declines the fault instead of fixing it. Both are off by default (and off in the
build measured below), so this is a follow-up before the switch is offered to players: a `__try`/`__except` around the
byte read, or skipping pools when `hos_pool_trap_active()`.

## First attempt (21:01-21:20, build z4 of 20:18:16) — not the measurement

`z4m.py` (fps and frames from `play: began` + 10 s; faults from `build/s5/<tag>.mem.csv`; page-ins from the `hl fault`
lines):

| arm | env | frames | fps | >100 ms | >500 | longest | faults | min free RAM |
|---|---|---|---|---|---|---|---|---|
| z4-warm | PF=1, file | 2110 | 91.7 | 7 (1.3 s) | 0 | 448 ms | 2.81 M | 4784 MB |
| z4-off1 | - | 24528 | 106.6 | 63 (14.5 s) | 4 | 1219 ms | 5.83 M | 832 MB |
| z4-on1 | PF=1, file | 3727 | 119.5 | 13 (2.9 s) | 0 | 481 ms | 3.94 M | 4003 MB |
| z4-off2 | - | 28909 | 123.2 | 53 (12.2 s) | 4 | 1263 ms | 6.35 M | 576 MB |
| z4-on2 | PF=1, file | 27268 | 119.9 | 61 (12.2 s) | 4 | 584 ms | 6.49 M | 554 MB |

- `z4-warm` and `z4-on1` **crashed** in `zp_close` after their second map (the 4-vs-8-byte copy); their frames stop
  there and the table file held 1 map, so the arms after them had almost nothing to read ahead (on2 read 285 MB at its
  first map and then its records were first visits).
- What the logs already show working: `Market_Child` read ahead 72,946 pages (284.9 MB) in 1408 ms (203 MB/s on the
  low-priority worker), `HyruleField_Child` recorded 73,285 pages over 8839 runs; the last `Market_Child` warp in on2
  was **stopped at 0 pages: less than 2048 MB of free RAM** — which is why the floor became a budget in `3e4387175`.
- Per map (`z4w.py`, frames over 100 ms in [map-6 s, map+12 s]; the first row of each is the start-up load, which
  ZONE2 keeps out of zone-entry numbers):

| arm | start-up Market | HyruleField | Kakariko | DeathMtn | Goron | Dodongo | Market again | all |
|---|---|---|---|---|---|---|---|---|
| z4-off1 | 8.42 s | 3.47 | 2.63 | 0.35 | 1.21 | 0.66 | 1.26 | 18.0 s |
| z4-off2 | 5.48 s | 3.14 | 0.81 | 2.26 | 1.23 | 2.06 | 1.43 | 16.4 s |
| z4-on2 | 14.14 s | 4.42 | 1.18 | 1.05 | 0.27 | 0.67 | 1.59 | 23.3 s |

  All three arms are start-up dominated and on2's start-up row is the worst; with one map in the table and every other
  map a first visit this says nothing about the feature yet, and the start-up window is where the prefetch competes with
  the first load. It is also the reason to read the rerun's rows per map, and to treat the first row apart.

## Series 2 — the A/B (22:19-22:19, build z4 of 21:28:43, lease `20261123-213012-zone4-speed-1c8d`)

Same build, slot c, one speed lease; arms `z4c-off1 z4c-on1 z4c-off2 z4c-on2` of 300 s (7 warps: Market, HyruleField,
Kakariko, DeathMountainTrail, Goron, Dodongo, Market), a 200 s warm-up arm with the switch on first. The common
environment is the clean one — `HL_HITCH_LOG=rel:8 HL_STALL_WATCH=rel:8 HL_STALL_WATCH_MAX=400 HL_FAULT_WATCH=10` — so
`HL_MEM_ACCOUNT` / `HOS_HOST_SPLIT` / `RX_VK_LEDGER` (the 30 s tick and the 600-present stall, ~20 s a tour) are out.
`HL_FAULT_WATCH` stays: the recorder rides on its page list.

`E:\OOT\scratch-zone4\z4m.py` (fps and frames from `play: began` + 10 s; faults from `build/s5/<tag>.mem.csv`):

| arm | env | frames | fps | >100 ms | >500 | longest | faults | worst 30 s | min free RAM | WS peak |
|---|---|---|---|---|---|---|---|---|---|---|
| z4c-off1 | - | 33548 | **143.2** | 28 (6.8 s) | 2 | 631 ms | 5.93 M | 125 k/s | 563 MB | 16.9 GB |
| z4c-on1 | PF=1 | 32420 | 139.4 | 28 (6.2 s) | 2 | 1003 ms | 5.39 M | 147 k/s | 754 MB | 16.3 GB |
| z4c-off2 | - | 33441 | **146.5** | 55 (9.1 s) | 2 | 632 ms | 6.06 M | 114 k/s | 526 MB | 17.1 GB |
| z4c-on2 | PF=1 | 31933 | 132.8 | 18 (4.7 s) | 1 | 560 ms | 6.32 M | 147 k/s | 337 MB | 17.5 GB |

What the read-ahead did (the `hl pf` lines; `z4c-on1` / `z4c-on2`):

| arm | maps recorded | read ahead | of which first visits (nothing to read) | budget-refused |
|---|---|---|---|---|
| z4c-on1 | 7, 926 MB | 5 maps, 872 MB (223,252 pages) | 2 | 0 |
| z4c-on2 | 7, 835 MB | 6 maps, 685 MB (175,452 pages) | 0 | 1 (free RAM under 512 MB at the last warp) |

Examples from `z4c-on2`'s log: `HyruleField_Child (child): reading ahead the 87857 pages (343.2 MB) … in 1497 ms`;
`Market_Child (child): read 36287 pages (141.7 MB) of the 131072 it may (512.0 MB of RAM to read into) in 589 ms`;
`KakarikoVillage_Child (child): 39899 pages (155.9 MB) in 754 ms` — 200-230 MB/s on the low-priority worker, and no page
it could not read. That is the mechanism working as designed.

Per map (`z4w.py`: frames >100 ms in [map - 6 s, map + 12 s], and the page-ins the log counts in that window, `M` =
millions of pages; the first row is the start-up load, which ZONE2 keeps out of zone-entry numbers):

| arm | start-up Market | HyruleField | Kakariko | DeathMtn | Goron | Dodongo | Market again | windows, >100 ms | loaders' page-ins |
|---|---|---|---|---|---|---|---|---|---|
| z4c-off1 | 3.45 s | 0.76 | 0.75 | 1.75 | 1.06 | 0.70 | 1.10 | 9.58 s | 0.52 M |
| z4c-on1 | 5.85 s | 1.83 | 0.62 | 0.46 | 0.14 | 1.45 | 1.52 | 11.86 s | 0.38 M |
| z4c-off2 | 8.18 s | 2.85 | 1.24 | 0.89 | 0.31 | 0.94 | 0.93 | 15.35 s | 0.46 M |
| z4c-on2 | 3.35 s | 1.41 | 0.62 | 0.28 | 0.14 | 1.17 | 0.89 | 7.85 s | 0.42 M |

Without the start-up row: off1 6.12 s / on1 6.02 s (−2 %); off2 7.16 s / on2 4.51 s (−37 %). Total page-ins in the same
windows: 0.98 M → 0.97 M (pair 1), 0.89 M → 1.08 M (pair 2, +21 %, about the 835 MB it read ahead: the pages came in a
second time for the loaders).

**Reading**: the read-ahead does what it was built to do — the loaders' page-ins in the load windows fall 27 % (pair 1)
and 9 % (pair 2), and the pages are read at 200 MB/s on a thread nobody waits for. But **it does not show a win**: the
stall seconds of the map windows fall in the second pair and not in the first (and the two pairs disagree by more than
either difference), and **fps does not rise** (139.4 against 143.2, 132.8 against 146.5 — the switch arms are the two
lower ones). The likely reasons, and what the logs say:

1. **The map line is too late.** It comes 3-6 s after the load starts (the warp at 55 s, the map line at 59 s, the
   loader storms from 58 s in `f2-A1`'s log), so the read-ahead starts inside the storm it means to pre-empt and runs
   alongside the loaders on the same pages instead of ahead of them.
2. **The machine has no RAM to read into.** 337-754 MB available during play with a 16-17 GB working set: in `z4c-on2`
   the last warp was refused outright (512 MB floor) and the pair's total page-ins rose by about what was read ahead —
   the prefetched pages were taken out again and faulted back on the loaders' threads. The floor is doing its job; the
   budget it grants (512 MB of cap, 200-500 MB of RAM) is what the machine cannot hold.
3. The tour visits six maps and repeats one: 5-6 read-aheads a 300 s arm is the most this design can do, and each is
   worth 0.1-0.34 GB against a load that faults 0.4-0.5 M pages (1.6-2 GB) in its window.

## The memory-hog attempt (23:32-23:40, lease `20261123-222020-zone4-speed-2194`) — not a pair

`z4_series.sh z4 300 0 700` (2 arms, hog target 700 MB free; the switch arm also `HL_ZONE_PREFAULT_LOWMEM_MB=256`).

| arm | frames | fps | >100 ms | >500 | longest | faults | min free RAM | play began at |
|---|---|---|---|---|---|---|---|---|
| z4h-off | 15880 | 106.1 | 33 (8.0 s) | 2 | 1093 ms | 5.33 M | 736 MB | 139.6 s |
| z4h-on | 27437 | 120.7 | 57 (13.8 s) | 3 | 1163 ms | 6.00 M | 544 MB | 62.5 s |

The arms are not comparable: the off arm's start-up took 139.6 s against the on arm's 62.5 s (both runs are 300 s wall
clock), so the off arm fitted 5 warps and the on arm 7. In the five maps both visited, the >100 ms seconds were
HyruleField 2.50 / 2.76, Kakariko 2.76 / 1.73, DeathMountainTrail 1.35 / 0.31, Goron 0.42 / 0.64, and the start-up Market
18.50 / 10.08 (off / on) — no direction. The read-ahead itself behaved (296 MB in 695 ms, 282 MB in 1525 ms, budget
reduced to 464 MB of 512 for HyruleField). A usable hog pair needs two runs with the same start-up, which this machine's
queue did not allow tonight.

## What is not known, and what to do next

- The two A/B pairs disagree (one −2 %, one −37 % on the map windows). The variance comes from the start-up row (3.35-8.18 s
  of frames over 100 ms in the first map window of every arm, which is the load ZONE2 keeps out of zone-entry numbers) and
  from the machine's free RAM, not from the switch. A cleaner test would need 4-6 pairs on an idle machine and the
  start-up rows apart.
- Whether the read-ahead's cost (a low-priority thread reading 0.2-0.9 GB a run, and its pages competing with the
  loaders' when RAM is short) is what made both switch arms the lower-fps ones cannot be told from two pairs.
- The two changes that the data points to, in order:
  1. **Trigger on the region, not the map line**: a load allocates its arena (`hos_region_alloc`) early — before the
     `map:` line — and on a first visit too. Reading ahead the first N MB of a freshly allocated large region (capped,
     with the same free-RAM budget) would run ahead of the loaders instead of beside them, and would not need the
     per-map table at all; the table remains useful for the GPU pools and the renderer's pages.
  2. **Only where there is RAM**: a floor high enough that the pages stay resident until the loader reads them (this
     machine's 0.3-0.8 GB free during play is below what a 512 MB cap needs), or a much smaller cap per warp (e.g.
     64-128 MB, the pages the load touches first, in first-touch order rather than address order).
- The switch is off by default and stays so; nothing here argues for turning it on.

- Build z4's log line and time; the A/B table; what the `hl pf` lines say (how much was recorded per map, how much was
  read ahead, how long it took, how often the free-RAM floor or a map change cut it short); the memhog pair; what the
  first visit to a map does (nothing) and whether the file between arms changes that.
