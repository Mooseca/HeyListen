# ASYNC1: the game's compute dispatches on a compute queue beside the graphics work (23 Nov 2026)

Branch `perf/async1` from `refactor/integ4` (2ed3bab9c: 133566ac7 plus the test-only commit after it). Main PC (RTX 5070, Ryzen 7 7800X3D).
Switches, all off by default: `RX_VK_ASYNC_COMPUTE=1` (the async path), `RX_VK_ASYNC_CHECK=<frame>[,<frames>]` (the check: footprints and
plans in the log, nothing recorded changes), `RX_VK_ASYNC_CUT=<draws>` (how big a graphics chunk gets before the game's next barrier cuts it,
default 16). Analyzer: `tools/bench/async_check.py <game_log.txt> [--gprof extract.txt]`.

**Verdict in one paragraph.** The machinery works: with `RX_VK_ASYNC_COMPUTE=1` a third to a half of the frame's dispatches (Kokiri:
43 of 121) run on the compute queue (family 2 of the RTX 5070, 8 queues). Kokiri, Hyrule Field and the Market ran with no device lost, no
Vulkan error and no stuck island, and the pictures match. **But in this first stage almost nothing overlaps.** The check shows why: the game's
compute work is not interleaved with graphics inside a recording part. It arrives as **parts of its own** (the NVN compute queue's
submissions, and the small command buffers SMALL1 found: light culling, particles, skinning), whose only "graphics" is an upload command
buffer before them and the write-backs after them. An island can only overlap work in its own part (the memory work's order is
per part), so it waits for its part's uploads (everything before it on the graphics queue) and the part's end waits for it. Kokiri,
two frames: 23 islands a frame, **0 draws beside any of them**. On the 5070 (CPU-bound) Kokiri was 114.1 fps against 116.3 and 118.5 off (the
extra submits and semaphores, as expected). The overlap the brief is after needs the next stage: completion
tracked per queue (a part done when both its queues are), footprints for the memory work (uploads, mirror syncs, readback refreshes,
write-backs), and the join of a compute part's islands deferred to the first *later* part that conflicts with them. **Proposed default: off.**
The check (`RX_VK_ASYNC_CHECK`) and the footprint library are what that next stage needs, and they are in.

## 1. How the replay records dispatches today

- **One queue.** Every recording (a submission's part, a parallel replay's segment, the uploads) goes to `dev.queue`, the graphics family's
  queue 0, in the stream's order (`submit_recording`, the segment submits, the batched flush). The presents may have a compute-family queue
  of their own (`RX_VK_PRESENT_QUEUE`, off since issue 1161), and the swapchain images are already shared between the two families.
- **The game's queues are interleaved by their events.** Each NVN queue's submissions are replayed in turns at their event waits
  (`submit_job`, `run_submit`, `resume_queue`, `schedule`); a burst puts a submission and the stopped ones it lets on into one recording.
  The console runs queue 3 (compute: culling, lights, fog) beside queue 6 (graphics); the replay runs them one after the other.
