<!-- Copyright (C) 2026 Sacrappy -->

# STUT3 (25-26 Nov 2026): the stutters on the PC 3050, by cause, and the cold pass's pool gate

PC 3050: i5-10400F (6 cores, 12 threads), 32 GB, RTX 3050 8 GB, Windows 11, NVIDIA 621.24. All runs from `run_bench.py` with the
default ini plus `send_performance_stats=1` (the hitch log writes only while the performance summary measures; with no telemetry
address nothing is sent), `HL_HITCH_LOG=rel:8 HOS_PERF_REPORT=1`, frame times from `present_trace.csv` counted from "play: began" +
10 s. Analysis scripts are the kit's (`runs/s3stats.py`, `f1.py`, `st1.py`, `c500.py`), not in the repository.

## The player's state

A player's folder before the first start holds the setup's files, the builder's shader census (`hookshot_shaders.bin`) and the
shipped pipeline state list (`hookshot_pipeline_states_shipped.bin` = `profile/pipeline_states.bin`); the builder then runs
`HeyListen.exe --prepare-shaders` (201-220 s here). That is the "first visit" state below; the "second visit" is the same folder
after one run. The NVIDIA driver's own shader cache could not be reset: first-visit driver compiles are under what a player with a
cold driver cache sees.

## The tour

The warp tour: from the Kokiri Forest save, the camera turning, live cheats 1000 / 1001 / 1002 / 1003 / 1009 / 1012 at +20 / 60 /
100 / 140 / 180 / 220 s (Kokiri, Hyrule Field, Kakariko, Market, Death Mountain Trail, Zora's River), 300 s of play.

| state (main e5e14b2a) | fps | frames > 50 ms a minute | > 100 ms a minute | s in frames > 33 ms |
|---|---|---|---|---|
| first visit (2 runs) | 74.8, 68.1 | 37.9, 27.7 | 8.7, 7.7 | 39.3, 31.8 |
| second visit (2 runs) | 63.0, 68.0 | 34.4, 32.8 | 6.7, 6.1 | 36.3, 36.8 |

The first visit is not worse than the second: with the shipped list, compiles are under 1 s of the ~36 s of stutter a tour (pipe,
xlate and drvcomp the largest part of 1-4 hitches). The Market with the camera turning (market-spin) has 1-3 frames over 50 ms
after its first 10 s, first or second visit; its arrival (the first 10 s) holds 11-29.

## Causes (hitch lines over 50 ms, by their largest measured part)

- **Readback waits**: 62-127 a tour, 7-14 s. The hitch log's own label for most of them is `gpu_bound`, with 1-40 ms of GPU time in
  the frame. With the read's label in the line (`| rb ...`): the culling job's 0x3980-byte reads in two pools, phase `rec` (the read
  waits for the replay to record the write-back), 110-125 hitches a tour; the 0x9b040 lists once. Not the order thread's doing:
  with `RX_VK_ORDER_THREAD=0` they stay (110-127) and 0x40 reads join them, and fps falls from 66-68 to 54-58.
- **Texture uploads with page faults**: 10-24 a tour, 3.5-6.3 s.
- **Render time the log does not split**: 27-63 a tour, 2.4-5.2 s. With the stall watch, in those gaps the order thread uses 5-15 ms
  of CPU and ends in a kernel wait, and the busiest thread is the game's main thread spinning in a short sleep: the presenting
  thread waits on something in the renderer the line does not time. The hitch line now ends with the renderer's waits of the frame
  (`| waits: slot .. (ahead ..) done .. ring .. value .. ot_idle ..`).
- **Page faults**: in the seconds holding a frame over 50 ms, 1.2-3.0 GB of pages come into the working set (`HL_FAULT_WATCH`): guest
  GPU pools (the game's `aglTextureDataMgr::Compaction`, its loaders, the replay), guest address regions (the loaders), host memory
  with no owner (the order thread).

## The cold pass's pool pages

The cold-pages pass (`HL_MEM_COLD`) took 5.3-6.3 GB of GPU-pool pages out of the working set in each tour and 3.9-4.6 GB came back
(heaps: ~3 GB out, 0.7 GB back). With the PC at 4.4 GB free at the least (22.9 of 31.9 GB in use, commit up to 98.6 percent), six
second-visit tours alternated:

| arm | fps | > 50 ms a minute | > 100 ms a minute | s in frames > 33 ms |
|---|---|---|---|---|
| default | 67.11, 65.80, 66.09 | 42.9, 41.9, 51.4 | 10.3, 8.4, 12.9 | 37.1, 40.2, 40.4 |
| `HL_MEM_COLD=0` | 65.21, 68.16, 65.35 | 44.4, 35.3, 44.1 | 8.9, 5.9, 6.9 | 38.9, 32.7, 36.3 |

Frames over 100 ms -31 percent, every run without the pass below every run with it; fps unchanged. But the next series' default
arm (7.2, 9.1, 7.4 a minute) was level with this "off" arm: the spread between series is as large as the effect, and a claim needs
one series of five tours a side.

A first gate on the pools alone (pool pages taken out only under 4096 MB available) did not help: nine tours alternated, today's
pass 7.2 / 9.1 / 7.4 frames over 100 ms a minute and 67.53 fps, the pool gate 6.5 / 8.2 / 10.2 and 66.27 fps. With the pools left
alone the heaps' part took 6 GB out and 2.2 GB came back (0.9 GB with the pools trimmed: the pools' come-backs had kept the heaps'
quiet rule on). The pool rule forced "low" all the time matched today's pass in pages out and back (the low-RAM path unchanged),
and free RAM stayed 4.5-4.9 GB in every arm (commit 98-99 percent, as before).

So the gate is on the whole pass: it runs only while the available RAM is under `HL_MEM_COLD_LOW_MB` (4096) and stops again once it
is back at `HL_MEM_COLD_HIGH_MB` (6144); `HL_MEM_COLD_LOW_MB=0` is the pass as it was (host/hl_mem_coldgate.h,
tests/test_cold_gate.py). On this PC that is the pass off. Its proof is one series of five tours a side, alternated.

## The longest frames

Of the frames over 500 ms in 16 tours: one of 2.1-2.5 s at the start of play in every start (a draw into a target made that frame
waiting for a pipeline built in play, `RX_VK_PIPE_WAIT_FRESH`: slow-submit lines "pipelines 1960-3811"); 0.5-1.7 s at each zone
arrival (readback waits, uploads with faults, the game thread off CPU); twice a first compute dispatch waiting 1-2.9 s
(`RX_VK_LAZY_COMPUTE`); and five of 3-12.7 s that no line names yet.

## Step 2, sized (not built): the upload's CPU copy out from under the parallel replay's lock

**What the lock protects there.** `vk_draw.cpp texture_view_of()` (every descriptor build, per texture handle): a handle seen the first
time takes ParLock (one recursive mutex for all segment workers) for `texture_of`, `texture_get` (the Texture and its image),
`texture_view` and `texture_touch` (the upload); a known handle tries `texture_touch_quick` / `texture_touch_unlocked` and falls back to
ParLock + `texture_touch` when it needs an upload. Inside `upload()` / `upload_astc_gpu()` (vk_texture.cpp), under the lock: `staging()`
(the arenas vector), `guest_bytes()` (`memory_as_submitted`, the late-fix wait, the lazy write-back settle), the memcpy or CPU
unswizzle into staging (where the page faults land), the BC and disk cache maps, recording into `upload_cmd()` (one command buffer a
recording), the texture's upload state, the budget counters and the GPU write history. The copy is inside only because it sits between
the reservation and the recording. Meanwhile every other worker's descriptor build waits on the lock (the freeze lines' "desc", summed
over workers), the order thread does not record, and the game's 0x3980 read waits ("readback").

