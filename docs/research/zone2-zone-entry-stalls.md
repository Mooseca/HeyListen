<!-- Copyright (C) 2026 Sacrappy -->

# ZONE2 (23 Nov 2026): what the long stalls at zone entries are, by cause, and what to fix

Analysis of existing logs only (no game run). Warp tour (`foot1_tour.sh`: 15 warps, one every 40 s, 11 minutes, Market save, env
`HL_HITCH_LOG=rel:8 HL_STALL_WATCH=rel:8 HL_STALL_WATCH_MAX=400 HL_MEM_ACCOUNT=30 RX_VK_LEDGER=30 HOS_HOST_SPLIT=40,30 HL_FAULT_WATCH=10`).

- Main PC (RTX 5070): `f1-A1`, `f1-ALL1`, `f1-warm`, `bc7c-off` (4 runs).
- PC 3050: `f3-A1 A2 ALL1 ALL2 warm` and the memory-hog runs `f3-hA1 hA2 hALL1 hALL2` (9 runs).
- Stalls = frames of 100 ms or more in `present_trace.csv`, matched to the log's `stallwatch: gap` blocks (per-thread CPU, where each
  thread was at the 10 ms mark, page faults, working-set change) by length and order (stutter_report.py's `align`), and to the
  `hl fault` lines (page-ins by thread and by memory kind, one a second) by time. Thread places are resolved with the build's
  `HeyListen.map` and the local ntdll's exports (`ZwReadFile`, `ZwAllocateVirtualMemory` ...). Two job-trace dumps (below) were the
  only stack-like evidence that survived.

## 1. Headline

1. **A third of the main PC's stall time in these tours, and a seventh of the 3050's, is made by the diagnostics themselves.** Two
   kinds, both outside zone entries. Do not read "196-254 over 100 ms a tour" as zone-entry cost.
2. Of the rest, **page-fault storms are 52-56 % of the stall time on both PCs**: the loaders (`ARes_Loading_0/1`, `Resource_Memory`)
   first-touching fresh guest memory while they read and ZSTD-decompress, and the renderer (`Presentation_Thread`,
   `mkw_vk replay worker`) first-touching guest GPU pools and host buffers. 400k+ faults in one frame is a 1.4 s stall.
3. **24-31 % is "idle": no thread in the process burns CPU for 100-300 ms** (the game's main thread waits for an event the presenting
   thread signals, and the presenting thread is not running or not waiting on anything the job trace sees). It is the biggest cause
   no log here can name. It needs one stack sample (section 5).
4. Game scene setup (guest threads busy, or all game threads spinning in `sleep_away`) and renderer CPU are small: 5-11 % together.

## 2. Instruments (not zone entries)

| artefact | what it looks like | stalls >=100 ms, main (4 runs) | 3050 (9 runs) | evidence |
|---|---|---|---|---|
| 600-present periodic | one stall of 60-250 ms every 600 presents (frame number = 599 mod 600), 0 page faults, `Presentation_Thread` at 100 % CPU inside an ntdll heap routine (`ntdll+0x605fa..0x61084`, a walk of a linked list of 0x3f0-byte nodes: the shape of a heap free/lookup) | 174, 21.3 s, median 121 ms | 256, 40.9 s, median 156 ms | it grows with the run (92 ms at 0:00, 150 ms at 10:00 on f1-A1); it sits at the 600-present stats dump (`vk: mirror syncs (600 submits)` ... lines follow the gap block); **absent from the earlier warp tours without this env** (`main-tour`, `mainck-tour`, `mainck-tour2`, `mainck-tour6`, `p102-tour`, 10k-23k frames each: no peak at 599) and present in every run with it (all 4 main runs here, `bc7c-cold*`, `bc7c-warm`, `f2-*`, all 9 on the 3050) |
| 30 s tick | all threads idle for 100-280 ms (median 199 ms main, 261 ms 3050), every 30.7 s, in two series: at the `HOS_HOST_SPLIT` census (40 s + 30k, the log prints it 0.3-1.3 s after the stall ends) and 5-8 s after it | 90, 18.7 s | 180, 45.6 s | census "684 ms to walk 11866 regions" walks the heaps (a heap walk holds the heap locks every thread allocates under); `hl mem: account` says "the pass took 200-470 ms" at the same cadence |
| start-up | the Market's first load, first 36 s | 38, 14.6 s | 139, 48.4 s | not a zone entry; kept out of the rest |

Which of `HL_MEM_ACCOUNT` / `RX_VK_LEDGER` / `HOS_HOST_SPLIT` / `HL_FAULT_WATCH` makes the 600-present stall is not known (the 600-present
stats code runs in every run; what grows is something the instruments feed). The claim "it is an artefact" rests on the 12 clean tours
(none at 599, but older builds) and the monotonic growth, not on a bisect.

Per tour, stalls of 100 ms or more, instruments and start-up removed: **main 13-18 s (16 s mean), 3050 42-48 s (45 s mean; 66-70 s with the memory hog)**.

## 3. Share of stall time by cause (stalls >=100 ms, instruments and start-up removed)

| cause (primary, by the rules in 3.1) | main: stalls, s, share | 3050: stalls, s, share |
|---|---|---|
| page-fault storm / working-set trim, faulted by the loaders | 103, 19.3 s, 30 % | 243, 97.0 s, 19.5 % |
| ... by the renderer (`Presentation_Thread`, `mkw_vk replay worker`, `mkw_vk_order`) | 63, 16.3 s, 26 % | 289, 130.3 s, 26 % |
| ... by game threads / other | 1, 0.2 s, 0.3 % | 27, 31.4 s, 6.3 % (13 game, 14 other) |
| **page faults in all** | **167, 35.8 s, 56 %** | **559, 258.7 s, 52 %** |
| idle, no thread busy (blocked) | 94, 19.8 s, 31 % | 478, 118.1 s, 24 % |
| no gap block (20 gaps a second cap, or no match) | 8, 1.6 s, 2.6 % | 196, 48.7 s, 9.8 % |
| game scene setup, game threads busy (`BaseProcCreateAndDeleteThread`, `ModuleSystemWorker*`) | 17, 2.7 s, 4.2 % | 116, 31.2 s, 6.3 % |
| game waits in SleepThread (all game threads spin in `sleep_away`) | 3, 0.4 s, 0.6 % | 67, 20.4 s, 4.1 % |
| our renderer busy (`Presentation_Thread` CPU, no faults) | 24, 3.4 s, 5.4 % | 109, 18.0 s, 3.6 % |
| game loading busy (loader CPU, no faults) | 0 | 16, 2.7 s, 0.5 % |
| total | 313 stalls, 63.8 s over 4 runs | 1,541 stalls, 497.7 s over 9 runs |

By the brief's groups (faults split to the thread that took them, idle apart): **game loading about 30 %** (main) / 20 % (3050);
**game scene setup 5 %** (main) / 13 % (3050); **our renderer about 31 %** (main) / 30 % (3050); idle and unmatched 34 % / 34 %.
The page-fault rows are the cross-cutting cause: the same stall is "loading" or "renderer" by who faulted.

Time after the warp (non-instrument stalls): main 2-10 s (182 of 312 stalls, 58 %); 3050 4-10 s (822 of 1,542, 53 %). A third of the
stalls (main 35 %, 3050 32 %) fall 12-40 s after the warp: mid-zone idle stalls and game scene work, not the load.
By zone, total per run: Hyrule Field 3.3 s (main) / 11.8 s (3050), Market 3.0 / 8.3, Dodongo 1.9 / 7.9, Goron 1.0 / 6.3, Kokiri 2.2 / 4.3.
The memory hog (`hA*`, free RAM low) adds 20-25 s a tour on the 3050, almost all in the page-fault rows.

### 3.1 Rules

Per stall: a gap with >=5000 faults, or a working-set change of 50 MB or more, or >=1000 faults at >=20 a ms, is a page-fault stall,
split by the top thread of the `hl fault` second that covers it. Else a non-spinning thread with >=0.8 Mcycles per ms of the gap is the cause (loader,
game, renderer by thread name); else three or more game threads at `sleep_away` (`a64_svc`) is "game waits in SleepThread"; else idle.
`sleep_away` pause loops, `spin_until_set` and QPC spins are not counted as work. A thread's place is where it was 10 ms into the gap:
one sample, not a stack. The `hl fault` lines come once a second and only above 2000 pages, so the faulting thread of short stalls is
inferred (the line that covers the stall's end); the faults rows are good to a thread class, not to a call site.

## 4. Where the time goes: top call sites

Non-instrument, non-start-up stalls >=100 ms.

| # | site | main | 3050 | what it is |
|---|---|---|---|---|
| 1 | `ARes_Loading_0/1`, `Resource_Memory`: first touch of "guest: address regions" memory inside `ZSTD_decompressSequences*` and `ZwReadFile` into fresh guest buffers (`ARes_Loading_*` are the game's resource loader threads) | 51+22+5 stalls, 14.8 s, 23 % | 73+60+24, 52 s, 10.5 % | the game reads a zone's archives, decompresses into newly committed guest memory, and every 4 KB page faults in (zero-fill) on the loader thread; the zone's loaders touch 40-120k pages a second |
| 2 | `Presentation_Thread` first-touch of "guest: GPU pool" and host private pages (`hookshot_vk.dll+0x397a67`, `+0x3868c3`, `+0x3aa6cd`, `ZwAllocateVirtualMemory` in three) | 17+8+5+2, 8.9 s, 14 % | 64+38+..., 45.7 s, 9 % | the renderer's reads of guest GPU pools (mirror sync, capture) and its own allocations fault in the pages the game or the loaders just wrote and the trim took out; the main thread then waits for the presenting thread |
| 3 | `host:mkw_vk replay worker`, `mkw_vk_order`: first touch of host private / `host tag: vk captures` | 6, 1.4 s, 2 % | 30+28+14, 39.6 s, 8 % | the capture copies and replay workers of the renderer, same mechanism |
| 4 | idle: the game's main thread blocked on the event at guest `lr 0x81207a6c` (signalled by `Presentation_Thread`; the presenting thread waits 0.3 ms on the frame hand-off queue and runs almost no CPU) | 94, 19.8 s, 31 % | 478, 118.1 s, 24 % | job-trace dumps `stall_168` (131 ms, 42 faults), `204` (125 ms, 0 faults), `395` (150 ms, 18 faults) of f2-TR: main thread 119-141 ms in that event, workers in their queues, loaders parked; **nothing runs**. A blocking call the job trace does not see (a host lock, the driver, a GPU wait, a log write) |
| 5 | game threads: `BaseProcCreateAndDeleteThread` (guest `f_81a77fe0`, 500-1600 Mcycles, 119-150 ms; `f_814efd20+0x151a` 2500 Mcycles on the 3050's first load), and all five game workers spinning in `sleep_away` (up to 900 Mcycles each, 350-400 ms, the 3050) | 17+3, 3.1 s, 5 % | 116+67, 51.6 s, 10 % | the game's own scene build, the game sleeping in guest `SleepThread` while its loaders work: our spin loop burns CPU but the cause is the game's wait |

For comparison, the rows that are not zone entries: the 600-present stall at `Presentation_Thread @ ntdll heap walk`, and the 30 s ticks.

Other facts the logs gave:
- The fault storms are real work, not an accounting error: 427,785 faults / 1,382 ms, 130,307 / 366 ms, 110,653 / 258 ms, 102,832 / 540 ms
  (2.4 to 5 us a fault over the stall); `hl fault` shows 20-40k pages added a second in the quiet seconds of a load and 500k+ in the worst.
- In 14 of the 20 long stalls with job-trace dumps (f2-TR) the main thread's longest wait is the event the presenting thread signals
  (guest `lr 0x81207a6c`); in the rest it is the event the game's own workers signal (`lr 0x80706d40`, `0x802ead44`). So most long stalls end at the
  presenting thread even when the loaders caused them; fixing renderer-side first touch helps both.
- ntdll's own names for what the threads were in: `ZwWaitForAlertByThreadId` (parked), `ZwWaitForSingleObject` (`hos_audio`, `hos_held_submits`, the GPU or
  file waits), `ZwReadFile` / `ZwCreateFile` (a thread there at the mark in 29 of the 94 idle stalls on main, 5.3 s of the 19.8 s), `ZwAllocateVirtualMemory`
  (the commits in front of a fault storm).

## 5. Fixes, ranked by gain and effort

Gain is on the real stall time per tour (main 16 s, 3050 46 s), from the shares above; it is an upper bound until measured.

| rank | fix | cause | gain | effort | notes |
|---|---|---|---|---|---|
| 0 | Cut the instruments from stall measurements: no `HOS_HOST_SPLIT` census, no `HL_MEM_ACCOUNT=30` / `RX_VK_LEDGER=30` passes while counting stalls (or run them on a worker, off the heap locks), and find what grows in the 600-present dump | measure | corrects 34 % (main) / 14 % (3050) of the counted stall time; if the 600-present stall also exists in a clean run (not seen in 12), it is the cheapest real win: 60-250 ms every 10 s | S (env) + S (bisect, 3 runs of 4 min) | do first: every later A/B is measured against numbers that carry a 20 s per tour instrument floor |
| 1 | **Prefault the zone's memory ahead of the loaders**, on a worker, while the game fades out (the warp's 1-3 s before the first load stall): record per zone the guest address-region and GPU-pool page counts of the last visit (`hl fault` already counts them), and touch them with `PrefetchVirtualMemory` / a write to the first byte of each page in 2 MB steps on idle cores; keep `HL_REGION_KEEP` resident for the zone just left | loaders' faults (30 % main, 20 % 3050) | up to 4-5 s per tour main, 9-10 s on the 3050 (most of the loader rows); the hog runs gain more | M | stall1 ruled out a plain `HL_PREFAULT` of the guest heap; this is the zone's own regions, and the loader's pattern (sequential decompress into new buffers) prefetches well. Risk: touching 1-2 GB on a PC low on RAM turns into trim; do it only above a free-RAM floor |
| 2 | **Take the renderer's first touches off `Presentation_Thread`**: touch a pool's pages in the import/mirror-creation path on the replay worker before the first mirror sync, size the capture ring ahead of a load (the pages a load will write, from the last visit), and stop `HL_MEM_COLD` taking pool pages out in the 10 s before a warp | renderer's faults (26 % both) | up to 4 s per tour main, 14 s on the 3050 | M | the fault lines show the presenting thread taking 5-18k "guest: GPU pool" pages in a second; it holds the hand-off the game's main thread waits on |
| 3 | Name the idle stalls: add a stack walk (`RtlCaptureStackBackTrace` / `StackWalk64` on the suspended thread) to the stall watch for the presenting and main threads, and a job-trace mark around every blocking call on the present path (`replay_mu`, the queue submit, the swapchain present, `logf`'s file write); one 4-minute tour with `HL_STALL_WATCH=100` and `HL_STALL_WATCH_MAX=400`, no other instruments | idle (24-31 %) | unknown, up to 5 s main / 13 s 3050 | S to name it, then S-M | the largest cause no log here can explain. Do before rank 4 |
| 4 | Do not let the guest spin: the five game workers burn 900 Mcycles each at `sleep_away` for 350-400 ms while loaders need the cores (the 3050 PC's cores are shared by the loaders, the replay workers and these spinners) | game waits in SleepThread (4 % 3050) | 1-3 s per tour on the 3050, from the cores freed for the loaders and the fault handling | S (yield / `SwitchToThread` after N pauses, or `Sleep(0)` in `sleep_away`) | cheap, safe to A/B |
| 5 | Lift or natively replace the scene-setup hot guest functions (`BaseProcCreateAndDeleteThread` `f_81a77fe0`, `f_814efd20`) | game scene setup (4-6 %) | 1-3 s per tour | L | small share; the lifter work already in flight may cover it |
| 6 | Trim and RAM pressure: do not run the trim in the 10 s after a warp, and raise the working-set floor for the first 15 s of a zone | faults under pressure (the `h*` runs) | 20 s a tour of the 3050's hog runs | S | only matters on a low-RAM PC |

Order to do them: 0 and 3 first (both are measurements and cheap), then 1 and 2 together (one prefault helper, two callers), then 4.

## 6. What is not known

- The 600-present stall and the 30 s ticks are attributed to the instruments from timing and from 12 clean tours, not from a bisect (the clean tours are older builds).
- The idle class (rank 3) has no stack. The two dumps that survived (the slot keeps only the latest 400, written during the first 50 s of the last run, f2-TR)
  show the main thread blocked on the presenting thread's event, the presenting thread idle, and nothing else running.
- The stall watch samples a thread's place once, 10 ms into the gap. A thread at `ZwWaitForAlertByThreadId` there may have been
  running later in the gap; CPU per thread (Mcycles) is the whole gap. Threads under 0.5 Mcycles are not listed, so a loader blocked in a
  read with no CPU is invisible: part of "idle" may be disk reads (5.3 s of the 19.8 s main idle time have a thread at `ZwReadFile`/`ZwCreateFile` at the mark).
- The `hl fault` lines are per second and only above 2000 pages; the faulting thread of a short stall is the one of the second that
  covers it.
- No per-frame zone marker exists in the log (the `map:` line comes 3-6 s after the warp is sent); the zone window is the scheduled warp time +15 s + 40 k.

Scripts and per-stall tables (not in the repo): `E:\OOT\scratch-zone2\full2.py`, `runall2.py`, `agg.py`, `*.detail.txt`.