- **Barriers.** The game's `nvnCommandBufferBarrier` is a full barrier (`ALL_COMMANDS`, memory write -> read/write), or a fragment-only one
  for `ORDER_FRAGMENTS` (`game_fragment_barrier`). A dispatch after other work gets a full barrier of its own (`dispatch_barrier`), a
  dispatch right after a dispatch none (`RX_VK_GAME_ORDER`, NVIDIA's default). Every recording starts and ends with a full barrier and ends
  with a host-read barrier. There is no per-resource hazard tracking: the order is the queue's and the barriers are global.
- **Memory work.** Guest pools are imported host memory, hot ones mirrored in VRAM. A part's uploads (texture uploads and decodes, the
  mirrors' CPU pages: `msync`, the readback pages: `rbrefresh`, the page table) go into its upload command buffer, submitted *before* the
  part; its write-backs (mirror -> guest memory, ~1 ms a frame in Kokiri) are recorded at the part's end (`memory_end_submission`). Uniform
  updates of the stream are kept in a list and written at the part's end (`flush_ub_updates`); bindings that overlap one read an overlay.
  Counters are written on the CPU in stream order. The mesh conversions (`RX_VK_MESH_CONV=2`) are dispatches recorded at the game's
  barriers, ahead of the mesh draws they serve.
- **Who records what.** With the parallel replay (on with 8+ hardware threads) a command buffer goes through a dry pass, then is either cut
  into segments (recordings of their own, recorded by the workers: 2 x 128 draws and dispatches and up, or 128+ with `RX_VK_MID_SEG`), or
  recorded whole into the open part by `record_segment` on the replay thread (in the workers' mode). The serial `replay()` pass records
  only with the parallel replay off, the GPU pass timing on (`RX_VK_PASS_TIMING`), or a dump. SMALL1 found the frame's compute batches
  (light culling, particles, skinning: 14-200 dispatches each) among the command buffers recorded whole.

## 2. What Rekarina tried, and the trap

`ext/rekarina/docs/oot-notes.md` and `roadmap-100fps.md` (read only, nothing run):
- *Async write-back on a compute-family queue* (`REKARINA_ASYNC_WB`): the save never finished loading. The cause was a **self-wait**: a
  part's prologue ran after its own write-back ranges were noted, its uploads overlapped them, so the part waited for the write-back of its
  own fence while the write-back waited for the part. With that wait skipped and the shared buffers made CONCURRENT it loaded, but ran
  slower (71 against 82-89 fps) and flickered hard: the next submissions rewrote words the pending write-back read.
- *Write-back on a second graphics-family queue*: NVIDIA time-slices two graphics-family queues; with the waits needed the two queues
  slowed each other (graphics 16 -> 32 ms).
- *Queue 3 on the compute queue* (`REKARINA_ASYNC_COMPUTE`, with the queues interleaved by their events): no speed on their forest path,
  and their mirror bookkeeping "is per submission and assumes one order: it has to become per queue first".

What this design keeps from it: a compute-only family (never a second graphics queue); **no memory work on the compute queue** (the islands
hold dispatches and the game's barriers only: uploads stay before the part, write-backs after it, on the graphics queue, in the order they
had); every wait is for work recorded *before* the waiter and already submitted (no self-wait, no wait before signal, no cycle); and
nothing is guessed from the game's events: the overlap is allowed only where the footprints prove it.

## 3. Design (first stage)

1. **Islands.** In stream order into the open part (the serial pass, or a command buffer recorded whole into the part on the replay
   thread), a run of dispatches with nothing between them but state, bindings, event waits and the game's barriers (a barrier only when
   a dispatch follows it) is recorded into a command buffer of the compute queue's family. A dispatch whose program is one of the game's
   networks (cooperative matrix, `gameplay_network`, TAAU: their stand-ins draw), not yet made, or watched by a diagnostic stays on the
   graphics queue. An island starts with a full barrier and ends with a host-read barrier.
2. **Chunks.** The part's graphics work is cut into command buffers at the game's barriers and event signals once a chunk holds
   `RX_VK_ASYNC_CUT` draws (16), a dispatch or opaque work, and always around an island (a full barrier opens the chunk after it: the
   island's barriers no longer order the graphics work on either side).
3. **Footprints** (`async_compute.h`), in the game's GPU address space: storage buffers as bound (a bare table entry to its pool's end),
   uniform buffers c3 and up, texel buffers to their pool's end (256 MB at most), textures and storage images by their storage, render
   targets (written), vertex, index and indirect buffers. Opaque: copies, clears (buffers, textures, attachments), counters, uniform
   updates, render conditions, the mesh conversions and the part's write-backs. An event signal writes its word.
4. **Plan, at the part's submit.** An island waits for the last chunk before it that conflicts with it (one writes what the other reads
   or writes; opaque conflicts with all), or for the part's uploads; the graphics work waits for the island from the first chunk after it
   that conflicts with it, or at the part's end. The chunks between run beside it.
5. **Submit.** Two timeline semaphores, one signalled only by each queue (a timeline's value must grow in the order its signals run, and
   the two queues run independently). In the stream's order: the uploads alone (a signal), the chunks in batches cut where an island waits
   (a signal) or where a chunk waits for an island, each island on the compute queue right after the batch it waits for; the part's last
   batch waits for every island not joined yet and carries the part's timeline signals and fence, so every reader of the part (fences,
   the timeline, the next parts) sees the islands done. The batched submits are flushed first (`queue_flush_locked`, which applies the
   pending late fixes).
6. **Sharing.** With the queue, every buffer and image is made CONCURRENT between the two families (`vkCreateBuffer` / `vkCreateImage`
   wrapped in vk_main.cpp, and given to VMA): no ownership transfers. Cost: none measured on NVIDIA buffers; AMD may lose image
   compression (DCC) on CONCURRENT images.
7. **Off with** the GPU pass timing and the performance profile (their query pools are the graphics queue's), dumps, and anything
   that is not the stream's order into the part (the workers' segments keep their dispatches on the graphics queue).
