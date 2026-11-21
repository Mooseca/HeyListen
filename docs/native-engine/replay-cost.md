# What the frame's heavy replay is made of (stream R4, 2026-11-15, PC 3050, castle-move)

Tools (logging only, `RX_VK_PROF_FINE=1`, every 120 presents): `a frame (fine)` (draw sections summed over the recording threads, now with the
program lookup, the pipeline lookup and the texture slots resolved again), `a frame (fine, replay thread, wall)` (submissions, the dry pass,
the segments, the command buffers recorded whole), `replay_handle_early's steps` and `ops of the dry pass / segment workers / whole`.
`RX_VK_PRESYNC_STATS=1` now also times the dirty-page scan and the chunk diff.

## Where the replay thread's wall time goes (ms a frame, 2.2-3 big command buffers, ~2,300 draws)
Submissions with 300 draws or more: 14.3. Of the early path's steps: the mirror pre-sync before the dry pass 4.2, the dry loop 2.6, the replay
thread's own (last) segment 4.7, waits and submits 0.6; 18 small command buffers recorded whole here 2.4.
Summed over threads, per draw: textures 2.0 us (of it 0.9 resolved again: 1.0 us each), program lookup 1.2, user uniform buffers 0.55,
storage buffers 0.56, descriptor push 0.66, pipeline bind 0.55, vertex+index binds 0.45. Raw `vkCmd*` calls are a small part; most of the
rest is already cached per thread (texture slots, handle hits, banks, vertex sets, descriptor reuse), so there is no large repeated work
left to remove between draws. The program lookup is in vk_shader.cpp (shader stamp): not touched.

## The pre-sync: the chunk diff hashed every page again
On this PC (slow link) the mirror syncs' chunk diff is on, and the capture's copy is meant to make its hashes (TICK-060). The claimed copy
(`RX_VK_CAPTURE_CLAIM`, on by default since sprint 5) dropped them: 6 slots of ~1,340 a submit were hashed by the copy, the pre-sync hashed
the rest again, 3.7 ms of its 5.4 ms. `claim_run` now passes the hash arrays on (`RX_VK_CLAIM_HASH`, default on, =0 as before): 1,451 slots
hashed by the copy, 13 hashed again, the pre-sync 2.5 ms, the heavy submissions 14.3 -> 10.4 ms a frame.
Speed (interleaved, 3 against 3): castle-move 31.9 -> 36.1 fps, kokiri-idle 34.0 -> 37.3 fps.

## Tried, no gain over the spread (removed)
A segment's place on a fixed worker (TICK-052's affinity, on the early path), 16 handles a texture slot (resolved again 0.92 -> 0.64 a draw, time
the same), later early segments shorter (the first longest): 36.2 against 36.1 fps.

# R6: shortening the heavy replay R (2026-11-15 night, PC 3050, castle-move and kokiri-idle)

What a frame's replay is, from a job trace of castle-move (`HOS_JOBTRACE`, one 25 ms frame; C2's marks): the main thread's held submit at
6.0 ms, the Presentation Thread's own small submits 8.9-9.9, `present` entered at 13.0, and the heavy replay on the replay thread from
about 12.2 (the main thread's signal) to 23.2: mirror pre-sync (1.4), then for each of the three big command buffers its dry pass
(0.6-0.8), its segments handed out as the dry pass passes their ends, **its own last segment (2.8, 1.2 and 1.8 ms: 5.8 of the 11)**,
the in-order waits and submits, and between them the small command buffers recorded whole (1.1 and 0.4 ms); the GPU's tail follows
(23.2 to 25.4). The workers' segments were done before the replay thread's own segment was.

## What was tried, in the brief's order

1. **The small command buffers recorded by workers.** The 18 a frame are 157 of the frame's 1,760 draws (16 us a draw on the replay
   thread against 8 on a worker: cold caches), 2.8 ms. But they sit *behind* the big command buffer in the same submission (cb 0 the
   big one, cb 1-7 small; the next big one is the next submission, replayed under its own `replay_mu` hold), so no later dry pass of
   the same submission is there to hide them behind, and a job left over between submissions would break the queue order against the
   other queues' replays. Two variants measured: replaying a command buffer of under 96 draws once, in order, without its dry pass
   (the dry pass of a small one is ~0.1 ms: 'dry pass' 5.10 against 5.02 ms, nothing); and keeping their dry-pass products as pieces
   recorded by a worker as the next big command buffer's first job (the pieces were all flushed at the submission's end: 'recorded
   whole' 1.95 against 1.94 ms). Neither kept.
