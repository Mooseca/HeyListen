<!-- Copyright (C) 2026 Sacrappy -->
# LAPTOP1: 25-30 fps while turning the camera on a low-end laptop (Ryzen 7 5700U, Radeon Vega 8)

Branch `perf/lowend` (worktree `E:\OOT\HeyListen-wt\laptop1`, main 318a4a839 + perf/texcache d7abeb700 merged). Scratch
`E:\OOT\scratch-laptop1`. Lease name `laptop1`. The laptop is run by its pilot session from run lists; its logs come back to
`E:\OOT\scratch-laptop1\L<n>\<arm>`.

Target machine: Ryzen 7 5700U, Radeon Vega 8 integrated (0x1002:0x164c), 15.4 GB shared RAM, no mesh shaders (issue 640 fallback),
driver 26.5.2, Windows; 1920x1080 output, Render resolution 50% (960x540), the game's own upscaling network (Upscaler 0):
`E:\OOT\scratch-texcache\laptop1\TX3_warm\game_log.txt` line 225.

## State

- 20:54 worktree made, texcache4 merged. List 1 (cost map, env-only levers: handheld profile, fog off) routed to the laptop (20:48),
  `E:\OOT\scratch-laptop1\list-laptop1-1.txt`. Main PC pictures of HOS_RES_SCALE 0.333 / 0.25 and the handheld profile queued
  (series s1, texcache4). Code written, not built: the Volumetric fog row (RX_VK_FOG) and the first-start low-end rule (HL_LOWEND).

## Where the frame goes before any lever (texcache4, warm disk cache, MIR_ref_w1)

Source: TEXCACHE list 3 arm 4 (`E:\OOT\scratch-texcache\laptop3\TX3_4_warm\game_log.txt`), 120-present blocks:

| window | fps | draws | GPU ms a frame | GPU uploads ms | gaps between recordings ms | replay "present" ms | "draw" | "descriptors" |
|---|---|---|---|---|---|---|---|---|
| still | 11.8-12.6 | 1896-1927 | 67.6-67.7 | 0.1 | 16.9-17.4 | 53-54 | 32-34 | 14.7-15.5 |
| turning | 9.3-10.7 | 2032-2220 | 73.1-75.5 | 5-17 | 15-16 | 60-72 | 45-53 | 24-29 |