8. **Device-lost watch.** An island not done 2 s after its submit is logged (both queues' progress); a device lost logs the two
   semaphores' values against what was submitted, and the compute queue's checkpoint count.

Not in this stage (each is a hazard the check names): islands inside the workers' segments, islands across parts (a part's uploads are
one command buffer that may rewrite what an island reads), the game's queue 3 placed by its events beside queue 6 (Rekarina's roadmap),
memory work on the compute queue.

## 4. The check (`RX_VK_ASYNC_CHECK`)

`RX_VK_ASYNC_CHECK=<frame>[,<frames>]` logs, for those frames (lines `vk: acx f<frame> t<thread> ...`): every dispatch with its
footprint (`disp ser=<n> cmd=<cb> prog=<key> grid=... R=<ranges> W=<ranges>`), every pass with its draws' union (`pass ser=<a>-<b>
draws=<n> ...`), the ops between them (barriers, event signals and waits, copies, clears, counters, uniform updates, render conditions,
mesh conversions), each recording's begin and end (`rec+`, `seg+`, `rec-end ... uploads=<0|1>`), each part's write-backs (`memend`), each
game queue's piece (`run q=<queue> ...`, `stop ...`) and every queue submit with its command buffers in order (`qsubmit <kind> cbs=...`).
With `RX_VK_ASYNC_COMPUTE=1` it also logs each island's plan at the part's submit (`island slot=.. k=.. dispatches=.. at=../.. dep=..
(why) join=.. (why) beside=.. chunks .. draws`). Outside those frames the cost is one test per op. `tools/bench/async_check.py` rebuilds
the frame's command buffers in queue order and applies the planner per island, in the part (stage 1) and across parts ("any part");
`--lenient` treats counters (CPU writes), uniform updates (written at the part's end), render conditions (CPU reads) and clears (the
pass's targets) as not opaque, `--memory-free` drops the upload command buffers and write-backs: the ceilings of later stages.
The frame number is the present count (`texture_frame_no`), and the menus run at 340 fps before play: pick a frame past "play: began"
(on the 5070, 15000 at a 45-55 s load).

**Kokiri, 5070, frames 15000-15001, async on (`ac2-chk-async-kokiri`).** 121 dispatches a frame:

| where the dispatch was recorded | dispatches a frame | why |
|---|---:|---|
| an island (compute queue) | 43 | runs of dispatches recorded into the part in stream order |
| a part's graphics chunk | 64 | the island cap (16 a part) reached: the game's uniform updates between the 1x1x1 dispatches (`755a777a`, 35 a frame) end each island |
| a worker's segment | 14 | big command buffers cut into segments (the networks `9dc98871` among them: never an island anyway) |

Every island's plan: `dep=-1 (the part's uploads) join=<end of the part>`, beside it 1-20 chunks with **0 draws**: the parts that hold
islands hold nothing else. 13 parts a frame end with uploads in 10. Island counts over the whole run (the stats line, every 3000 parts):
7.7 islands a part with islands (23,000 in 3,000 parts), all of them waiting for the part's uploads only, 91% joined at the part's end
and 9% where a later chunk of the part reads what they write.

What the analyzer says of the frame across parts, with the memory work and the CPU-side ops forgiven (`--lenient --memory-free`): a
handful of single dispatches inside graphics streams (`6ccba775`, `942cd7b4`, `600f56f6`) could have 200-700 draws beside them; the costly
compute (`ee7764a6` 0.42 ms, `27ee9883` 0.36 ms, `171c34b2` 0.23 ms in the 3050 profile) has 22-29 draws beside it before a pass that
reads its output: the game uses those results right away in the next graphics part. The 1x1x1 chain (`755a777a` and its neighbours) reads
150 MB of a pool through a bare pointer (bound to the pool's end), so its footprint is coarse and conflicts with most writers.

Hazards the check found, by kind (the reasons in the plans and the analyzer): the part's uploads (most), clears of attachments at pass
starts (as opaque work: they are the pass's target writes and could be footprinted), counters and uniform updates (CPU-side, could be
dropped from the opaque list), mesh conversions (dispatches of their own on the graphics queue, reading the game's indirect arguments),
the part's write-backs, `copy-t2t`/`clear-tex`/`clear-buf` (real GPU writes, unfootprinted), and direct read-after-write (a pass sampling
the island's storage image or reading its buffer).

## 5. Validation

- Unit test `tests/test_async_compute.py` (+ `.cpp`): the range sets (merge, half-open overlap, the cap that only grows), conflicts,
  the planner (dep, join, opaque chunks, the part's start and end), and the renderer's source shape (the hooks, the submit path, the
  CONCURRENT wrappers). The source-shape tests the change touched (`test_late_defer`, `test_device_lost_exit`, `test_parallel_rb_refresh`,
  `test_mesh_conv`, `test_same_bind`, `test_bank_gen`, `test_split_before_draw`, `test_compute_pipeline_atomic`) pass; full suite: see
  the commit.
- Function on the 5070, `RX_VK_ASYNC_COMPUTE=1`: Kokiri (`kokiri-idle`), Hyrule Field (`hyrule-idle`), the Market (`market-spin`), and
  the Kokiri fps runs: no `FATAL`, no device lost, no `VK_ERROR`, no "island ... not done". Hyrule and Market pictures
  (`RX_VK_SHOTS`, one per 300 presents) look as the async-off ones: light, fog, shadows, grass, characters.
- Validation layer (Vulkan SDK 1.4.363, `RX_VK_VALIDATION=1` with `VK_KHRONOS_VALIDATION_VALIDATE_SYNC=true`, errors only, 10 of each),
  Kokiri village, one run each way (`ac2-val-base`, `ac2-val-async`): both reached play (69 s) and played ~40 s at 18-24 fps. The only
  message in both is `VUID-vkResetQueryPool-firstQuery-02741` (an existing query-pool reset out of range, not this change). With async on:
  no synchronization hazard, no queue-family-ownership or sharing error, no semaphore error, while islands ran on the compute queue
  (the stats line: 6,000 parts with islands by then). Short, and one scene: not a proof, but the timeline-semaphore scheme and the
  CONCURRENT sharing pass the layer.

## 6. Numbers

fps from "play: began" + 10 s, speed lease, slot c, one build (`async1`, f93b1e4eb) with env arms (`RX_VK_ASYNC_COMPUTE=1` or not),
interleaved after a warm-up. No run had more than 15 frames over 50 ms except the validation runs.

| scene (save) | A: off | B: `RX_VK_ASYNC_COMPUTE=1` | B/A (medians) |
|---|---|---|---:|
| kokiri-idle (kokiri-village) | 126.6 / 129.0 / 127.3 | 117.8 / 121.4 / 119.3 | **-6.3%** |
| kokiri-idle (kokiri-forest, 2 rounds, interrupted) | 116.3 / 118.5 | 114.1 | -2.8% |
| castle-move, market-spin | not run: the leases went to the owner twice, then to stage 1b | | |

The "GPU time" line drops with async on (Kokiri village 6.5 -> 6.0 ms a frame, median of the windows) only because it times the graphics
queue's command buffers: the islands' work moved to the compute queue is no longer in it. On the 5070 the replay's CPU chain is the
limit (MORNING.md, ORDER3), so the cost is the CPU's: a command buffer per island and per chunk (`vkBegin`/`vkEnd`, the draw path's bound
state forgotten at each switch: pipelines, descriptors and vertex buffers bound again), the footprints of every serial draw and dispatch,
and 3+ queue submits a part with islands instead of one (never batched). Stage 1 gains nothing to pay for it.

PC 3050 (GPU-bound in Kokiri and Hyrule at 100%, where the gain should show if the work overlapped): run list sent to the coordinator
(3 scenes x 100%/50% x 3 rounds A/B, pictures, the stats line). Expected from the check: no gain (nothing overlaps), a small loss from the
extra submits and semaphore waits.

PC 3050, Task 40 (build `async1` #2, 2560x1440, upscaler off, fps from play + 10 s; routed by the coordinator, read from
`C:\OOT\pc3050s-out\async1\` and `matrix40.txt` there):

| render | scene | A: off | B: `RX_VK_ASYNC_COMPUTE=1` | B/A |
|---|---|---:|---:|---:|
| 100% | Kokiri | 44.6 | 43.5 | -2.5% |
| 100% | Hyrule | 40.5 | 40.1 | -1.0% |
| 100% | Market | 42.1 | 40.7 | -3.3% |
| 50% | Kokiri | 59.6 | 57.2 | -4.0% |
| 50% | Hyrule | 55.9 | 52.8 | -5.5% |
| 50% | Market | 48.6 | 47.1 | -3.1% |

Slower everywhere, by 0.2-0.9 ms a frame (more at 50%, where the frame is shorter and the fixed cost weighs more).

## 6b. Where the cost comes from (stage 1b)

From the check: the parts that hold islands hold no draws (Kokiri: 23 islands, 0 draws beside them, two frames). So nothing overlaps, and
each island costs a round trip between the queues: the graphics queue signals (the part's uploads), the compute queue waits for it, runs
the island and signals, and the graphics queue waits for that before the part's end. On Windows both waits go through the kernel's
scheduler (the queues' monitored fences); each adds the time from one queue's signal to the other's start, with the GPU idle
in between, about 23 times a frame. On the CPU, each such part goes out in 3+ queue submits instead of one (never batched), and every island
and chunk is a command buffer of its own with the draw path's bound state forgotten at each switch.

Stage 1b (build `async1` #3, 906bbb893) measures it and cuts it:
- `RX_VK_ASYNC_STAMPS=1`: a timestamp at each chunk's start and end on the graphics queue and each island's on the compute queue (two a
  command buffer, nothing serialised), read back when the slot comes round again, and the async path's CPU time on the replay thread.
  The line "vk: async stamps, a frame ..." gives per frame: compute busy, compute beside this part's graphics (the overlap), the part's
  graphics busy and idle, the latency from what an island waits for to its start, the latency from an island's end to the chunk that
  waits for it, and the CPU (submits, island open/close, chunk switches).
- `RX_VK_ASYNC_MIN_DRAWS=<n>` (default 1): an island opens only in a part that has recorded n draws: none in the compute-only parts.
- uniform updates and counters (no GPU work in the stream) inside islands and out of the opaque list; clears as their targets' writes;
  one compute submit for all islands that wait for the same point.
- `RX_VK_ASYNC_ISLANDS=0`: chunks and footprints but no island: the tracking's own CPU cost.

STAGE1B_RESULTS

## 7. Risks and what is not verified

- **No overlap in this stage, so no gain**: on the 3050 (GPU-bound in Kokiri and Hyrule) the same is expected; the run list was sent so
  that the stage's cost there is measured too. The gain needs the next stage (below).
- **Footprints are a model, not a proof.** They cover what the descriptors bind, the targets, vertex, index and indirect buffers. What the
  draw and dispatch paths record beyond that (overlay copies, the grid patch, the exposure meter's fill, occlusion queries) goes to
  private buffers or is inside the island, as read in the source; a path not seen would be a race the pictures might not show. Textures
  are keyed by their storage's start and size (`guest_size`, at least 1 byte): two views of one storage at other offsets are caught only
  if their ranges meet. Bare pointers are bound to their pool's end, which is conservative (it over-reports conflicts).
- **CONCURRENT images**: free on NVIDIA as far as measured here; AMD may lose delta colour compression on render targets. A later stage
  should make only the resources the islands touch CONCURRENT, or transfer ownership.
- **More submits**: a part with islands goes out in 3+ submits and two semaphore operations per island, and is never batched
  (`RX_VK_BATCH`). On a CPU-bound PC that is pure cost (Kokiri on the 5070: about -2%).
- **Not verified**: validation layers with synchronization validation over a whole scene (see section 5), AMD and Intel (their
  compute-only families, and the present queue on the same family, `RX_VK_PRESENT_QUEUE=1` with `RX_VK_ASYNC_COMPUTE=1`: the queue is
  then shared or the family's second queue, by its count), Linux, long play, zone changes, the 3050 (run list sent).

## 8. The next stage (what the overlap needs)

1. **Completion per queue.** Today a part's timeline value, fence and slot are signalled by the graphics queue, which is why every
   island is joined at its part's end at the latest. A compute part should signal a compute-side value; the fences, `recording_wait`,
   the timeline the game's waits read (`vk_timeline_wait`, the readbacks) and the completion thread would take the max of both queues'
   values for a part (Rekarina reached the same: "the mirror bookkeeping is per submission and assumes one order").
2. **Footprints of the memory work**: the mirror syncs' and readback refreshes' pages, the texture uploads' images, and the
   write-back ranges are all known where they are recorded (vk_memory.cpp, vk_texture.cpp). With them a part's uploads need not wait for
   an island of an earlier part that does not touch them, and an island need not wait for its own part's uploads.
3. **Joins across parts**: a compute part's islands joined at the first later chunk (of any part) that conflicts with them, the
   write-backs of what they wrote moved to that point (never onto the compute queue: Rekarina's trap).
4. Cheap fixes on the way, from the check: clears as their targets' writes, counters, uniform updates and render conditions out of the
   opaque list (they are CPU-side or deferred), uniform updates allowed inside an island (the 1x1x1 chain of `755a777a` breaks into one
   island a dispatch today and hits the cap).
5. Alternatively, the game's own schedule: queue 3 (compute) placed by its events beside queue 6 (Rekarina's roadmap item 2), with the
   footprints as the check that the events cover the replay's own memory work.

## State at stop (2026-11-23 reboot)

- **Branch** `perf/async1` in `E:\OOT\HeyListen-wt\async1b` (the older `HeyListen-wt\async1` worktree is another stream's, perf/async-replay:
  left alone), rebased on main 1434a3edd. Commits: dbf2a8758 (stage 1: islands, chunks, footprints, check), 906bbb893 (stage 1b:
  RX_VK_ASYNC_STAMPS, RX_VK_ASYNC_MIN_DRAWS default 1, CPU-side ops inside islands, clears as target writes, one compute submit per wait
  point, RX_VK_ASYNC_ISLANDS), then this doc.
- **Done**: stage 1 built (#2), function-checked on the 5070 (Kokiri, Hyrule, Market, no errors, pictures right, validation layer clean),
  5070 Kokiri A/B -6.3%; PC 3050 Task 40: B slower everywhere (table in 6). Stage 1b built as **#3**: `E:\OOT\HeyListen\build\s5\bin\async1`
  = `E:\OOT\scratch-async1\bin3` (exe sha256 2c0fb2524d725a40..., dll 44638e74ffe17806...), unit tests pass (async_compute and the
  source-shape tests it touches).
- **Half done**: #3 has not run on the 5070 yet (its speed lease was queued ~7th when the reboot came). The 3050 runs #3 as the peer's
  Task 45 (list sent: A/B x3 at 100%/50% for kokiri-village, hyrule-walk, market-spin, plus stamp runs C = MIN_DRAWS=0 + STAMPS and
  S = STAMPS). Section 6b's STAGE1B_RESULTS is still to fill in from those results and the 5070's.
- **Next command after the reboot** (game-free first, then the 5070 A/B; never during an owner lease):
  `bash /e/OOT/scratch-async1/speed_runs.sh /e/OOT/scratch-async1/bin3 /e/OOT/scratch-async1/list4.txt > /e/OOT/scratch-async1/speed4.log 2>&1`
  (it asks for a priority-2 speed lease as owner async1, backs up slot c, runs the 2 stamp runs then A/B/C/D x3 on kokiri-village,
  restores slot c, releases). Then `python -I -B /e/OOT/scratch-async1/fps.py ac3-kv-A1 ...` and `grep "async stamps" build/s5/ac3-stamps-*/game_log.txt`.
- **Leases and scripts at stop**: none held. The speed ticket 20261123-115738-async1-speed-17db was released; the chain that waited
  for it (speed_runs.sh list4) was stopped before it ran anything; slot c holds its own binaries (checked with cmp). Scratch:
  `E:\OOT\scratch-async1` (bin1/2/3, lists, fps.py, speed_runs.sh, build_leased.sh, syn.sh, shots).

## 6b. PC 3050, build #3 (stage 1b), Task 45 (2026-11-23)

43 runs, 1440p, upscaler off, no error. B (RX_VK_ASYNC_COMPUTE=1, MIN_DRAWS=1) against A, fps from play+10 s, 3 rounds:

| Scene | 100% A | 100% B | 50% A | 50% B |
|---|---|---|---|---|
| Kokiri village | 52.3 | 50.3 | 69.0 | 65.5 |
| Hyrule Field | 42.9 | 41.0 | 60.0 | 56.4 |
| Market | 44.1 | 43.1 | 54.7 | 52.4 |

Stamps (C = MIN_DRAWS=0, S = the new defaults; within 1% of each other): the compute queue is busy 2.5-2.9 ms a frame, and only 0.02-0.08 ms of it runs beside graphics (under 3%). Islands start 12-17 ms (summed over the frame) after the work they wait for; the part's graphics 1.7-1.8 ms with 1.0-3.0 ms idle inside the part.

**Conclusion.** Inside a frame there is no work to overlap: each of the game's compute runs depends on the graphics just before it, and the graphics after it depend on it. Cheaper islands (stage 1b) do not change that. Async compute within the frame stays off and this stream stops here. The only overlap left is across independent work, such as frame N's compute beside frame N+1's first graphics (the shadow pass), which needs the frame-overlap refactor of the presentation chain (docs/research/pipe1-frame-overlap.md), not a queue switch.