**Two phases instead.** (a) Under ParLock, short: find or make the Texture, decide the upload, reserve the staging range (arena +
offset, pinned by its rec_value), set a per-texture "upload in flight" token and pin the Texture, copy the parameters. (b) Outside: the
guest read and the copy or unswizzle into the reserved range (the faults, in parallel on the 4-6 workers). (c) Under ParLock, short:
re-validate (not destroyed or evicted, slot version unchanged), record the copy or the ASTC dispatch, the BC/disk cache entries, set
uploaded/upload_gen, publish, clear the token. Readers that must respect the token: other workers meeting the same texture (the touch
fast path, the handle cache), the eviction pass and texture destroy, the defer budget.

**What can go wrong.** A draw binding the image before (c) recorded its copy (the copy must go to the right segment's upload buffer,
as SegInit does for first layout changes); eviction or destroy between (a) and (c) (pin; drop the range if gone); guest memory read
outside the replay's serialization (`memory_as_submitted`, the late-fix and lazy write-back calls write guest memory: the riskiest
part, where the guessed write-backs and the crash family live); two workers uploading one texture (the token); the BC7 remake flag
set in (b). Failure modes: wrong or missing textures, validation errors, a lost device on a destroyed image.

**Tests.** A state-machine header (reserve / fill / publish, pin, token, eviction in between) compiled and run with two threads; text
checks that the copy holds no ParLock and that (c) re-validates; a parallel-replay stress with a fake host; pictures at the six
arrivals, the hitch lines' desc/upload/readback at arrival, validation layers once; a switch to turn it off.

**Expected gain** (estimates from the logs' parts, not measured): start freeze 1.1-2.5 s to about 0.9-1.3 s; arrival frames 0.5-1.7 s
to 0.3-0.9 s; a zone change of 1165 ms (descriptors 1404 + upload 1023, 264k faults) to 500-700 ms. The faults stay (3-10 us each,
1-3 s of CPU, spread over threads). No fps change. Size: 4-5 working days, risk medium-high: after the release, behind a switch.

**The page faults (120-380k a frame).** In the seconds holding a frame over 50 ms: guest GPU pools about 40 percent (the textures'
source arrays the upload reads: many taken out by the cold pass, which the gate now stops on PCs with RAM to spare; others never
resident since loaded), guest address regions about 30 percent (the loaders' file reads, not the upload), host private memory about
20 percent (new 64 MB staging arenas, freed when idle and faulted again at each zone; capture buffers). The destination is VRAM.
Ahead of time: a worker could touch a texture's guest source when the game registers it (before its first draw), and the staging
arenas an arrival needs could be kept and touched by a worker when made (RX_VK_STAGING_KEEP_MB / _IDLE_S / _BURST_S exist).
