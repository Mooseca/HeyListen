<!-- Copyright (C) 2026 Sacrappy -->
# GPU1: cutting the GPU's frame on a weak GPU (2026-11-22), what was measured and what was built

Branch `perf/gpu1` (from `refactor/integ2`, readback ring and native draw loop on). Judge: the PC 3050 (i5-10400F, RTX 3050, driver 621.24),
Market `market-spin`, 1440p 100% render, `dlss=0 upscaling=0 hdr=0 vsync=0`, no frame cap, 2-3 interleaved rounds, game killed at 2 minutes.
Every 3050 number below was run by the 3050's own session from a run list; logs are in `E:\OOT\scratch-gpu1\3050` (local).

## 1. Where the GPU frame goes with the ring on (serialized `RX_VK_PASS_TIMING=1`, the Market-time report of the seq runs)

| Item | ms a frame | Spans a frame | Note |
|---|---:|---:|---|
| render passes | 10.63 | 146 | 1,852 draws; the game's own work |
| compute dispatches | 3.84 | 114 | the game's own work |
| write-backs (`wb`) | 0.87 | 8.8 (131 runs) | 53 MB; the largest emulation item left |
| barriers (recordings') | 0.55 | 210 | |
| readback refresh (`rbrefresh`) | 0.19 | 40 | 1.02 ms before the ring (step 0); 0.8 MB |
| mirror sync (`msync`) | 0.19 | 25 | |
| upload command buffers' barriers | 0.18 | 104 | |
| texture copies (`xfer`) | 0.18 | 7 | |
| mesh-argument conversion (`meshconv`) | 0.12 | 24 | |
| uniform update copies, events, clears | 0.06 | | |
| total (serialized) | 16.9 | | against 16.2 ms of unprofiled GPU time |

Emulation is now about 1.8 ms (11%) against ~3 ms before the ring: the ring took `rbrefresh` from 1.02 to 0.19 ms.
The `wb` row was lowered by the lazy write-back rule already (`wb_lazy_on`); the bytes left are by category (log line
"written back, MB a submit"): pools the CPU writes 5.2 MB a submit, the CPU reads 1.6, outside game pools 0.5, uncached 0.3.

Per-pass dependencies and what overlaps: the `RX_VK_PASS_SEQ` log (below) and the game's own barriers. The Market-time passes of the
seq runs could not be laid out frame by frame (the window of the first runs fell in the load; the second kept only scene-sized
recordings but the passes of the native draw loop's segments are not in the profiled command buffers), so the dependency view comes from
the barriers' counts and from the bounds below, not from a per-pass timeline: **not verified per pass**.

## 2. Barriers: the bound, class by class (PC 3050, `RX_VK_TEST_BARRIER_DROP`, a bound only, the picture may be wrong)

| Arm | fps | GPU ms | GPU tail ms |
|---|---:|---:|---:|
| base | 50.4 | 16.2 | 14.9 |
| `=4` dispatch barriers | 50.6 | 16.0 | 14.8 |
| `=2` pass-start barriers | 50.1 | 16.2 | 15.0 |
| `=8` the game's barriers | 50.7 | 15.9 | 14.4 |
| `=10` pass-start + the game's | 53.0 | 14.8 | 13.8 |
| `=1` all three | 54.2 | 14.3 | 12.9 |

No class alone is worth more than 0.3 ms; two together are worth 1.4 ms (a drain sits at the same place twice and each hides the other).
So eliding only the game's barriers (what `RX_VK_HAZARD_BARRIER` does) has a ceiling of about 0.3 ms (2%).
`RX_VK_BARRIER_TRUST` is already on by default (`hos_main.c`), so A4 = A0; `RX_VK_GAME_BARRIER_NARROW` and `RX_VK_RB_RANGES` are inside the noise.

## 3. Async compute: not built, and why

- The same-queue overlap is what the barrier bounds measure: dropping the dispatch barriers gives 0.2 ms; dropping all of them 1.9 ms. A second queue
  would win at most what the drain bound shows, and the compute that matters (the game's networks, culling, the meter) reads and writes
  guest memory through buffer device addresses, so what a dispatch reads that an earlier pass wrote cannot be proven from the engine's
  side: only the game's `nvnCommandBufferBarrier`s say. 52 of the 56 game barriers of the one seq window are between two dispatches and 4 between two passes.
- The queue families of the 3050 are not known to the engine's log (`vk_main.cpp` picks a graphics+compute family, a compute-only
  family only for the present queue, `RX_VK_PRESENT_QUEUE`); a second queue also means ownership or concurrent sharing for every pool's
  mirror and every render target, and a segment's command buffer cannot wait mid-way: it must be cut in three submissions at each
  dispatch. That is a restructuring of `vk_replay.cpp`'s submission path (batching, late fixes, the timeline waits of captures), not a
  switch; it was not attempted without a per-pass proof that something could overlap.
- What was built instead is the same overlap on one queue with a proof the engine can make: `RX_VK_HAZARD_BARRIER` (section 4).

## 4. `RX_VK_HAZARD_BARRIER` (off; 0 off, 1 on, 2 counts only), `vk_texture.cpp` `hazard_*`, hooks in `vk_replay.cpp` and `vk_draw.cpp`

A game barrier that follows only draws (no dispatch, copy, clear, update, query since the trust point), whose bits only order primitives and
fragments or invalidate textures (0x17), is owed instead of recorded. It is recorded at the first op that is not a draw's state, a draw whose
program writes memory, a draw that samples a texture a pass wrote since the last full barrier, or at the end of the replay call; a dispatch
that samples or stores no such texture goes ahead of it, and the first draw after such a dispatch records it first.

Measured on the 3050 (3 rounds each): list C (`=1` against base) 48.60 / 48.63 fps, GPU 16.15 / 16.08 ms: no change. The counts said why:
of 159 game barriers a frame, 48 were owable and 44 were recorded at once by the next op (UPDATE_UB 21, RENDER_COND 13: the stream's own
lists and CPU reads, no GPU command), 2.6 by a sampled target, ~2 replaced by a later full barrier. With those two ops leaving the barrier
owed (gpu1d) the next forcing op is REPORT_COUNTER (20 a frame). Given section 2's ceiling (0.3 ms) the work stopped there: the switch stays off.

## 5. Tools

`RX_VK_PASS_SEQ=<first>,<count>` with `RX_VK_PASS_TIMING=1` logs the profiled spans of count recordings in order (`vk: seq` lines: start, length, label;
passes carry `W:` (written) and `R:` (sampled) texture addresses, dispatches `T:` (textures and images) and `B:` (storage ranges), the game's barriers their NVN
flags). `tools/gpu1_seq.py <log>` reads them: kinds, overlap bound by game-barrier intervals, barrier neighbours, texture dependence of dispatches.

## 6. Write-back bound (list F, PC 3050, 3 rounds, `gpu1d`, bounds only: both switches bring back issue 50's cut-grass bug)

| Arm | fps | GPU ms | GPU tail ms | written back MB a submit (pools the CPU writes) |
|---|---:|---:|---:|---:|
| base | 49.7 | 16.23 | 14.75 | 5.17 |
| `RX_VK_WB_POOL_EAGER=0` | 50.0 | 15.95 | 14.57 | 0.00 |
| + `RX_VK_WB_SMALL_EAGER_KB=0` | 50.9 | 15.83 | 14.34 | 0.01 |

Serialized (`RX_VK_PASS_TIMING=1`, `WB_POOL_EAGER=0`): `wb` 0.87 -> 0.59 ms (53 -> 25 MB a frame). The ceiling of a rule that writes back only
what the CPU reads is ~0.4 ms of GPU and +2.4% fps on the 3050. Not built: the safe rule needs per-page tracking of pages both sides write (the
mirror sync's chunk diff, `RX_VK_MSYNC_DIFF`, protects the GPU's words only at its 256-byte granularity).
