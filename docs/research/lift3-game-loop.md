<!-- Copyright (C) 2026 Sacrappy -->
# LIFT3: the speed of the translated code in the Market's game loop (24 Nov 2026)

Branch `perf/lift3` (worktree `E:\OOT\HeyListen-wt\lift3`, from main c79bee6f6), scratch `E:\OOT\scratch-lift3`.
Why: in the Market (market-spin) the frame is set by the game's own loop, the translated code, on both PCs; LIFT2's
native floating point gave +6.6% (3050) and +10-12% (5070) there. Target: the largest further cut of the game loop's
time without changing what the game computes.

## Summary (final, 24 Nov 22:00)

- **What sets the Market frame on main c79bee6f6 (ini D):** the Presentation Thread's replay, on the PC 3050 and on the main PC
  (3050 critpath: PT 18.08 of 19.45 ms a frame on the path; game threads about 1 ms). The translated code reaches fps only
  through CPU contention with the PT and through the perf report's "game" part (4.1-4.6 ms of ~19.5).
- **Measured on the PC 3050** (market-spin, ini D + send_performance_stats=1, 3 interleaved passes, fps from play + 10 s):
  - L1 `A64_NATIVE_FP_COLD=1` (lift option, this branch, off by default): **+1.5%** (matrix91: 51.56 -> 52.36 fps, 3/3).
  - L2 hot list + 400 Market functions with a fresh PGO profile (build data): **+1.25%** (matrix93: 52.06 -> 52.71, 3/3).
  - L1 + L2 together: **+3.2%** (matrix93: 52.06 -> 53.71, 3/3; game part 4.46 -> 4.23 ms, render 15.99 -> 15.23 ms).
  - L3 `HOS_SHORT_SLEEP_TIMER=1`: no gain (matrix91: 51.37 against 51.56). Closed.
- Left: ship L1 on by default after a picture / physics check; re-record L2's profile with castle-move too (its dump came after
  the run's end) and decide whether the hot list and profile in `profile/` are replaced; L4 (the PT's virtual-core wait behind
  the executors, 0.38 ms a frame on the path) not built (PRESENT1 tried the presenter's priority before, no gain); locals in
  the hot functions (ReLink's LOCAL_REGS_HOT) need the FP blocks to see through local registers first.

## State

- 24 Nov 22:00: done for this session. No lease held, no background command, the shared work folder lifted back to main's
  text (`lift3restore`). Builds in `build/s5/bin` (lift3base, lift3cold, m1, m1c) and on the 3050 `C:/OOT/builds/lift3*`.
  L2's data: `E:\OOT\scratch-lift3\hot_funcs_m1.txt`, `E:\OOT\scratch-lift3\pgo\m1.prof` (not committed: a profile
  re-recorded with castle-move should replace it before it ships).

## 1. Where the Market's game-thread time goes (main PC, sampled, shares)

Runs: `prof_run.sh` (slot lease, market-spin from market-mid, `HOS_SAMPLE_ALL` 30 s from play + 6 s, `HOS_JOBTRACE` 80-86 s),
read with `E:\OOT\scratch-lift3\ana.py` (per thread group, by leaf kind) and `tools/bench/critpath.py`. lift3-b1 (lift3base):
a DECOUPLE build (14 compilers) ran beside it, 18.2 ms frames in the window; lift3-c1 (lift3cold): my own base lift and
build ran beside it, 22.7 ms. Neither is a speed measure.

ms a frame of thread time, lift3-b1 (`b1.ana.txt`):

| threads | wait | guest, hot list | guest, cold | spin in short sleeps | host code | system / driver | FP helpers | translation runtime |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| main thread | 13.48 | 1.79 | 0.68 | 0.42 | 0.63 | 0.89 | 0.06 | 0.15 |
| executors (6) | 80.89 | 16.26 | 6.43 | - | 2.85 | 0.59 | 1.53 | 0.79 |
| module workers (5) | 71.15 | 8.45 | 2.58 | 2.20 | 2.90 | 2.95 | 0.24 | 0.51 |

- **The critical path on the main PC is the Presentation Thread (the replay)**: critpath over lift3-b1's trace, 371 frames,
  16.11 ms a frame: PT 14.67 ms, main thread 0.39, module workers 0.60, executors under 0.05 each. lift3-c1 the same
  (PT 18.5 of 22.2 ms). The main thread waits 74% of its time. On this machine and under this load the game loop is not
  what sets the frame; the PC 3050's runs decide.
- **Cold code is 28.6% of the game threads' guest-leaf samples** in the Market (lift3-b1, innermost lifted function of each
  sample whose leaf is lifted code or an FP helper): the hot list (849 functions, castle / Kokiri / Hyrule, 8 Nov) holds
  71.4%. 1,305 cold functions; the 200 largest of them hold 14.5 points, the 400 largest 19.0. Cold functions are built at
  -O1 without a profile, and until A64_NATIVE_FP_COLD their floating point went through the exact outlined helpers.
