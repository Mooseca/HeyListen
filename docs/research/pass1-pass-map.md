# PASS1: pass map and the 3050 switches (23 Nov 2026) - STATE: code written, not built, no measurements yet

**The machine queue blocked it.** At 12:00 the main PC's queue held five speed leases (45 min each, priority 2) ahead of a build
lease at priority 5, so the build was not granted in the first hour and would not have been for about four more; the ticket was
released. Nothing below was compiled or run. What exists is source (commit on `perf/pass1`), a test of the wiring and of the VRS
selection rule, the diagnostic that produces the pass map, and the 3050 script.

## What the pass map will be made from (one run, no code beyond this branch)

`RX_VK_PASS_TIMING=2 RX_VK_PASS_TIMING_TOP=80` (new: the number of spans and programs the report lists, default 25 and 20) prints every 600
presents, per pass: `pass WxH fFMT Nc[+d], draws bucket, N sampled, first prog, last prog, dw<0|some|all> disc<0|Y> a2c<0|Y> latez<0|some|all>
blend<...> cl<mask> vrs<0|1>` with its GPU ms, and per dispatch `dispatch prog <key> grid XxYxZ`. New in the label: `dw` draws that write
depth, `disc` rasterizer discard, `a2c` alpha to coverage, `latez` draws whose fragment program writes depth or kills (early Z lost,
from `Shader::Info::stores_frag_depth` / `uses_demote_to_helper_invocation`), `blend`, `cl` the attachments cleared by loadOp
(RX_VK_LOAD_CLEAR). Run it at `resolution=1` (100%) and `resolution=4` (50%) in the slot's hookshot_options.ini, scenes Kokiri village
(`savelib/kokiri-village`), Hyrule field and Market (`market-mid`), on the 5070 and the 3050. Intermediate-image captures go to
E:\OOT\scratch-pass1 with the existing `RX_VK_SHOTS` / `RX_VK_DUMP*` switches.

Load/store ops today: every pass is `loadOp LOAD, storeOp STORE` on every attachment (`begin_pass`, vk_draw.cpp); no pass discards
(`DONT_CARE`) anything, and clears are `vkCmdClearAttachments` inside the pass.

## Known 3050 numbers (from `docs/native-engine/gpu-pass-cost.md`, `shader-efficiency.md`, the task brief)

Top programs, 3050, 1440p 100%: `1a7482c0` ~1.0 ms full screen in every scene (the best VRS candidate if it is fog or light: check its
`dw`/`latez` in the map before using it), Kokiri `918adef1` 1.7, `43ec86f3` 1.3, `d8e59341` 1.1 (1.41 in Market), Hyrule `739acd67` 1.4,
`d905f52b` 0.9; `d8180bd8` full-screen 2560x1440 with 6 sampled textures 0.49 ms Kokiri. The top-10 table by 3050 cost, with each pass's
formats, sizes, ops, 50% scale cost and early-Z status, is to be filled from the run above.

## The switches (all off by default; `tests/test_pass1_switches.py` checks the wiring and compiles the VRS rule)

| Switch | What | Why it is safe off |
|---|---|---|
| `RX_VK_VRS=<prog hex prefix or WxH or all>,...` (`RX_VK_VRS_MIN_W`, default 64) | pipeline shading rate 2x2 (VK_KHR_fragment_shading_rate, dynamic, combiners KEEP) for draws of the named fragment programs, or colour-only passes of that size; never multisampled, never a depth-writing draw | the extension is not enabled and the pipelines have no new dynamic state unless the variable is set |
| `RX_VK_LOAD_CLEAR=1` | a full-target clear that opens a pass becomes the pass's loadOp CLEAR (colour with mask 0xF; depth when it covers every aspect), the clear call is skipped | only the first clear of a pass converts |
| `RX_VK_SHADOW_SHIFT=1..3` | the sun's shadow map (square depth-only 2D, 8192+ texels, 12288 D16, 288 MB) made 2^n smaller per side; viewport, scissor and clears shrink with it; no upload from guest storage | reached by `create` only with the variable set |

