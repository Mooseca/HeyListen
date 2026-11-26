<!-- Copyright (C) 2026 Sacrappy -->
# GPU cost on the PC 3050, lists A to F (GPU1, 2026-11-22)

Companion of `gpu1.md` (the tools and the switches) and `gpu-pass-cost.md` (STEP0). PC 3050 (i5-10400F, RTX 3050, driver 621.24), Market
`market-spin` from `market-mid`, 1440p 100% render, `dlss=0 upscaling=0 hdr=0 vsync=0`, no frame cap, game killed at 2 minutes, runs by the
3050's own session, rounds interleaved. fps = median of the Market-window perf lines; GPU = median of the "GPU time ... ms a frame" lines in the
Market window; tail = median "GPU tail before the late waits". Builds: `gpu1base` (= `refactor/integ2` as it was: ring and native draw loop
on) for A and B, `gpu1b` for C, `gpu1c` for D, `gpu1d` for E and F. Logs: `E:\OOT\scratch-gpu1\3050\{A..F}` (local, not in the repository). The series
drifted by up to 1 fps between lists (list E ran about 0.8 fps lower than A-D): compare inside a list.
No device lost and no Vulkan validation message in any run.

## List A: existing switches (2 rounds)

| Arm | env | fps | GPU ms | tail ms |
|---|---|---:|---:|---:|
| A0 | none | 49.9 | 16.28 | 14.82 |
| A1 | `RX_VK_RB_RANGES=1` | 50.5 | 16.25 | 14.78 |
| A2 | `RX_VK_TEST_BARRIER_DROP=4` (dispatch barriers) | 50.6 | 16.00 | 14.90 |
| A3 | `RX_VK_TEST_BARRIER_DROP=1` (all three classes) | 54.2 | 14.35 | 12.83 |
| A4 | `RX_VK_BARRIER_TRUST=1` | 50.2 | 16.05 | 14.96 |
| A5 | `RX_VK_GAME_BARRIER_NARROW=1` | 49.6 | 16.20 | 14.99 |

A1 left no log line proving it applied (the switch logs nothing). A4 is the default: `hos_main.c` sets `RX_VK_BARRIER_TRUST=1` before main, so A4 = A0.
A5's line was present: narrowing the destination stage drains the same.

## List B: barrier classes (2 rounds; `RX_VK_TEST_BARRIER_DROP` masks, bounds only, the picture may be wrong)

| Arm | mask | fps | GPU ms | tail ms |
|---|---|---:|---:|---:|
| B0 | none | 50.3 | 16.15 | 15.00 |
| B1 | 2 pass starts | 50.1 | 16.20 | 15.02 |
| B2 | 8 the game's | 50.7 | 15.90 | 14.42 |
| B3 | 10 pass starts + the game's | 53.0 | 14.80 | 13.77 |
| B4 | 1 (14: all three) | 54.1 | 14.25 | 12.87 |

No class alone is worth more than 0.3 ms; two together 1.4 ms; all three 1.9 ms (+7% fps). The same drain sits at the same place twice and each
hides the other, so the cost is only recovered when both go.

## List C: hazard barrier first version (`gpu1b`, 3 rounds) and the first sequence log

| Arm | env | fps | GPU ms |
|---|---|---:|---:|
| C0 | none | 50.0 | 16.22 |
| C1 | `RX_VK_HAZARD_BARRIER=2` (counts only) | 49.9 | 16.17 |
| C2 | `RX_VK_HAZARD_BARRIER=1` | 49.9 | 16.18 |

C2's counters (a frame): 159 game barriers (0x1 4.8, 0x8 3, 0x9 1, 0x10 2.8, 0x11 45, 0x12 88.6, 0x13 2, 0x21 4, 0x28 16, 0x92 3, 0x97 1);
could be owed 48.1; recorded after all by another op 43.6; by a sampled target 2.6; replaced by a later full barrier 1.9; kept at once 107.6, of
which 28 because their bits are not in 0x17. Full barriers recorded a frame: C0 283.9 (107.1 left out), C2 289.9 (101.5 left out).
Luma of the frame logs: C0 mean 105.81 (1,218 frames, 1 pulse), C2 105.74 (1,410 frames, 3 pulses; the camera spin differs from run to run).

## List D: owed barrier lets a dispatch go ahead (`gpu1c`, 3 rounds) and the second sequence log

| Arm | fps | GPU ms | tail ms |
|---|---:|---:|---:|
| D0 | 49.8 | 16.14 | 14.98 |
| D1 `RX_VK_HAZARD_BARRIER=1` | 50.3 | 16.05 | 14.84 |

D1: could be owed 47.5, recorded after all by another op 42.2, a sampled target 3.1, replaced 2.2; dispatches ahead of an owed barrier 0.3 a frame.
The ops that forced a recording, per frame: op7 `NOP_UPDATE_UB` 21, op42 `NOP_RENDER_COND` 13, op4 `NOP_SIGNAL_EVENT` 2, op37 `NOP_RESET_COUNTER` 1,
op38 `NOP_CLEAR_TEX` 1, op48 `NOP_WAIT_EVENT` 1. Shots (31 each) and frame logs of D0 and D1, looked at by the 3050 session: no white, banding,
missing object or flash.