- **The visibility job's waits spin.** Every sample in the "spin" column is `nn::os::SleepThread` called by `f_800998a0`
  (the culling / render-list job, run by the 5 module workers and the main thread) while it waits for another thread's flag:
  the host makes a guest sleep under 1 ms a PAUSE loop to the deadline (HOS_SHORT_SLEEP_PAUSE, on by default). 2.6 ms a
  frame of CPU in lift3-b1, 8.5 in lift3-c1 (the busier machine). On the 3050's 6 cores this competes with the frame's
  own work; matrix91's arm T (HOS_SHORT_SLEEP_TIMER=1, the sleeps on the timer) measures it.
- The flat profile of earlier notes holds: the largest function is 5.4% of the game threads' guest time
  (`f_80084de0`, the render recording job), the top 50 under 45%.

## 1b. The PC 3050 (decision machine): baseline and profile

matrix90 (`C:\OOT\pc3050s-out\matrix90.txt`, parts in `matrix90-parts.txt`), lift3base, market-spin, ini D +
send_performance_stats=1, fps from play + 10 s, parts_ms of the Market_Child map in the run's last perf JSON:

| run | fps | game | render | gpu_wait |
|---|---:|---:|---:|---:|
| B1 | 51.48 | 4.232 | 15.797 | 1.045 |
| B2 | 52.20 | 4.139 | 15.975 | 0.901 |
| B3 | 52.55 | 4.292 | 15.330 | 0.896 |
| P1 (sampled) | 50.13 | 4.345 | 15.837 | 1.158 |

P1's samples (last 25 s, `p3050.ana.txt`) and job trace (critpath, 308 frames, 19.45 ms a frame):
- **The critical path is the Presentation Thread**: PT 18.08 ms of 19.45 on the path, main thread 0.46, module workers 0.42,
  the PT waiting for a virtual core behind EX0 0.38. The PT is busy 18.3 of 19.55 ms (renderer dll 6.89, driver and system
  10.23); the main thread waits 72%. The same as the main PC. The brief's premise (the game loop sets the Market frame) does
  not hold on main c79bee6f6 at ini D: the translated code reaches the frame through its CPU (cores and SMT siblings the PT
  shares, virtual cores) and through the 4.2 ms "game" part.
- Game threads' CPU, ms a frame: executors 39.8 (hot guest 22.4, cold guest 8.7, FP helpers 2.7, host 4.2), module workers
  22.8 (hot 8.6, cold 2.7, spin 4.7, host 3.3, driver 2.5), main 5.5 (spin 0.9). Cold functions 25.4% of the guest time.

## 2. Levers, ranked (expected size from section 1; the 3050's numbers decide)

| # | Lever | Switch | Expected | State |
|---|---|---|---|---|
| L1 | Native FP in the cold functions | `A64_NATIVE_FP_COLD=1` (lift) | part of the 28.6% cold time that is FP | built (`lift3cold`), 3050 A/B in matrix91 |
| L2 | Market functions in the hot list + a fresh PGO profile with the Market in its training | the hot list and profile files (build) | up to the 19 points of cold time moved to -O2 + profile + native FP | `pgo_cycle.sh m1` running |
| L3 | The visibility job's short sleeps | `HOS_SHORT_SLEEP_TIMER=1` (run time, exists) | 2.6-8.5 ms a frame of CPU back to the other threads | matrix91 arm T |

## 4. Measured on the PC 3050: matrix91 (L1, L3)

