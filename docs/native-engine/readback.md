# Readbacks, the replay's start and the frame's loop (stream R2, 2026-11-14, main PC)

Question (stream C1): 81% of the 30.7 ms frame on the PC 3050 is a thread waiting inside the renderer, the present on the replay and the
game's CPU reads of GPU results (`invalidate`) on the replay and the GPU's write-back. Which reads wait, why, and can they be
answered without waiting with the picture right; why does the replay start late in the frame. Everything below is measured on the main
PC (Ryzen 7 7800X3D, RTX 5070, castle-move, 1280x720, main 349e5685 plus this stream's logging), the machine otherwise free for the
speed rows, the frame rate a run of 110 s cut at 66 s as always. The PC 3050 was not used.

## Tools built (logging only, default off)

- `RX_VK_RB_PROF=1` (`vk_replay.cpp`, `RbScope`): every `invalidate` timed by phase (the ticket's wait for the replay section in
  progress, the catch-up, the wait for the write-back's recording split into the flush's late-fix wait / the queue's lock / the
  sending / the recordings' semaphore, the GPU timeline, the strict wait, the texture catch-up), by thread, by range and by call site
  (the exe's frames above the renderer, resolved against the link map), a line every 300 presents.
- `HOS_RB_LR_LOG=1` (`host/nvn_native.c`): the CPU's reads of GPU results by guest return address, size and thread.
- `RX_VK_TL=<present>` or `RX_VK_TL_S=<seconds after the first present>`: a timeline of 3 frames of the renderer's threads (submits,
  replays and their stops at event waits, the CPU's event signals, presents and their drains, fence waits, readbacks with the writer's
  value, recordings sent and flushed, the late fixes), in the log as `vk: tl ...` lines (plain text).

## What a frame reads (castle-move, 89-97 fps)

33-34 `invalidate` calls a frame, 19.4 of them on ranges with write-backs, 6-10 of those pending (the writer not done). The time
they wait, summed over the threads that read (several wait at once, so this is not the chain's loss):

| | ms a frame |
|---|---:|
| all readbacks | 6.7-8.0 |
| the ticket (the replay section in progress when the fence was polled) | 1.2-1.4 |
| the write-back's recording | 5.3-6.7 |
| of it: the flush's wait for the pending late fix (`late_fix_wait_unlocked`, the GPU timeline) | 5.1-6.4 |
| of it: the queue's lock, the sending, the recordings' semaphore | 0.1 + 0.0 + 0.1 |
| the GPU timeline wait (`wait_value`), the strict wait, textures | 0.0 |

By thread: ModuleSystemWorker1 2.25, 2 1.82, 3 0.85, 4 0.47, 5 0.33, the main thread 2.28. By range, one call a frame each:
0x113c88b000 +0x1040 (the light meter's buffer, 2.0 ms), a 0x40 range (1.97), the two 0x2000 ranges that alternate frame by frame
(0.97 and 1.0); the rest (0x3980 x2, 0x8b040, 0x9b040, 0x44b040, 0x1b580) wait 0.01-0.05 ms. By caller (guest return address):
the meter's 0x1040 x3 and 0xc0 from the ring helper `f_80357060` (7 callers), the 0x2000 from `f_8007c120` and `f_8034f440`, the
0x40 from `f_80354060` (many addresses in a row, one wait for all), the big ranges from `f_80362ff0`, 0x1b580 from `f_80364080`,
0x3980 from `f_80365f00` and `f_800998a0`. Only 0.2-0.6 of the 33 calls a frame have the newest submission as their writer: the
game reads what the **previous frame's** heavy submission wrote (value of the queue's 4th submit), after polling that submission's
fence (answered "done" early from the recording, see `direct-emission.md` section 12). So Longshot's `RX_VK_READBACK_LATE=newest`
does not apply here (0.2-0.6 calls a frame match it); its by-size rule would name the 0x2000 and 0x40 ranges.

What the wait is for: the GPU's completion of the previous frame's heavy submission. The readbacks call `wait_recorded`, which flushes
the held recordings first (`queue_flush_for`), and the flush's first step waits for the pending late fix, the timeline value of a
capture's late page, which is that same submission's write-back. The recordings' semaphore itself is signalled before the wait begins
or within 0.1 ms. (The first piece of the submission is what `value_rec` keeps, so on this driver, where `RX_VK_READBACK_STRICT` is
off, that wait is the only one that makes a readback see the whole submission's write-back.)

## The frame's loop, from the timeline (`RX_VK_TL_S`)

One frame, in order:
1. The game's CPU phase (main thread, module workers, executors) until the main thread signals the CPU event that the heavy queue's
   first command buffer waits for (0x1006e38000 / 0x1006e38004, alternating by frame).
2. Until then the renderer has only the Presentation Thread's four small submits (each stops at a GPU-event wait, 0.05-0.1 ms of
   replay each) and the main thread's two held submits (capture 0.6 ms, replay 0.1-0.2 ms each). The heavy submission stops at the CPU
   event: **this is why the replay is idle for the first ~10 ms of the frame on the 3050: it has nothing it may run**. The game
   submits the work before its data is final and holds the GPU with an event the CPU sets when it is.
3. The signal; the order thread (`sync_watch`, `Sleep(1)`) or the Presentation Thread's present finds it 0.5-1 ms later (the order
   thread polls; `RX_VK_WATCH_KICK=1` wakes it at the signal), and the heavy submission replays: 4-9 ms here, in pieces that stop at
   GPU-event waits; the present, called at about the same time, waits for the section's lock.
4. The present returns when the drain is done; the next frame's CPU phase begins.
5. In the next CPU phase, about 3-4 ms in, the main thread and the module workers read the previous frame's results (above) and wait
   for the GPU to be done with that heavy submission, 0 to 5 ms (1.4 ms in the frame traced), then go on to signal the event.

The loop is therefore: replay end of frame N-1 -> GPU done with it -> readbacks of frame N -> event signal of frame N -> replay of frame N.
The GPU's own work is 2.6-2.9 ms a frame, with 9 ms of gaps between recordings (the log): the wait looks like the replay handing
the GPU its last recordings late rather than the GPU's speed (an inference: see "Not verified").

## What was tried, speed and picture

Speed: castle-move, the whole machine held (`slot.sh all`), the same binary with only environment switches differing, arms
interleaved (the order reversed each round), 110 s a run cut at 66 s, fps of the run. Picture: `RX_VK_FRAMELOG` for 25 s of each run
(2,400-2,700 frames at 320x180), `scripts/framelog.py` for its flash events, and the mean luma of every frame (an exposure that
pulses or is wrong moves it; `RX_VK_EXPOSURE_LOG=2` was logged too, but the word it names stays 1.0 in this scene, so it says nothing
here). Shots every 600 presents were kept in `build/s5/r2-fl-*-shots/` (local).

| arm | fps, each run | mean | against the baseline | picture (luma mean, range, pulses, framelog flash events) |
|---|---|---:|---:|---|
| baseline (all switches off) | 97.6, 97.7, 97.0, 97.8, 97.2, 98.1 | 97.6 | | 40.6, 26.8-53.5, 0, 4 one-block events |
| `RX_VK_WATCH_KICK=1` | 104.0, 104.1, 105.0, 104.0, 104.1 | 104.2 | **+6.8%** | 41.0, 27.9-54.6, 0, 0 events: right |
| `RX_VK_READBACK_LATE=2000,40` | 98.3, 98.0, 98.2 | 98.2 | +0.6% (inside the spread) | 40.6, 28.7-53.0, 0, 0 events: right |
| `WATCH_KICK=1` + `READBACK_LATE=2000,40` | 105.3, 105.1, 104.4 | 104.9 | +7.5%, +0.7 over the kick alone | not run (each alone is right) |
| `RX_VK_NO_READBACK_WAIT=1` (the bound) | 115.5, 112.9 | 114.2 | +17% | 42.2, 27.8-67.7, **24 pulses**, frame-to-frame step up to 11 (0.5 in the baseline): wrong |
| `RX_VK_POOL_MIRROR=1` (step 3) | 88.8, 89.0 (against 96.6, 97.6 in the same screen) | 88.9 | -8.5% | not run |
| `WATCH_KICK=1` + `POOL_MIRROR=1` | 93.5, 94.6 | 94.0 | -3.2% (the kick still adds +5.7% on the mirrors) | not run |
| (built, taken out) `RX_VK_WAIT_REC_SENT=1`: no flush before the wait for a recording already sent | 109.6 (one run) | | +12% | **177.7 mean, 245.9 max: burnt out to white**: wrong |

Of the 12 runs of the first screen, two did not leave the title screen (0 frames measured, the game's present count stops at 39.4 s
after the first present, 360 fps of a 50-draw frame): one of the `NO_READBACK_WAIT` runs and one of the `WATCH_KICK` runs. None of the
9 runs of the second screen, none of the baseline or `READBACK_LATE` runs (9 and 3). The scripted input is the first suspect (the same
instant in both); the renderer's change is not excluded: not established. Said plainly: too few runs to rule out that `WATCH_KICK`
makes the stall more likely.

### What each result says

- **The readbacks wait for the GPU's completion of the previous frame's heavy submission, through the flush's late-fix wait.** 5.1-6.4
  of the 5.3-6.7 ms a frame that the recording's wait costs is `late_fix_wait_unlocked` in `queue_flush_for`, called by `wait_recorded`
  before it waits on the recordings' semaphore. The late page is always the same one, 0x100d6c8000 (pool 0x100c000000 +0x16c8000, not a
  readback page): the page of the GPU event words, which the heavy submission's last event signal writes back (log line "late page
  deferred: ... write-back 2415, submission 2417": the write-back of the previous frame's heavy submission against the capture of the
  next frame's held submit; 598 fixes in 600 presents). It is that wait that holds the frame's other recordings (11.5 command buffers a
  frame held until the fix thread sends them), and it is that wait the readbacks join.
- **Skipping that wait (`WAIT_REC_SENT`) is fast and wrong.** The recordings' semaphore a readback then waits on is the one of the FIRST
  recording the writing submission went into (`value_rec` keeps the first), signalled long before the submission's write-back of the
  meter has landed; on this driver `RX_VK_READBACK_STRICT` is off, so nothing else waits for the whole submission. The flush's late-fix
  wait was the only thing that did, by being the same GPU completion. The meter then read stale sums: the exposure went to white (mean
  luma 177). That wait must not be removed without replacing it by one on the timeline value of the range's write-back
  (`RX_VK_READBACK_STRICT=1` does that, and its own wait flushes through the same late fix, so it costs the same).
- **The answer-late rules do not gain here.** `newest` names 0.2-0.6 of the 33 calls a frame. The by-size rule for the two rings that
  are not the meter (0x2000, 0x40: 3.9 ms of the 8 summed) gives +0.6%: the meter's ranges (0x1040 x3, 0xc0), read by the same threads
  at the same moment, still wait for the same GPU completion, and the threads wait together, so removing some of the waits shortens
  nothing. Only removing all (`NO_READBACK_WAIT`, +17%) moves the frame, and it breaks the meter.
- **Reading the previous frame's value is not what the game is built for.** The game reads, in frame N, what frame N-1's heavy
  submission wrote, after polling that submission's fence; on the console the poll can say "not done" and the game then skips the read
  (its own protocol). The meter is read and reset (0 written), and the GPU adds the next frame's sums into the reset value: a skipped or
  a stale read doubles the next measure (78, 163, 254 in sprint 5's log) and the exposure moves. That is also what the 24 pulses of
  `NO_READBACK_WAIT` are. A rule for the meter's ranges has to be exact.
- **The replay's late start is the game's own wait, not the renderer's.** The heavy queue's first command buffer waits for a CPU event
  (0x1006e38000 / 0x1006e38004), which the main thread signals at the end of its CPU phase. Until then the replay has the Presentation
  Thread's four small submits (0.05-0.1 ms each, stopped at GPU-event waits) and the main thread's two held submits, and nothing else it
  may run: the idle first ~10 ms of the 3050's frame (a 10-14 ms CPU phase there; 5-8 ms on this PC). After the signal the order thread
  (`sync_watch`, `Sleep(1)` with a 1 ms timer) finds it 0.5-1 ms later (0.56, 0.95, 0.64 ms in three traced frames);
  **`RX_VK_WATCH_KICK=1` wakes it at the signal and is worth +6.8% here**, picture right, because that 0.5-1 ms is on the frame's loop
  (signal, replay, present, next frame's CPU phase, signal). The replay stays serial: the replay of frame N cannot overlap the CPU phase
  of frame N+1, because frame N+1's readbacks wait for frame N's heavy GPU work, and its event signal, which the next replay waits for,
  comes after them.

Step 3 (the replay's own work, 4.6 ms on the 3050: page hashing, mirror sync, the GPU-write diff): `RX_VK_POOL_MIRROR=1` makes the
replay do more, not less, on this PC (a staging copy per pool fill and write-back: -8.5%, 2 runs against 2); it saves memory (its
purpose), not replay time, and none of the three costs went away. The per-phase cost with it on was not measured.

## Switches built (default off, except the kick: see the second session)

| switch | what it does | state |
|---|---|---|
| `RX_VK_WATCH_KICK` (**on by default since the second session**; `=0` off) | the CPU's event signal sets an event the order thread waits on (1 ms timeout), so the stopped queue's replay starts at the signal | +7.1% castle-move (10 against 10), +7.7% kokiri-idle (3 against 3), picture right; 23 runs from the title, no stall |
| `RX_VK_READBACK_LATE=<rules>` | Longshot's #238 (`newest`, a hex size), plus `-<hex size>` to never; a ranged readback is read without its wait | no gain here; picture right for `2000,40`; the meter must not be named |
| `RX_VK_RB_PROF=1`, `RX_VK_TL=<present>` / `RX_VK_TL_S=<s>` (now with the GPU's timestamps), `HOS_RB_LR_LOG=1` | the measurements above | logging only |

## Not verified

- One scene (castle-move), one PC. Kokiri-idle and hyrule-walk were not run; the 3050 was not used (its numbers, 81% in waits, are C1's,
  not reproduced here: on this PC the readbacks wait 1.4-2.0 ms a frame on the chain, not 9 ms).
- The two runs that stayed on the title screen (above): not reproduced in the second session (see there); their cause is not known.
- `WATCH_KICK`'s picture: second session, three scenes by eye and 12 frame-log captures (17,700 kick frames); two exposure pulses in the kick
  arm, one in the baseline: not shown to differ, not shown equal. The PC 3050 was still not used.
- The GPU completion's own time: the log's GPU time is 2.6-2.9 ms a frame and its "GPU tail" 0.4-0.7 ms, but a recording submitted at
  4.5 ms of the traced frame was not done on the timeline before 9.9 ms. Where the other ~3 ms go (the segments of the heavy command
  buffer are recorded together by the parallel replay and reach the queue together; the queue submit's own time was not logged until
  the last build) is the open question and the one worth the next stream's time: the heavy submission's GPU work is not pipelined with
  its replay.

## Second session (2026-11-14 evening, main PC): the switch's safety, and what the GPU does between the pieces

### RX_VK_WATCH_KICK: the title-screen stalls, the three scenes, the speed

- **Stall test.** 10 baseline and 10 `RX_VK_WATCH_KICK=1` runs of castle-move, interleaved, in the whole-machine lock, from the title
  (scratch `stall.sh`): **20 of 20 left the title screen** (4,205-4,310 frames measured baseline, 4,507-4,604 kick). Baseline 96.2-98.1 fps,
  mean 97.5; kick 103.9-105.2, mean 104.5: **+7.1%**, every kick run above every baseline run. With the 10 runs of this test, the three
  validation runs, 7 frame-log runs and 3 kokiri-idle runs, 23 runs had the kick on and none stalled (the first session: 1 of ~6 with the kick stalled,
  1 of ~3 with `NO_READBACK_WAIT`). The stalls were not reproduced with the kick or without it; the first suspect stays the scripted menu
  input, known to be missed now and then. The kick's code has no path that can wait for something that never comes (the order thread waits
  on the event with a 1 ms timeout, as it slept 1 ms before). Said plainly: 23 clean runs rule out a stall rate above ~12%, not a rare one.
- **Validation, the three scenes** (`valid.sh`, kick on): kokiri-idle, castle-move, hyrule-walk all ran (4,358 / 4,541 / 4,374 frames), no
  crash line, game-speed ratio 59.99 / 60.06 / 60.06; the last shots of each scene looked at by eye (the Kokiri lake at night, a field at night
  with Link and Navi, a night road with ruins: not black, not white, not tinted, geometry and HUD whole).
- **Picture by the frame log** (`RX_VK_FRAMELOG` 25 s, mean luma of every frame, scratch `lumastat.py` / `steps.py`): kokiri-idle base 50.67,
  kick 50.42, no frame-to-frame step above 0.12; hyrule-walk base 47.0, 46.8, 48.0, 47.0 and kick 47.2, 46.0, 46.9, 47.3; castle-move base 41.3,
  41.4 and kick 40.8, 41.7 (session 1: base 40.6, kick 41.0). One kind of event shows in both arms: the picture goes 8-15% brighter for
  15-16 frames and comes back (the exposure pulse of the `RX_VK_READBACK_STRICT` note, a doubled meter sum): base 1 in 16,600 frames
  (hyrule-walk), kick 2 in 17,700 frames (one hyrule-walk, one castle-move). The first session's baseline has them too (4 one-block events).
  The kick does not make it obviously more frequent (2 against 1), and it is not new; it is also not proven not to.
- **Speed**: castle-move above (10 against 10, +7.1%). Kokiri-idle, whole machine, 3 against 3 interleaved: base 93.8, 94.8, 94.5 (mean 94.4),
  kick 101.5, 101.9, 101.6 (mean 101.7): **+7.7%**, no stall. **The kick is now on by default** (`RX_VK_WATCH_KICK=0` turns it off): the
  three scenes ran clean and the picture is right by eye and by luma; it is its own commit, easy to take back if the owner's play shows
  anything.

### What the GPU does between the pieces of the heavy submission (`RX_VK_TL_S`, now with the GPU's own timestamps)

`RX_VK_TL` / `RX_VK_TL_S` now also print the GPU's side: every recording's upload and command buffer start and end on the host clock
(`gpu-up+/-`, `gpu-cmd+/-` lines; the timestamps are read when the recording's slot comes round, so they are printed 14 presents after the
window opens; `VK_EXT_calibrated_timestamps`, enabled only with the timeline on). The queue's other submits (present's blit, sparse binds,
texture and memory readback submits) have `blit-submit` / `bind-sparse` / `tex-rb-submit` / `mem-submit` events: in a frame's window only
the present's blit is submitted besides the recordings (no bind, no readback submit). Scratch `gpulag.py` tables each recording's queue
submit, GPU start and end. Castle-move, 3 frames, kick off, the heavy submission (4 pieces, cut where a queue stops at an event wait):

| piece | queue submit (ms) | GPU start after the submit (ms) | GPU idle before it (ms) | GPU time (ms) |
|---|---:|---:|---:|---:|
| 1 | 0.57 | 0.02 | | 0.24 |
| 2 | 1.77 | 0.02 | | 1.14 |
| 3 | 2.98 | **0.94** | 1.0 | 0.55 |
| 4 (the last: the write-backs, the timeline value) | 4.87 | **4.56** | 4.96 | 0.20 |

The same in every frame and every run (piece 3 starts 0.78-1.08 ms late, piece 4 4.0-4.7 ms late). The pieces' queue submits take 15-40 us
(`rec-qsubmit`) and the GPU is idle (the GPU time of the whole heavy submission is 2.1 ms) while the piece sits in the queue. So the **3 ms
between the submit of the heavy recording and its completion is neither GPU work nor the submit's cost: the GPU starts the last piece 4.5 ms
after it was submitted, and the readbacks of the next frame's CPU phase wait for that**: the late fix's wait ends with the end of piece 4 (the
fix thread's `fix-wait-` 0.05 ms after `gpu-cmd-`). Once the GPU starts piece 4, everything queued behind it (the Presentation Thread's six
small recordings, a dozen command buffers) runs back to back in 0.3 ms. The two late starts (piece 3's and 4's) are 4.5-5.8 ms apart, ~5.2
on average, and fall at the same phase of every frame.

What did not change it (each a timeline run of castle-move, the same delays): a `vkGetFenceStatus`, a `vkGetSemaphoreCounterValue` or an
empty `vkQueueSubmit2` after each submit (to make the driver hand the work over: `RX_VK_SUBMIT_KICK`, built and taken out), `RX_VK_CHUNK=0`,
`RX_VK_POOL_MIRROR=1`, `RX_VK_PRESENT_QUEUE=0`, `RX_VK_BATCH=1` (with and without `RX_VK_BATCH_IDLE=0`), and holding the third and later
non-signalling pieces to send them with the signalling one in one submission (`RX_VK_TAIL_HOLD`, built and taken out: piece 3 then started
at once when it went out alone 2.2 ms after piece 2's end; piece 4, submitted 0.2 ms after piece 3's end, still started 4.9 ms later; fps
95.7 against 97). What fits all of it: **a submission that reaches the queue soon (under ~0.5 ms) after the previous one's completion waits
~1 ms (after piece 2) or ~5 ms (after piece 3) before the GPU starts it, with nothing running; one that comes 0.9 ms or more after a
completion starts at once.** The cause is not found (the queue's scheduling after a completion in the driver or the OS; not PCIe, which is
Gen5 x16, and not a pool or a write-back cost: pool mirrors, chunking, batching and the presents' own queue change nothing). It is the one
lever left under the frame's loop: with piece 4 started when it is submitted, the GPU would be done at ~5.4 ms of the frame instead of 9.6,
before the readbacks come (7.8 ms), and the late fix's wait (1.9 ms in that frame) would be gone. Not built: nothing tried moves it.

One more try, `RX_VK_PIECE_GAP_US=1000` (built and taken out): a piece of a submission is sent only 1 ms after the GPU's end of the
previous piece (its bottom-of-pipe timestamp against the calibrated device clock now). Piece 3 then started 0.02-0.09 ms after its submit
(the rule holds for it), but piece 4, submitted 1.2-1.3 ms after piece 3's end, still started 4.28-4.4 ms later, and the frame rate fell
(91.5 against 97). So the piece-4 delay is not about its arrival after the previous completion either; nothing at that moment on the
CPU side of the timeline (all the threads are in waits or quiet) explains it.

### The late-fix dependency (item 3): real

The readbacks of frame N+1 do not wait for the late page in order to read their own range; they wait for the GPU's completion of the
write-back of the previous heavy submission, and their range depends on that. (1) The writer value of the meter's ranges (`rb-val`) is the
heavy submission's own, `value_rec` maps it to the FIRST recording of that submission (an earlier one, long done), so the recordings'
semaphore alone lets the read pass: five readbacks of the same writer made 4.9 ms into the frame, before any late fix existed, passed in 4
us each and read what the GPU had not written yet (ranges of other uses, so the picture is not what they decide). (2) The late fix that
holds the later ones has the same value as that writer: the capture of the next frame's first held submit finds the heavy submission's last
write-back still pending (`fix-pending`, the value the readbacks wait on). So there is no readback that waits for the late page and does not
depend on it here; skipping the flush's wait (`RX_VK_WAIT_REC_SENT`, session 1) burned the picture out for that reason. What would shorten the
wait is the GPU completing sooner (above), or the meter being written back by an earlier piece than the last (registered per submission, at
its end today; not changed).

## Hand-over (second session)

- Branch `stream/r2-readback`, worktree `E:\OOT\HeyListen-wt\r2-readback`. New tooling, all logging: the GPU side of `RX_VK_TL` /
  `RX_VK_TL_S` (`tl_gpu_dump`, `TlGpuRec` in `vk_replay.cpp`; `VK_EXT_calibrated_timestamps` is enabled only when the timeline is asked for),
  `vk_tl_note` (events from `vk_texture.cpp` / `vk_memory.cpp`). Scratch scripts, not in the repository, under
  `E:\OOT\scratch-from-c\r2b`: `tlrun.sh` (one castle-move run with the timeline at 70 s, merged and tabled), `tlmerge.py`, `gpulag.py`
  (each recording's submit, GPU start and end), `stall.sh` (interleaved arms with frames and fps), `flmany.sh` + `steps.py` (frame-log runs,
  luma steps), the older `lumastat.py` / `tlshow.py` under `r2`.
- Session 1's tools (RX_VK_RB_PROF, HOS_RB_LR_LOG, RX_VK_TL) are described under "Tools built".
- Built and taken out (the numbers are in "What the GPU does between the pieces"): `RX_VK_SUBMIT_KICK`, `RX_VK_TAIL_HOLD`,
  `RX_VK_PIECE_GAP_US`.
- Next, in order: (1) **find what delays the GPU's start of the heavy submission's last piece by 4.3-4.7 ms** (and the third by ~1 ms):
  piece 4 is submitted at ~5 ms of the frame and starts at ~9.5, with the GPU idle, whatever the submit path (batched, kicked, alone, with a
  gap, on the presents' own queue or not). Ideas not tried: the same timeline with the game's window in fullscreen (`fullscreen=1`: DWM is out
  of the queue's scheduling), with `HOS_` / driver settings that change the GPU's scheduling (hardware-accelerated GPU scheduling), a timeline
  on the PC 3050 (it is the machine where the readbacks cost 9 ms) to see if the late start is the same there, a Vulkan `VK_NV_low_latency2`
  off/on A/B, and a trace of the process with ETW GPU events (GPUView) for one frame: it shows what the queue's hardware context waits on.
  If the late start goes away, the late fix's wait (1.4-1.9 ms a frame) goes with it, and `NO_READBACK_WAIT`'s +17% is the bound of the gain.
  (2) The exposure pulse (15-16 frames, +8-15%) exists with and without the kick at about 1 in 10,000 frames; `RX_VK_READBACK_STRICT=1`
  is its known cure (18% on this driver): a cheaper exact rule is wanted. (3) The PC 3050 was not used by either session.

## Third session (2026-11-14 night, main PC): what the late pieces wait on

Question: the heavy submission is cut into 4 pieces at event-wait stops; the GPU starts piece 3 ~1 ms and piece 4 ~4.5 ms after the piece was
submitted, with the GPU idle by our own timestamps, and every readback waits for piece 4. What does a piece wait on, and why is the wait satisfied
so late? Everything below is castle-move on the main PC (RTX 5070, driver 617.42, 1280x720 window, `RX_VK_WATCH_KICK` on), the whole machine held,
timelines by `RX_VK_TL_S=70` (about 104 fps with the probes on).

### 1. At the API level a piece waits on nothing

`submit_recording` (every piece, every held or batched submit) has **no wait semaphores and no events**: each submit signals the two timelines
and a fence and that is all; no `VkEvent`, no `vkCmdWaitEvents`, no `vkSignalSemaphore` anywhere in the renderer. The only wait on the queue is
the present's blit (the acquired image's semaphore; `RX_VK_ACQUIRE_FENCE=1` takes it off the queue). The game's GPU events are host-side stops of
the replay, not GPU waits. The event a stopped piece waits for is a guest event the replay polls (the order thread, and `sync_watch`); the
heavy queue's first piece waits for the CPU event the main thread signals (`cpu-signal` in the timeline: value 0 resets, value 1 signals,
alternating between two event words). Those stops explain when a piece is *recorded and submitted*, which the timeline shows (piece 4 is submitted
0.5 ms after the GPU ended piece 3: the replay resumes right after the GPU's write of the event word). They do not explain a GPU that is idle after
the submit.

### 2. The late start is the graphics queue holding new work: probes (`RX_VK_TL_PROBE`, logging only)

Built: `RX_VK_TL_PROBE=1` (needs `RX_VK_TL` / `RX_VK_TL_S`): before each recording's queue submit a one-timestamp command buffer is submitted on the
replay's queue (probe 1); `=2` also on a second queue of the same family (probe 3); with `RX_VK_PRESENT_QUEUE=1` also on the compute queue right
after the piece (probe 2); `=3` adds a monitor thread that submits a probe on the replay's queue every 0.2 ms while the window is open; `RX_VK_PROBE_JOB=<n>`
(+ `_EVERY`) adds synthetic jobs of n fills of a 256 MB buffer; `RX_VK_TL_FRAMES=<n>` lengthens the window; `RX_VK_QUEUE_PRIO` sets the queue priority.
Results (scratch `probes.py`, `monitor.py`, `holes.py` under `E:\OOT\scratch-from-c\r2c`):

- **A trivial probe submitted just before piece 4 starts on the GPU at the same instant as piece 4** (+4.4 to +5.0 ms after the submit, to within
  0.01 ms), and a probe before piece 3 the same at +0.9-1.1 ms. So the delay is not the piece's content, size, signals or fence: it is the queue.
- **The compute-family queue is not held**: its probe, submitted right after the piece, runs 0.013-0.03 ms after the submit in every frame, while
  the graphics queue sits in its hole. The second queue of the graphics family (probe 3) is held too but differently (+0.3 to +2.1 ms).
- **The monitor (a probe every 0.2 ms) shows the graphics queue gated in two windows a frame**: after the end of piece 2 (a ~1.1 ms job) the queue
  runs nothing for **1.1-1.3 ms**, then runs everything queued back to back (2-3 us apart); after the end of piece 3 (0.55 ms) it runs the probes
  already queued and then runs nothing for **4.9-5.05 ms**; probes and pieces submitted during that time all start together when it ends. The lengths
  are the same in every frame (1.13-1.16 and 4.99-5.05 within a run; 4.5-5.4 on other runs) and are not related to anything the CPU does in
  the window (no event of any thread falls at the end of a hole). Outside those two windows the queue answers in 6-20 us.
- The windows and lengths are **the same** with: fullscreen (a 2560x1440 swapchain, `fullscreen=1` in the slot's options), `RX_VK_IMMEDIATE=1`
  (immediate present mode), `RX_VK_ACQUIRE_FENCE=1`, `HOS_NO_PRIORITIES=1`, `RX_VK_QUEUE_PRIO=0`, `RX_VK_PRESENT_QUEUE=1`, no implicit Vulkan layers
  (`VK_LOADER_LAYERS_DISABLE=~implicit~`: the RivaTuner layer, Steam's and Epic's overlays were loaded before), `RX_VK_NO_WRITEBACK=1` (piece 4's GPU
  time falls from 0.20 to 0.03 ms: the write-back copies are nearly all it holds; the holes stay), `RX_VK_NO_HOST_IMPORT=1`, and with a **60 fps cap**
  (`HL_FPS_LIMIT=60`: CPU not saturated; 1.13-1.16 and 4.9-5.04 ms again). Earlier sessions: `RX_VK_CHUNK=0`, `RX_VK_POOL_MIRROR=1`,
  `RX_VK_BATCH`, a gap before the submit, holding pieces, empty submits and fence/semaphore queries after each submit.
- **It is not a property of the GPU after any long job**: synthetic 1.2-1.4 ms fill jobs in the same process, at the title screen (light load), are
  followed by no hole. At the title screen no hole appears at all (probes answer in 10-20 us); the holes belong to the game's real heavy
  submission (about 160 render passes, 1,900 draws and 140 dispatches a frame, per `RX_VK_PASS_TIMING=1`).
- The GPU clock is steady (P0, 2.89 GHz at 50 ms sampling); no other process uses the 3D engine more than 1% (`\GPU Engine` counters), yet the
  counter gives HeyListen's 3D engine **82% busy** against ~25% of real work by our timestamps: Windows counts the holes as busy, so the engine
  (or its context) is occupied by something that is not our timestamped work.
- Not admin, so no ETW GPU trace: the next step is outside what an agent here can do.

### 3. What this means for the frame

The loop is: the main thread's event signal -> the replay (pieces 1-4 submitted over ~5 ms) -> the GPU's holes -> piece 4's end at ~9.7 ms ->
readbacks of the next CPU phase (which arrive at ~7.8 ms and wait ~2 ms) -> the next signal. Without the 5 ms hole after piece 3 the GPU would be
done at ~5.4 ms, the readbacks would not wait, and `RX_VK_NO_READBACK_WAIT`'s +17% is the bound of the gain. Piece 4 is almost only the write-back
copies (0.17 of its 0.20 ms), which are what the readbacks wait for.

Not built, and why: (a) the write-back copies of piece 4 on the compute-family queue (it is not held): the copies depend on the draws of pieces 1-3, the
write-back machinery (`vk_memory.cpp`: captures, mirror syncs, late pages, the late fix) assumes one queue and `dev.present_mu`, and the compute queue
for presents is off by default since the device lost of issue 1161; too large for what is verified; (b) writing back each piece's ranges at the end of
that piece and telling the readbacks which piece wrote their range (so the meter, written by an earlier piece, would not wait for piece 4): needs per-piece
write registration in `vk_memory.cpp` and a rule that no later piece rewrites the range; not started.

### Tools an owner could run (not installed here, not downloaded)

`wpr -start GPU -start CPU` (built in, needs an elevated shell) around a castle-move run, then the Windows Performance Analyzer or GPUView on the
`.etl`: it shows what the 3D queue's hardware context waits on in those two windows. Also Nsight Systems (a GPU trace of the queue), and the same run with
hardware-accelerated GPU scheduling toggled in Settings (the owner's setting; `HwSchMode` is not set in the registry here) and, if one exists, another
NVIDIA driver.

## Hand-over (third session)

- Branch `stream/r2-readback`; new logging only: `RX_VK_TL_PROBE`, `RX_VK_PROBE_JOB`, `RX_VK_TL_FRAMES`, `RX_VK_QUEUE_PRIO` (diagnostics, default off, no behaviour
  change when off). Scratch under `E:\OOT\scratch-from-c\r2c`: `tlrun.sh <slot> <name> ENV=..` (one run with the timeline, merged), `probes.py`, `monitor.py`,
  `holes.py` (idle-while-queued windows), `late.py`, `gpu_sample.ps1` (`\GPU Engine` by process), `smi.ps1`.
- The open question is exactly one: **what holds the graphics queue for ~1.1 ms after the end of piece 2 and ~5.0 ms after the end of piece 3 of the
  heavy submission**, with new submits (any content) held, the compute queue free, and no CPU or API cause found. A reproduction outside the game that submits
  the same kinds of work (passes, dispatches, barriers) and watches probes would show whether it is the driver; removing one kind of work at a time in the replay
  (render passes, dispatches, mesh draws, the 2560x1440 targets) would show which one starts the hold.
