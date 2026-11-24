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

## Levers

(filled as measured)

## Levers that need more than a night

(filled as found)
