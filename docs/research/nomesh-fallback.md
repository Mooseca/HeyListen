Copyright (C) 2026 Sacrappy

# GPUs without mesh shaders: where the time goes (AMD Ryzen 7 5700U, Radeon Vega, Hyrule Field)

## State

(25 Nov 2026, perf/nomesh on main 51e533a87; notes only, no code change yet.)

- Machine: Ryzen 7 5700U (Lucienne, vendor 0x1002 device 0x164c), 15.4 GB RAM, driver 26.5.2, Vulkan 1.3.260, 1920x1080 at 50%
  render scale (960x540). `vk: no mesh shaders: task and mesh programs run as compute shaders (issue 640 fallback)`.
- Right picture, still camera: about 13 fps, GPU 60-67 ms a frame. Turning camera: 8-9 fps (uploads of new textures).
- White/cyan grass, black parts and the HUD flicker are one fault: the GPU reads guest memory in place after the game rewrote it.
  RX_VK_WAIT_OWN=1 (default on AMD integrated GPUs) and RX_VK_MIRROR=1 both remove it; they run at the same speed
  (13.1 against 13.2-13.5 fps still). The 16 fps of WAIT_OWN=0 is the faulty picture, drawn with the same number of draws
  (about 1883 against 1847-1870) but cheaper.
- Open: the three big compute dispatches (below), the CPU unswizzle of non-ASTC textures in turning frames, the fallback's pass splitting.

## GPU time split (RX_VK_PASS_TIMING=2, still, WAIT_OWN=0, 59.6 ms a frame)

| part | ms | share |
|---|---|---|
| render passes (193 a frame, 1882 draws) | 30.3 | 50.8% |
| the game's compute dispatches (125 a frame) | 19.2 | 32.2% |
| barriers (438 a frame) | 4.3 | 7.2% |
| xfer, meshconv, events, other | 1.9 | 3.2% |
| gaps between buffers | 4.1 | |

Switches tried, one at a time (still camera):

| switch | GPU ms a frame | note |
|---|---|---|
| none | 59.6 | |
| RX_VK_NO_MESH_FALLBACK=1 (mesh programs not drawn) | 54.1 | the whole mesh path is about 5.5 ms; pass spans 193 -> 113, barriers 438 -> 185 |
| RX_VK_BARRIER_HAZARD=3 | 59.65 | no gain |
| RX_VK_SKIP_PROG of the three dispatches below | 50.6 | 15.4 -> 18.9 fps, same draw count |

## The three big dispatches

Binding sizes and IR shape only (the IR dumps stay under OOT\runs\amd-1124\ir_dump on the laptop, not in the repo).

| key | grid x workgroup | voxels | ms a dispatch | what the IR shows |
|---|---|---|---|---|
| 27ee9883e2a20323 | 12x9x11 of 8x8x8, 18 KB shared | 96x72x88 | 5.5 | 13k ops, 457 blocks, 20 texture samples + 2 depth-compare samples, 6 image writes, shared memory, exp2/recip: a volume (froxel) pass with shadow lookups, no buffer stores |
| ee7764a6b1ef459c | 6x9x12 of 8x4x4 | 48x36x48 | 2.5 | 19k ops, 493 blocks, 112 global loads (72 x 32 bit, 40 x 128 bit: pointer reads), 12 samples + 2 depth-compare, 10 image writes |
| 1e2fcee33a0c7209 | 12x9x1 of 8x8x1 | 96x72 | 1.8 | 525 ops, 3 samples, 3 image writes: a small screen-space pass |

All three read the 224 MB guest window at c0+0x880 (27ee also a 9.5 MB and a 98 KB storage buffer). Outputs are images, not buffers.

## The fallback's pass splitting

Trace of one frame (RX_VK_PASS_TRACE_AT): 50 passes, 28 of them on the 1600x1600 depth-only target (30 draws, one draw a pass, a
different program each), 14 on 960x540 f122 (81 draws). A fallback draw's compute dispatches cannot run inside a render pass, so the
pass ends and restarts with a load/store of the 1600x1600 depth. The 1600x1600 spans take 2.7 ms and a 2400x2400 depth-only
target (a clear, 0 draws) 2.6 ms a frame. Idea, not done: record every fallback draw's dispatches first and then one pass.
Bound of the gain from N2: 3-4 ms (about 1 fps). No switch scales these shadow maps in main14.

## Open leads (25 Nov 2026)

1. The fallback's pass splitting: about 1 fps (3-4 ms of GPU; N2 without the fallback 59.6 -> 54.1 ms, 80 passes and 250 barriers
   a frame fewer). Needs one record pair per fallback draw instead of the shared pair, so more record memory.
2. The per-frame upload work while turning: 55-75 ms of a 65-70 ms frame, 6-9 textures made a frame; CPU unswizzle of the
   non-ASTC formats about 59% of it, the GPU ASTC decode about 41%. Small textures take tens of ms (0.2 MB in 52-80 ms), which
   is not unswizzle time and not paging (T0/T1 below).
3. The volumetric-fog volumes (27ee, ee77): a switch that runs them every second frame, and off as a low-end option, is being
   written on the main PC; the volume-scale idea is parked (the images keep the game's size).

## Results of 24-25 Nov (same field, main14 = main 51e533a87 minus the wait change)

- ASTC decode: on the CPU it stalls 12-20 times a minute for 1.1-1.9 s (1.5 fps while turning); on the GPU 14.2 fps (the spin
  script) and no stall. Vega-generation APUs keep the GPU decode (8f5ca506b).
- Wait: values 0, 2, 3 flicker the HUD in 15-17 of 20 pictures, 1 in none; RX_VK_MIRROR=1 with WAIT_OWN=0 also none (a 32 MB mirror
  is enough), at 13.2 fps still and 8.9 turning against 13.0 and 8.4 for WAIT_OWN=1.
- T0/T1 (b'): turning 60 s window 7.9 fps with the cold-page trimming, 8.3 with HL_MEM_COLD=0 HL_MEM_COLD_HEAPS=0 (+5%, noise). The
  trimming is already held under 3072 MB of free RAM, always the case here (free RAM min 1.4-1.7 GB). Page faults avg 9.3k/s and
  12.1k/s, pages input 0.4k/s: paging does not explain the small uploads' time. The sums over the 14 "a frame's uploads took" lines:
  took 2064 / 1940 ms, on the CPU 1096 / 874 ms, ASTC on the GPU 946 / 1016 ms.
- The three dispatches (a): see the table above; the picture with them skipped has a crisper distance (a haze removed).

## Turning cost

Turning frames carry 55-75 ms of uploads on a 65-70 ms frame. Of the 4 biggest upload frames, 882 ms are "on the CPU"
(non-ASTC formats 0x4b, 0x46, 0x49, 0x4d, 0x8b) and 611 ms "ASTC on the GPU". HL_MEM_COLD=0 (trimming off) gives +5% (noise):
the cold-page trimming is already held when free RAM is under 3072 MB.
