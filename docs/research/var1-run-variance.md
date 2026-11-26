# VAR1: why the same build gives different fps from run to run on the main PC

## State
- 2026-11-24 21:10: done. Variable = other work on the machine (CPU contention): quiet 111-117 fps (9 runs, 3-4%), loaded 55-57 (flip: 12 busy processes, a second game, or 22 compilers). See Variable and Recipe.

## Old runs (build/s5/tc-texcache1-*), scene frames (>= 50 draws), per zone
Source: build/s5/tc-texcache1-<run>/game_log.txt, split with E:\OOT\scratch-var1\seg.py. Columns: fps, draws a frame, GPU ms a frame (the "vk: GPU time" line), replay submit ms.

| zone | off2 | warm1 | warm2 | cold |
|---|---|---|---|---|
| Kakariko | 50.1 fps, 2358 draws, GPU 13.97 | 49.2, 2592, 15.34 | 84.0, 2483, 6.76 | 28.8, 2049, 19.81 |
| Hyrule Field | 61.4, GPU 12.24 | 54.7, GPU 20.11 | 39.9 (12 s), GPU 4.37 | 35.9, GPU 23.26 |
| Death Mountain Trail | 73.2, GPU 9.63 | 75.6, 9.32 | 105.1, 5.45 | 36.7, 22.74 |
| Goron City | 79.5, 7.23 | 55.5, 21.26 | 78.1, 9.15 | 76.2, 9.61 |

Same draws, GPU time per frame varies 2-4x: the variation is on the GPU side (clock, contention), not in the scene.
objlog.csv (E:\OOT\scratch-mem\objlog.csv, 5 min samples): during 17:14-17:35 avail_mb swung 513..10649, 8-10 clang running, 1 game besides.

## Simple case, quiet machine (speed lease 19:56-20:08, slot b, build main14, save kakariko-village, scene kokiri-idle, 6 runs)
Script E:\OOT\scratch-var1\run6b.sh; runs build/s5/v1k1..v1k6 (game_log.txt, bench.json); logs of nvidia-smi / CPU in E:\OOT\scratch-var1\v1k*.smi, .cpu.csv.
bench.json fps: 112.7, 114.8, 117.1, 114.5, 116.3, 115.6 (spread 4%, run 1 the slowest).
Scene frames from the log (seg.py): 111.6, 114.5, 116.5, 114.1, 115.4, 114.9 fps; draws 2427-2508; GPU ms a frame 6.80-6.95; replay submit 6.1-6.2 ms.
Result: with nothing else running there is NO two-state behaviour in one zone: 4% spread, GPU ms identical to the 4th digit.
nvidia-smi: run 1 clocks mean 2175 MHz / 84 W (28 samples), runs 3 and 6 2625 MHz / 102 W (GPU clock ramp-up in run 1).
The old tour's good Kakariko run (warm2: 84 fps, GPU 6.76 ms, 2483 draws) matches the quiet GPU time (6.8 ms); the slow ones (GPU 14-20 ms for the same 2400 draws) are the loaded ones.

## Tour on a quiet machine (speed lease 20:22-20:35, slot b, main14, save kokiri-forest, warps 1003 1001 1002 1009 1012, 35 s apart, 230 s)
Script E:\OOT\scratch-var1\tour.sh; runs build/s5/v1t1..v1t3 (game_log.txt, bench.json, <tag>.livelog). Warm shader cache all three (9478-9484 graphics pipelines at start).
bench.json fps: 128.7, 125.0, 127.5 (spread 3%).
Scene fps per zone (v1t1 / v1t2 / v1t3), seg.py: Market 94.6/99.1/99.8, Hyrule Field 126.9/125.6/124.5, Kakariko 99.6/91.5/93.8, Death Mountain Trail 136.7/137.6/140.5, Zora's River 108.0/108.2/111.9.
GPU ms a frame in every zone: 5.3-7.7, all three runs. The old tour's range for the same zones was 4.4-23.3 ms.
Result: the spread does not come back on a quiet machine, tour or not. Kakariko is 91-100 (9%), the worst zone; the old tour had 29-84.