2. **The own segment.** R5's `RX_VK_PLAN_TAIL` (all segments end together) did not shorten R, and `RX_VK_PARALLEL=5` and `=6`
   (more recorders) did not change the own segment either (4.6-4.9 ms against 4.7-4.9, 4 rounds). What did: more, shorter segments
   than recorders (below).
3. **The heavy buffers' dry pass before the signal.** Not done, because the dry pass is not a pure walk. In stream order it also
   *writes guest memory*: the counters of the reports (963 a frame), the clears the dry pass makes on the CPU (depth-stencil: 32 a
   frame, 14 us each; colour: 43 at 2.7 us), and it reads the render conditions' operands (445 a frame) out of the memory those
   reports and the game write, and it marks the textures the draws write. A clear made before the signal lands before the game's own
   writes of the same range, which the stream orders after it; the marks reach the textures other work reads. Only the state walk
   (bind ops, draws: ~1.2 of the dry pass's 2.4 ms a frame) is pure, and running it twice (early, then again for the effects) costs
   what it saves. What would have to hold to run it early: the effects deferred to the signal and replayed from the recorded stream
   with the state of each op, which is the dry pass again.
4. **R5's `RX_VK_DRY_WANTED`** (the dry pass copies the state only at the points a boundary takes; cherry-picked d043efd8). Castle-move,
   fine profile, two rounds against `=0`: dry loop 2.77/2.93 -> 2.61/2.43 ms, own segment 5.20/4.98 -> 4.91/4.80 (fps 34.1/34.7 ->
   35.0/34.9, inside the spread). On, as R5 left it.

## Tried, no gain (removed)

- `RX_VK_SEG_PRESYNC`: the early path's mirror pre-sync as `RX_VK_PRESYNC_EARLY`'s job on a worker beside the dry pass, the segments
  held until it is done (par_active must stay off while the sync records its chunk hashes). The first big command buffer's pre-sync is
  1.3 ms and the dry pass 1.2: they overlapped, but the submit of the pre-sync's own recording (0.12 ms) and the held segments took
  the difference back: 'pre-sync + dry loop' 3.94 against 4.0 ms, castle-move fps 37.0 against 36.9 over 4 rounds.
- `RX_VK_SEG_SUBMIT`: each segment submitted, in order, by the thread that finishes it (the replay thread submitted all of them after
  its own segment, ten submits of 0.1 ms). With the finer segments: 37.3 against 37.6 fps (4 rounds), nothing.

## More, shorter segments (`RX_VK_FINE_SEGMENTS`, default on under 16 hardware threads)

A big command buffer was cut into one segment a recorder (4 workers and the replay thread: 5), balanced by recording time; the workers'
started as the dry pass passed their ends, the replay thread's own when the dry pass was over, and it was the last to finish. Cut into up
to ten segments of ~128 draws instead (`RX_VK_SEG_MAX=10 RX_VK_PARALLEL_ROUNDS=0 RX_VK_PARALLEL_SEG=128`), the last ones are short and a
recorder that is done takes the next (the pool's queue; the replay thread helps from it). The replay thread's own segment 4.7-5.0 ->
3.6 ms (3.1-3.2 with 12 segments of ~96), the waits for the segments 0.7 -> 1.4. Castle-move, 4 rounds interleaved: 36.1 -> 37.6 fps
(+4%), 1% low unchanged. 12 segments (96 or 64 draws) gave the same.

## Confirmed on main 38ab626c (PC 3050, plain runs, interleaved, new defaults against `RX_VK_FINE_SEGMENTS=0 RX_VK_DRY_WANTED=0`)

- castle-move, 3 rounds: 35.6 / 34.3 / 36.2 (mean 35.4) -> 37.6 / 37.9 / 37.7 (mean 37.7), +2.3 fps (+6%); 1% low 7.9-12.0 -> 18.2-19.8.
- kokiri-idle, 3 valid rounds (the first, after the rebuild, was a cold-cache throwaway): 37.4 / 39.8 / 36.9 -> 37.1 / 37.4 / 37.5 / 36.9:
  no gain, inside the spread.
- Picture: frame log (320x180, ~35 s each) of castle-move, kokiri-idle, a saved zone (Kakariko) and the Zora run (D4's movement
  script, the reporter's save): 0 one-frame luma dips in all of them, "uploaded by the later segment" lines 0, no made frames;
  flashes by framelog.py: castle 449 against 418, Zora 415 against 572 (small blocks, not dips), kokiri 0 against 4, zone 0 against 0.
  Shots of the four scenes by eye: right.
- Suites on the final HEAD: Windows 291 passed, 1 failed (nx2/test_nup_paths, known); Linux 307 passed, 2 failed (nx2/test_nup_read_name:
  no `zstandard` in WSL; the byte-compile check: git refuses the worktree path there).

## ORDER2 (the order thread off the critical path on 6-core CPUs)

Evidence: Market on an i5-10400F. The order thread runs 9.0 ms of a 24.3 ms frame; the presenter waits on it ~10.5 ms. ORDER1's counters
(PC 3050, RX_VK_PROF_FINE): locked passes 12.6 ms wall / 9.5 ms cpu, submissions 11.8 ms, dry pass 3.5, segments' recording and wait 6.6,
queue submits 14 a frame (0.57 ms), slot waits 30 a frame (0.13 ms); SEG_MERGE never engaged, FENCE_POLL changed nothing. So the driver
calls are the small part there; the dry pass (serial) and the wait for segments are the big ones. Step order re-aimed accordingly:
 A. segments: the in-order submit by whichever thread finishes (EARLY_GPU, exists), and the replay thread no longer joining the
    segments before it goes on (join deferred to the next point that needs the recordings: next begin_recording of the same state,
    present, wait) -- not started.
 B. dry pass: parallel / early / overlapped with the previous frame's segments -- not started.
 C. GPU-completion off the order thread (done, below), D. memory sync off the order thread, E. submission queue instead of
    sync_order_mu on the presenter, F. smaller own segment (more to the idle workers).

Invariants to keep (every step):
 1. Submission order: vkQueueSubmit2 calls keep the order the replay made them in (one queue; guarded by dev.present_mu); fences and the
    recordings timeline are signalled in that order. Anything handed to another thread is enqueued under dev.present_mu.
 2. The game's fence/semaphore semantics: a value's timeline signal, value_rec / whole_val / q_last marks are made at the submit that
    finishes the value, never earlier; a game fence is never answered before its recording is done.
 3. Readback ordering: invalidate (CPU readback) after a fence poll sees every write-back of the recording (RX_VK_READBACK_TICKET,
    memory_staged_apply before `completed()` is told): completion tracking must not make `submitted`/slot reuse visible earlier.
 4. Present ordering: a present follows the work it presents (sync_order_mu, dev.present_mu) and the swapchain's acquire/done fences.
 5. A slot is reused only after its submit retired AND its fence is reset; its command pools are reset only then.
 6. Event waits (RX_VK_WATCH_EVENT, perf/wait-044): sync_watch's kick is still sent by update_blocked / event_signal_queued; nothing here
    changes the watch. Integrate by merging perf/wait-044 after measuring; the two touch different lines.
 7. Blocking waits that are semantics, not bookkeeping (occ_sync / occ_go_on, replay_flush_upload) stay blocking.

### Step C (done, 6f2966edc): `RX_VK_COMPLETION_THREAD=1` (off)
engine/gpu/vk/completion_tracker.h: a thread waits for each submit's fence in queue order and resets it; the four submit sites (submit_recording,
presync early, submit_job, the merged segment submit) hand over under dev.present_mu; recording_wait reads an atomic (blocks on a
condition variable only when the GPU is still on the slot). Groups need no FenceGroup. Batch recordings keep the old path.
`RX_VK_COMPLETION_CHECK=1`: checks, at each retire, the recordings timeline reached the submit's value and the fence is reset (logs
and counts violations; counters logged every 7200 slot waits: found done / waited / ms). Tests: engine/tests/test_completion_tracker.py
(order, groups, stale generations, 48-slot ring, waiters, stop).
Expected gain: small on the PC 3050 (slot waits 0.13 ms + polls); it is the cheap, safe base.

### Hand-over
- Branch perf/order2 (from perf/order-044 3b8a320e7), worktree E:\OOT\HeyListen-wt\order2, tip 6f2966edc + this note. Not built yet (mkg.ps1 pending a lease), unit test passes (25 runs).
- To validate when machines are free: build; run Market and castle-move with RX_VK_COMPLETION_THREAD=1 RX_VK_COMPLETION_CHECK=1: 0 violations, pictures as default, no stalls; then A/B with RX_VK_PROF_FINE.
- Next: step A (defer the segment join), measured against ORDER1's counters.