`C:\OOT\pc3050s-out\matrix91.txt`: B = lift3base, C = lift3cold, T = lift3base + HOS_SHORT_SLEEP_TIMER=1; ini D +
send_performance_stats=1, market-spin, 3 interleaved passes after a warm-up; fps from play + 10 s; parts_ms of Market_Child.

| pass | B fps | C fps | T fps | B game / render | C game / render | T game / render |
|---|---:|---:|---:|---|---|---|
| 1 | 51.59 | 52.15 | 51.18 | 4.209 / 15.92 | 4.188 / 16.436 | 4.832 / 15.668 |
| 2 | 51.82 | 52.68 | 51.57 | 4.575 / 16.082 | 4.422 / 15.593 | 4.64 / 15.741 |
| 3 | 51.27 | 52.24 | 51.35 | 4.348 / 15.701 | 4.139 / 15.972 | 4.488 / 15.748 |
| mean | 51.56 | 52.36 | 51.37 | 4.377 / 15.90 | 4.250 / 16.00 | 4.653 / 15.72 |

- **L1 (A64_NATIVE_FP_COLD): +1.5% (51.56 -> 52.36 fps), C above B in all 3 passes**, the game part 4.38 -> 4.25 ms. Small, as
  section 1b predicts for a PT-bound frame, but consistent. Proposed: on by default (the same helpers and proof as the hot
  functions' native FP, which ships), after a picture / physics check; kept off in this branch until the coordinator decides.
- **L3 (HOS_SHORT_SLEEP_TIMER=1): no gain** (51.37 against 51.56; the game part up to 4.65 ms: the visibility job's waits
  wake late on the timer). Closed: the spin's CPU does not reach the PT's frame here.

## 3. L1: A64_NATIVE_FP_COLD

`nx2/nativefp.py` `cold_text`: in every function that is not in the hot list and not one the text edits and the gates read
(`fastvec.PLAIN0`), the outlined exact helpers `a64_fpx_<shape>` become `a64_fpx_nat_<shape>` (inline: the host's instruction,
the exact helper for a NaN), the 2/4-lane add / sub / mul `a64_vfpx_nat_*`, the integer conversions `a64_nat_*`: the same
helpers the hot functions use since LIFT2, so the same proof (`tests/test_native_fp.py`, which now also checks the cold
rewrite's names). Lift (`mk-lift3cold.log`): `cold 293575, cold_scalar 263226, cold_vector 134622, cold_conv 23580`. The exe is
462 MB against 479 MB. Function check: lift3-c1 played the Market to its end (main PC, play at 65 s).

## 5. Measured on the PC 3050: matrix93 (L2, L1 + L2)

`C:\OOT\pc3050s-out\matrix93.txt`: B = lift3base, M = lift3m1 (L2), X = lift3m1c (L1 + L2), same setup as matrix91. The first
try of M's warm-up run failed (not reported by the pilot why; the retry ran).

| pass | B fps | M fps | X fps | B game / render | M game / render | X game / render |
|---|---:|---:|---:|---|---|---|
| 1 | 52.20 | 52.53 | 54.04 | 4.482 / 15.923 | 4.524 / 15.602 | 3.947 / 15.257 |
| 2 | 51.75 | 52.87 | 53.50 | 4.436 / 16.111 | 4.056 / 15.519 | 4.24 / 15.33 |
| 3 | 52.22 | 52.73 | 53.60 | 4.473 / 15.925 | 4.496 / 16.062 | 4.499 / 15.114 |
| mean | 52.06 | 52.71 | 53.71 | 4.464 / 15.99 | 4.359 / 15.73 | 4.229 / 15.23 |

L2's cycle (`E:\OOT\scratch-lift3\pgo_cycle.sh m1`): lift with the hot list (1,249 functions), instrumented build, training in
slots (counters reset at play + 5 s, dumped at play + 35 s): market-spin, kokiri-idle, hyrule-walk (castle-move's dump came
after the run's end: play began at 74.5 s), merged 6 : 1 with the shipped profile (3 functions' counters differ from it:
f_804f5030, f_804e48c0 and one more), final build with that profile. With the larger list the hot functions hold 87.5% of the
game threads' guest time on the main PC (lift3-m1c) against 74% before.