## The flip (speed lease 20:54-21:07, slot b + slot c for the second game, main14, kakariko-village, kokiri-idle, ~110 s each)
Script E:\OOT\scratch-var1\flip2.sh (burn.py = N busy processes for 100 s from play: began); runs build/s5/f-q1, f-cpu12, f-game2, f-q2; <tag>.loadlog, .smi.
| arm | bench.json fps | scene fps (seg.py) | draws | GPU ms | gaps between recordings ms | replay submit ms |
|---|---|---|---|---|---|---|
| f-q1 quiet | 111.8 | 110.8 | 2461 | 6.76 | 2.34 | 6.27 |
| f-cpu12 (12 busy processes on the 16 threads) | 56.6 | 56.3 | 2492 | 6.81 | 11.46 | 8.14 |
| f-game2 (a second game in slot c, same scene; it ran 46.3 fps) | 55.5 | 56.5 | 2460 | 7.55 | 9.82 | 9.04 |
| f-q2 (meant quiet; someone's build started during it: objlog 21:06:16 = 22 clang, 25 python) | 55.0 | 53.5 | 2379 | 6.61 | 14.44 | 8.74 |
Same build, same save, same scene: 111 fps without competing work, 55-57 with any of three kinds of it. f-q2 is an unplanned third flip: it had the same command as f-q1 and ran at half speed because 22 compilers started in the middle (runguard checks the machine only at the start).
GPU ms stays 6.6-7.6 in all arms: the GPU is not the loser here. What grows is the wait between recordings (2.3 -> 10-14 ms) and the replay's submit time: the game's CPU threads are starved. (The old tours' GPU 14-23 ms in the slow runs is a different symptom, probably the GPU shared with the other agents' games; not separated.)

## Variable
Other work on the machine (compilers, a second game, anything that keeps the 16 threads busy) during the run. Quiet: 3-4% spread over 6 + 3 runs. Loaded: 2x. The old tour's 29..84 fps in Kakariko is this, not the cache (warm1/off2/cold/warm2 had 8-10 clang in objlog, only 5 min samples so the exact load per zone is not known).

## Recipe for comparable fps runs on the main PC
1. A speed lease for the whole block, and check clean at the start AND the end of EACH run, not only at the start: `bash build/s5/machine.sh check <ticket> --clean` and a count of clang/python/HeyListen processes right after the run; discard a run if any appears. Other agents' builds do start during a speed lease (f-q2).
2. Read the "gaps between recordings" and replay submit lines: gap above ~4 ms with the same draws and GPU ms means the CPU was contended; a run with it is not comparable.
3. Warm shader cache (precompile line "graphics pipelines from N notes" with N in the thousands); discard the first run after a build switch (run 1 of v1k was 3% slow, GPU clock 2175 against 2625 MHz).
4. fps on scene frames (>= 50 draws) per zone, never the whole-run average; same save, same scene, same resolution line.
5. 3 runs per arm are enough when quiet (spread 3-4%); judge a difference only above ~6%.
6. Keep blocks short; do not run two games or a build beside a measurement, also not your own.

## Players
A player who runs a browser, a launcher or a video beside the game is exposed to the same halving; the game cannot stop that. What it can do: the background shader workers (~95% of a core each, see the cold-cache note) run during the first start; lowering their priority below the render/replay threads would keep a cold start from starving the replay thread. Not tested here.

## Not verified
Whether the starved thread is the replay (render) thread or the game thread (HOS_THREAD_TIMES not used); whether the main PC's GPU contention explains the old GPU 14-23 ms; typeperf CPU files were not written (no .cpu.csv); the exact load of the old runs; the second of two allowed blocks was not needed.