Reading (to confirm with list 1's thread times and pass map): at rest the frame is the GPU's work plus the gaps where it waits for
the next recording; turning adds GPU uploads and about 10 ms of descriptor work and 5-8 ms of texture lookups on the replay side.
Both the GPU (67 ms) and the replay (53 ms) are over the 33-40 ms a 25-30 fps frame allows.

## List 1: the cost map (texcache4, warm cache, 24 Nov 20:52-21:18)

Logs `E:\OOT\scratch-laptop1\L1\<arm>\game_log.txt`, pilot summary `L1\pilot-summary.txt`, read with `E:\OOT\scratch-laptop1\ana.py`.
Every arm WAIT_OWN=1 (the AMD integrated default), 50% render, game's own upscaler.

| arm | what | fps still | fps turning | GPU ms still / turning ("vk: GPU time") | gaps ms |
|---|---|---|---|---|---|
| R0, R1 | reference | 10.3-12.4 | 10.1 / 10.5 | 65-69 / 71-77 | 13-27 |
| H0 | HOS_HANDHELD=1 (the game's handheld profile) | 15.1-15.7 | 13.5 | 48 / 52-55 | 13-17 |
| F0 | fog off (RX_VK_SKIP_PROG on its three programs) | 11.2-13.1 | 12.2 | 59 / 60-61 | 14-16 |
| HF | handheld + fog off | 16.0-17.2 | (7.6: invalid, see below) | 44 / 47-54 | 13-17 |
| THF | the same with the pass map | 14.6-16.6 | 13.6 | | |

- HF's turning is not the lever: its disk cache served 268 textures against 2344-3809 in the others ("vk: BC disk cache" line;
  the map list read nothing, fixed in texcache5), and its GPU uploads were 57-80 ms a frame.
- The machine is GPU-bound: whole-CPU use 10-30% (perf.csv of R0), and frame time = GPU busy + the GPU's empty gaps between
  recordings (R0 still: 69.5 + 27 ms at 10.3-12.4 fps; HF still: 44 + 16 ms at 16-17 fps). HOS_THREAD_TIMES gave no lines on
  Windows (the thread-time sampler is in the Linux path only).
- The game's upscaling network does not run on this GPU: "matrix multiplies in software (no cooperative matrices)", "program
  ... not translated: a network left out on this card" (11 programs), and our TAAU stand-in (linear + FXAA) draws in its place.
  So there is no network cost to remove; any render share works with the stand-in.

### Pass map (RX_VK_PASS_TIMING=2; blocks of 600 presents; T0 block 5 = turning, THF block 5 = still; ms a frame)

| item | T0 (reference) | THF (handheld + fog off) |
|---|---|---|
| busy / window | 77.4 / 92.3 | 47.5 / 63.4 |
| passes | 32.6 (191 spans) | 21.8 (191) |
| dispatches | 19.2 (133) | 9.3 (123) |
| barriers | 3.7 (420) | 3.8 (424) |
| ASTC uploads (u) | 8.1 | 0.2 |
| holes inside command buffers (glue) | 12.4 | 11.2 |
| empty between buffers (gaps) | 14.9 | 15.9 |
| fog 27ee9883 / ee7764a6 / 1e2fcee3 | 5.45 / ~2.8 / ~1.8 (docked: 96x72x88 volume) | off (handheld makes the volume 72x48x56: 1.8 ms in TH) |
| shadow targets | 2400x2400 f126 2.3 + 3 x 1600x1600 f124 2.1 | 1600x1600 f126 0.9 + 3 x 1000x1000 f124 0.46 |
| scene passes | 960x540 (17 kinds) | 768x432 (15 kinds) |
| output-size passes | 1920x1080 f43 1.1, f122 clears | 2560x1440 f43 0.73, 1536x864 f122 0.57 |

The handheld profile is the game's own lower settings, not only a smaller picture: scene 768x432 (from 960x540), shadow maps
1600+1000 (from 2400+1600), fog volume 72x48x56 (from 96x72x88). With the fog off too, no single item over 1.2 ms is left:
what remains is spread over ~190 passes and ~120 dispatches, plus ~420 barriers (3.8 ms), the glue (11 ms) and the gaps (16 ms).

Pictures (`L1\R0\still.png`, `L1\HF\still.png`): HF has no haze (crisp castle and hills, more saturated) and a softer scene; HUD,
Link, Navi, grass right. Acceptable for a low-end preset.

## List 2: the low-end set, the render share under 50%, the mirror instead of the wait (texcache4, 24 Nov 21:19-22:05)

Logs `E:\OOT\scratch-laptop1\L2\<arm>\game_log.txt`, pilot summary `L2\pilot-summary.txt`. LE = HOS_HANDHELD=1 + fog off
(RX_VK_SKIP_PROG on its three programs); M = RX_VK_WAIT_OWN=0 RX_VK_MIRROR=1; 33 / 25 = HOS_RES_SCALE=0.3333 / 0.25.

| arm | fps still (windows 2-4) | fps turning (~60 s) | GPU ms still / turning | gaps ms |
|---|---|---|---|---|
| LE, LE2 | 16.3-16.6, 16.3-16.7 | 13.9, 14.3 | 44-46 / 49-51 | 13-16 |
| LM | 13.7-15.8 | 13.6 | | |
| L33 | 17.2-18.1 | 14.2 | | |
| L33M, L33M2 | 19.0-19.5, 14.0-18.5 | 15.0, 15.3 | 45-47 / 47-49 | 8.5-11 |
| L25M | 17.3-17.9 | 14.9 | 45-48 / 47-49 | 9-13 |

- The scale arms were scaled (T33M: scene passes 512x288 against 768x432; the "Render resolution" line shows the menu's row,
  not HOS_RES_SCALE). The GPU time does NOT follow the render size at this level: 44-48 ms at 768x432, 512x288 and 384x216.
- The mirror in place of the wait takes the gaps from 13-16 to 8.5-11 ms and gives about +1 fps turning at 33% (L33 14.2 ->
  L33M 15.0/15.3), nothing at 50% (LM 13.6 against LE 13.9/14.3). Pictures with the mirror (`L2\L33M\turning+150..450.png`,
  `L2\L25M\...`): HUD, grass and hills right.
- Pictures: 33% acceptable, 25% blocky (`L2\L25M\turning+150.png`).
- Turning frame (L33M2): GPU 48.5 + uploads ~8 + gaps ~10 = ~66 ms, 15 fps.

Pass map at 512x288 (T33M block 5, still, 600 presents): busy 43.9 = passes 18.2 (191 spans, 95 us each), dispatches 9.2 (122),
barriers 3.4 (435), meshconv 0.6, bubbles between spans inside command buffers 11.6; plus 8.8 ms empty between buffers (window
52.7). Largest spans: barriers "other" 1.8 (246 a frame), the game's barriers 1.1 (109), dispatch b6122162 1.3 and indirect
44511d69 1.0 (culling for the mesh passes), 1600x1600 shadow clear 0.8, the 2560x1440 f43 composite 0.7, one-draw grass passes
d905f52b / 739acd67 0.7 each even at 512x288. So what is left is a fixed cost per pass, per dispatch and per barrier, not pixels.

### Why the fixed cost: the no-mesh fallback splits passes

Each fallback mesh draw (`vk_draw.cpp` fallback_record: ~49 a frame here, the "meshconv" count) ends the pass, records 4 full
barriers, fills its records header, dispatches the task and mesh stages as compute, then starts the pass again (a load and a store
of every attachment in GENERAL layout). The laptop's N2 (nomesh notes, docked): RX_VK_NO_MESH_FALLBACK=1 drops passes 193 -> 113
and barriers 438 -> 185 a frame and 5.5 ms of GPU time. List 3 measures that bound at the low-end set.

## Levers

(filled as measured)

## Levers that need more than a night

(filled as found)