## List E: UPDATE_UB, RENDER_COND and RESET_COUNTER leave the barrier owed (`gpu1d`, 2-3 rounds)

| Arm | fps | GPU ms | tail ms |
|---|---:|---:|---:|
| E0 | 49.3 | 16.27 | 14.78 |
| E1 `RX_VK_HAZARD_BARRIER=1` | 48.9 | 16.35 | 14.81 |

E1: could be owed 40.7; recorded after all by another op 26.8 (op5 `NOP_REPORT_COUNTER` 20, op4 2, op38 2, op48 1); a sampled target 12.6;
replaced 1.3; dispatches ahead 0.3. No gain.

## List F: write-back bounds (`gpu1d`, 3 rounds; both switches bring issue 50's cut grass back: bounds only)

| Arm | env | fps | GPU ms | tail ms | MB copied a submit |
|---|---|---:|---:|---:|---:|
| F0 | none | 48.0-49.7 | 16.2 | 14.7 | 7.4 |
| F1 | `RX_VK_WB_POOL_EAGER=0` | 48.6-50.0 | 15.95 | 14.5 | 3.5 |
| F2 | + `RX_VK_WB_SMALL_EAGER_KB=0` | 49.4-50.9 | 15.8 | 14.4 | 2.0 |

(fps ranges: the coordinator's means and the median-of-Market-lines of this analysis; both put F2 about +2.4-2.9% over F0.) The written-back MB a
submit by category, F0: outside the game's pools 0.48, pools the CPU reads 1.58, pools the CPU writes 5.17, uncached 0.28; F1: writes 0.00, uncached 1.43.
Serialized (`RX_VK_PASS_TIMING=1`, F1): `wb` 0.87 -> 0.59 ms, 53 -> 25 MB a frame.

## The Market-time serialized report, ring on (`RX_VK_PASS_TIMING=1`, last 600-present report of the seq runs, 3050)

| Kind | ms | Spans | Items |
|---|---:|---:|---:|
| pass | 10.63 | 146 | 1,852 draws |
| dispatch | 3.84 | 114 | |
| wb | 0.87 | 8.8 | 131 runs, 53 MB |
| barrier (recordings') | 0.55 | 210 | |
| rbrefresh | 0.19 | 40 | 0.8 MB (1.02 ms before the ring) |
| msync | 0.19 | 25 | 0.78 MB |
| u barrier | 0.18 | 104 | |
| xfer | 0.18 | 6.8 | |
| meshconv | 0.12 | 24 | |
| ubupd + event + clear | 0.06 | | |
| all | 16.9 | | against 16.2 ms unprofiled |

## What the sequence logs show, and do not

`RX_VK_PASS_SEQ=<first>,<count>` (with `RX_VK_PASS_TIMING=1`) logs each profiled span with its start, length and label; `tools/gpu1_seq.py` reads it.
The windows could not be laid on a Market frame: in the first run (C, `24000,28`) and the second (D, `2000,40`, only recordings of 40 spans or more) the
profiled command buffers held mostly the game's network dispatches (`mma` programs of 0.1-2.1 ms, 14 a recording) and 3 passes a recording; the passes of
the native draw loop's segments are not in the two command buffers the profile times. What they gave: of the game's barriers in the window, 52 of 56
(C) and 520 of 560 (D) sit between two dispatches and 4 and 40 between two passes; none of the 56 and 560 dispatches sampled or stored a texture a pass
wrote in the 12 spans before. No per-pass dependency timeline of a Market frame exists; the sound proof of overlap would need the segments' command buffers
timed too.

## Why `RX_VK_HAZARD_BARRIER` cannot elide much (the forcing ops)

A game barrier is owed only if since the trust point only draws and pass edges were recorded (48 of 159 a frame). It is then recorded at the
first op after it that is not a draw's state: in list D that op is `UPDATE_UB` (21 a frame) or `RENDER_COND` (13), in list E `REPORT_COUNTER` (20),
and the sampled-target check takes 3 to 13 more. What is left is 1-2 barriers a frame replaced by a later full one. Even eliding every game barrier is
bounded by B2 (0.3 ms). The pass-start barriers, whose removal together with the game's gives the 1.4 ms, are already trusted (121 left out a frame, 21
attachments-only), so what remains of them is after non-draw work. Switch left off, documented in `docs/SWITCHES.md`.

## Switches added by GPU1 (all off by default)

| Switch | What |
|---|---|
| `RX_VK_PASS_SEQ=<first>,<count>` | the profiled spans of count recordings in order, with barrier flags and texture use (diagnostic; needs `RX_VK_PASS_TIMING=1`) |
| `RX_VK_HAZARD_BARRIER=0/1/2` | the game's barriers owed (1), or only counted (2) |

## Read this way

On the 3050 at 1440p the GPU is busy with the game's own work (passes 10.6 ms, dispatches 3.8 ms of 16.2); emulation is about 1.8 ms and what is
measurable of it is bounded by 0.4 ms (write-backs) and 0.2-0.3 ms (the game's barriers alone). The 1.4-1.9 ms of barrier drains is real but needs the
pass-start and the game's barriers to go together, which no hazard the engine can see allows. Not verified: the RTX 5070 against any GPU1 build
(no gpu1 exe could be placed in a slot), 1080p, and any per-pass timeline of a Market frame.