Not done: storeOp DONT_CARE (no frame lookahead exists at `begin_pass`: a depth buffer's next pass reloads it, so it cannot be proved
dead there; it needs the map plus a per-frame "last pass of this target" pass), grass density and volumetric fog resolution (both are
guest-side sizes chosen by the game's own code; the only replay-level handle is the same texture-size remap as the shadow map, to be
tried once the map names their targets), barrier cuts, merging the 1x1x1 dispatches.

## Risks to check in the first build

- `RX_VK_SHADOW_SHIFT`: a shader that reads the shadow map by texel (texelFetch) or a PCF kernel built from the guest's size changes the
  look; picture check against off in Kokiri and Hyrule (sun shadows, Link's shadow).
- `RX_VK_VRS` on a pass that is later read by texel (compute): 2x2 blocks show; pick only passes the map shows as smooth.
- The code has never been compiled: expect a first round of build errors (`vkCmdSetFragmentShadingRateKHR` added to `VKX_DEVICE3`).

The 3050 A/B: `build/s5/pass1/ab_pass1.sh <tag> <bin dir> [rounds] [scenes]` (arms `-`, load-clear, VRS list, shadow shift 1 and 2, all
three; fps from play + 10 s; `LEASE=none` when a lease is already held; `HL_REPO`, `HL_SLOTS`, `HL_SLOT`, `VRS_LIST` set the layout).

## State at stop (2026-11-23 reboot)

Updated since the header above: the branch BUILT on the first try (mkg, 89 s, `build/s5/bin/pass1`, build lease released). A slot lease on slot b
(ticket in `E:\OOT\scratch-pass1\slot.ticket`, released at the stop) ran `build/s5/pass1/map_run.sh`: RX_VK_PASS_TIMING=2 RX_VK_PASS_TIMING_TOP=80 at resolution 100% and 50%
in kokiri-village, hyrule-field, market-mid. Logs copied to `E:\OOT\scratch-pass1\map\<scene>-r1|r4.log` (r1 = 100%, r4 = 50%): kokiri-village r1/r4,
all six logs are there (market-mid r4 finished at the stop).

Done: switches coded and built, test passes, pass-map labels, scripts (`map_run.sh`, `ab_pass1.sh`; both fixed to call `build/s5run.sh`).
Not done: reading the 5 logs into the pass map (top 10 by 3050 cost, VRS-eligible passes = `dw0` and `latez0`), the picture checks of each switch
(RX_VK_LOAD_CLEAR=1, RX_VK_VRS=<list from the map>, RX_VK_SHADOW_SHIFT=1/2 against off, `RX_VK_SHOTS=<dir under E:\OOT\scratch-pass1> RX_VK_SHOT_EVERY=900`,
Kokiri and Hyrule), the 5070 numbers, the 3050 numbers (the 3050 gets `ab_pass1.sh`).
The 3050 data above in this file is from older logs, not from these.

Exact next commands after the reboot (the slot ini of slot b is restored by map_run.sh's trap; check `resolution=1` in `E:\OOT\slots\b\hookshot_options.ini`):
1. Nothing to rerun: all six logs exist. Go straight to step 2.
2. Parse: `grep "pass " E:/OOT/scratch-pass1/map/*.log`, lines of the 600-present report with ms, label `... dw<> disc<> a2c<> latez<> blend<> cl<> vrs<>`.
Leases used: build (released), slot b ticket 20261123-120848-pass1-slot-0acd (released at the stop). No background command left.

## Pass map, 5070 (23 Nov 2026, read from the six logs; the 3050 logs had not landed)

Source: the last 600-present report of each log, RX_VK_PASS_TIMING=2, 100% (r1) and 50% (r4); ms a frame; profiled frames run at
12.9 ms (Kokiri), 7.3 (Hyrule), 8.4 (Market) at 100% and 6.2 / 6.25 / 6.8 at 50%. The 5070 is not resolution-bound in Hyrule, so these
are shares, not 3050 times: the 3050 costs of the programs are in the section above. Scale = r4 cost / r1 cost of the same first prog
(a drop to about a quarter means pixel-bound).

Top 10 passes (1440p unless noted; Kok/Hyr/Mar = ms at 100%):

| # | first prog | pass | Kok | Hyr | Mar | 50% | dw / latez | VRS |
|---|---|---|---|---|---|---|---|---|
| 1 | d8e59341 | f122 1c+d, 0-4 draws, 4-5 sampled | 0.377 | 0.089 | 0.133 | 0.365 / 0.084 / 0.170 (flat) | dw0 latez0 | yes |
| 2 | 4f0c0b40 | f122 1c+d, 0-4 draws, 5 sampled | - | 0.298 | - | 0.294 (flat) | dw0 latez0 | yes |
| 3 | da7a7ab2 | 1280x720 f97 2c+d, 9 sampled | 0.248 | - | - | 0.113 | dw0 latezall blendall | no (latez) |
| 4 | 7fd6e4fd..522cf5a2 | f122 1c+d, 5-32 draws, 14-16 sampled | 0.107 | 0.219 | - | 0.019 / 0.089 | dwsome latezsome | no |
| 5 | 2cf34ce7..46c14f8e | f122 1c+d, 33-256 draws, 6 sampled | 0.216 | - | - | 0.036 | dw0 latez0 | many draws, geometry mixed: no |
| 6 | d8180bd8 | f37 1c, full screen, 6 sampled | 0.142 | - | 0.101 | 0.037 (pixel-bound) | dw0 latezall blendall | no (latez) |
| 7 | d905f52b | f122 1c+d, 0-4 draws, 5 sampled | 0.043 | 0.142 | - | 0.043 / 0.116 / 0.038 | dw0 latez0 | yes |
| 8 | 46c14f8e..700c26a1 | f122 1c+d, 33-256 draws, 8 sampled | 0.136 | - | - | 0.045-0.122 | dw0 latez0 | many draws: no |
| 9 | 1a7482c0 | f122 1c+d, 0-4 draws, 11 sampled | 0.119 | 0.103 | 0.084 | 0.032 / 0.029 / 0.030 (pixel-bound) | dw0 latez0 | yes (first choice) |
| 10 | 43ec86f3 | f122 1c+d, 0-4 draws, 6 sampled | 0.112 | - | - | 0.106 | dw0 latez0 | yes |

Top 10 dispatches (ms a frame at 100%, Kok / Hyr / Mar): `7984161d` grid 528x1x1 0.99 Kok; `cc627640` grid 2x1x1 0.33 Kok;
`9dc98871` 64x36 mma 0.24 / 0.11 / 0.09; `ee7764a6` 8x9x12 0.22 / (6x9x12) 0.18 / 0.13; `ab7699ee` 4x4x6 0.21 / 0.14 / 0.11;
`755a777a` 1x1x1 0.07 / 0.21 / 0.09; `435a0138` 1x1x1 0.15 / 0.11 / 0.08; `27ee9883` 16x9x12 0.13 / 0.09 / 0.09;
`26fe0c70` 80x60 0.13 / 0.06 / 0.05; `171c34b2` 80x23 0.08 / 0.04 / 0.04. Dispatches do not move with resolution (50% costs the same
for ee7764a6, ab7699ee, 755a777a, 435a0138, 27ee9883), so VRS and the shadow shift do not touch them. The 1x1x1 ones (755a777a,
435a0138, 09cc9a93) are launch/sync cost, a merge candidate.

Whole frame: passes 35.7%, dispatches 29.5%, barriers 16.1% (195 a frame), meshconv 7.0%, write-back copies 6.3% in Kokiri.

**VRS list** (dw0 and latez0, 0-4 draws = full-screen quad passes = low-frequency light/fog/post content, depth-write free):
`1a7482c0,d8e59341,43ec86f3,d905f52b,4f0c0b40`. Left out: `d8180bd8` and `da7a7ab2` (latezall: the fragment program kills or writes depth),
the multi-draw scene passes (`2cf34ce7`, `46c14f8e`, `7fd6e4fd`: geometry edges at 2x2 would show). The ab_pass1.sh default VRS_LIST is this list.


## Picture checks, main PC slot b, 1440p, RX_VK_SHOTS every 900 (23 Nov)

Pixel diffs are useless: the runs do not share a timeline (off against off2 differs as much as any switch), so the verdicts are by eye on the shots in `E:\OOT\scratch-pass1\pics`.
- LOAD_CLEAR=1: Kokiri and Hyrule look the same as off. OK to keep as a candidate.
- SHADOW_SHIFT 1 and 2: Kokiri and Hyrule sun shadows and Link's shadow look the same as off at this size; no fps run yet. Candidates.
- VRS (list 1a7482c0,d8e59341,43ec86f3,d905f52b,4f0c0b40): BAD. Kokiri shows visible 2x2 blocks on the rock wall detail (so at least one of the listed passes is not low-frequency, probably d8e59341, 43ec86f3 or d905f52b); Kokiri ran at 68.6 fps against 109 off (one run); Hyrule never reached play (black frames, 0 frames from play). Per-program bisect still to do. Safe first try: `1a7482c0` alone.

## Pass map, 3050 (RTX 3050, 1440p, from pc3050s-out/pass1map, last report of each log; ms a frame; profiled frame 18.0 / 20.2 / 21.0 ms Kok / Hyr / Mar at 100%, 12.6 / 14.7 / 15.0 at 50%)

Pixel-bound = the cost drops to about a quarter at 50%. Top passes at 100% (Kok / Hyr / Mar, then 50%):

| # | first prog | pass | 100% | 50% | pixel-bound | VRS |
|---|---|---|---|---|---|---|
| 1 | d8e59341 | f122 0-4 draws, 5 sampled | 1.458 / 0.317 / 0.377 | 1.311 / 0.28 / 0.351 | no (flat) | no: not pixel-bound |
| 2 | 1a7482c0 | f122 0-4 draws, 11 sampled, dw0 latez0 | 1.012 / 0.967 / 1.067 | 0.264 / 0.244 / 0.273 | yes (4x) | first choice |
| 3 | d905f52b | f122 0-4 draws, 5 sampled, dw0 latez0 | 0.111 / 0.808 | 0.101 / 0.626 | barely | second |
| 4 | 7fd6e4fd..522cf5a2 | 5-32 draws, 16 sampled, dwsome latezsome | Hyr 0.801 | - | | no |
| 5 | 2cf34ce7..46c14f8e | 33-256 draws, 6 sampled, dw0 latez0 | Kok 0.694 | 0.275 | yes | scene pass: edges, test last |
| 6 | 739acd67..64b82cf0 | 33-256 draws, 18 sampled, latezsome | Hyr 0.672 | - | | no |
| 7 | da7a7ab2 | f97 2c+d 9 sampled, latezall | Kok 0.612 | 0.25 | yes | no (latezall) |
| 8 | 4f0c0b40 | f122 0-4 draws, dw0 latez0 | Hyr 0.555 | 0.556 | no (flat) | no: not pixel-bound |
| 9 | 7fd6e4fd..0b5964d2 | 5-32 draws, 14 sampled | Kok 0.488 | - | | no |
| 10 | d8180bd8 | f37 1c, 6 sampled, latezall | 0.435 / - / 0.466 | 0.122 / 0.13 | yes | no (latezall) |

Top dispatches (ms, 100% = 50%, none is resolution-bound): ee7764a6 6x9x12 0.43 (Hyr) / 8x9x12 0.40; 9dc98871 64x36 0.42; cc627640 2x1x1 0.36 (Kok);
27ee9883 16x9x12 0.34 / 12x9x11 0.29; 26fe0c70 80x60 0.21-0.27; 755a777a 1x1x1 0.24 (Hyr); 171c34b2 80x23 0.16-0.23; 435a0138 1x1x1 0.21; ab7699ee 0.17; b6122162 292x1x1 0.17.
The 1x1x1 dispatches cost 0.2 ms each on the 3050 (launch/sync).

VRS list from the 3050 (dw0, latez0, pixel-bound): `1a7482c0` (about 1 ms in every scene, of which 0.75 ms should go away at 2x2), then `d905f52b` (Hyr 0.8).
d8e59341 and 4f0c0b40 are not pixel-bound: VRS cannot help them (dropped from the list).
