<!-- Copyright (C) 2026 Sacrappy -->
# PIPE2: the stages' slack and the replay on an order thread (23 Nov 2026 -)

Branch `perf/pipe2` from origin/main 4b599eb04 (PIPE1 merged, `RX_VK_TOUCH_FAST` on). Worktree `E:\OOT\HeyListen-wt\pipe2`. Design:
`pipe1-frame-overlap.md` section 3 (stages 0-3 with their gates). Main PC (RTX 5070); PC 3050 runs are routed by the coordinator.

## State (PIPE2 continues; last edit 23 Nov ~19:00)

Where it stands: the gate series for `pipe2d` is **queued** (ticket `20261123-...-pipe2-s1-speed`, 22 runs to do: castle 6, Kokiri 7,
Market 7, the PROF_FINE pair last; a speed lease at priority 2 behind foot2's and zone3's leases, which hold the machine to ~20:30).
Runner `build/s5/pipe2/series.sh` (a tag with a valid result is skipped, so a cut series resumes by re-requesting); its list is
`E:\OOT\scratch-pipe2\tmp\s1-series.sh`, log `build/s5/pipe2/series-s1.log`; launches go through
`E:\OOT\scratch-pipe2\tmp\launch.py` (a detached bash; the harness's shell alternates between Git bash and PowerShell, so a plain
`nohup ... &` from a call is not dependable - a doubled launch cost one tour and one lease today).

Clean baseline, castle off (the series' warm-up `p2s1-warm-c`, 127.2 fps from play + 10 s): frames 8.37-8.79 ms, the PT waited
0.26 ms for the main thread's hand-over, the main thread 1.34-1.43 ms for the present (89-94% of frames over 0.5 ms): replay-bound, the
PT's chain 8.1-8.5 ms. **GPU time 7.6-7.7 ms a frame** in the played windows (1.7 at the title screen; not 5.5, that was a run with
another agent's build in it): the GPU is 89-91% busy, so the stage 1 gate's +8% (7.9 ms frames) is at or beyond the GPU's own work in
this scene - see section 3. The main thread's held submits are replayed on the `HOS_NVN_HOLD=2` flush thread (0.73-0.90 ms a flush),
not on the PT: stage 3's "held flush" is already off the PT in this build.

Losses today: the first series start (18:36-18:40) ran the warm-up and castle off-1 (the run came out at 66.9 fps, 36 frames over 50 ms:
another agent's build began during it, deleted) and then died on runguard exit 11; a second start got the lease at 18:51 and died on
exit 11 again (my own two tour games left running by a doubled launch: killed, both slot leases released, the slots' own exes restored
from `build/s5/pipe2/bak-{a,b}`); a first tour attempt (slot b, 19:31) never started: runguard exit 12, 1065 MB of RAM free with
zone3's game in slot a (a second game does not fit: the tour waits until the machine is free).

Built `build/s5/bin/pipe2e` (19:28, 571 s, tests 503 passed / the 3 known failures) from `0bb228966`: the tip plus the readback
ring's meter re-apply (`vk_rbring.cpp`: with the order thread the game reads and zeroes the meter's block, so a frame's second read
finds its own zero and no new entry; the ring now hands the last applied entry back - the same value the meter hold gave - for the
meter's block only). Committed as `0bb228966`, `fix(vk): the readback ring hands the meter's block its last result back when no entry
is new (order thread, lag 3)`. The gate series now runs on pipe2e (tags `p2g-*`).

Done before this session: stage 0 (`HL_SLACK`, on) and stage 1 (`RX_VK_ORDER_THREAD`, off) on perf/pipe2, tip 1758bb3b0 + the doc; tests
only the known environmental failures. Builds `build/s5/bin/pipe2a..pipe2d` (pipe2d = the tip's code). Function runs (slot, shared
machine, so not comparable): castle on 126.5 / off 119.9; Kokiri on 115.3 / off 118.0; order thread the bound, its replay 8.1-8.5 ms a
frame against the PT's inline chain 7.3; meter 308-496 of 2000 reads given the last result again (0 off).

Open this session:
- Uncommitted, untested: `vk_rbring.cpp`, `rbring_apply` hands the meter's block the last applied entry back when no entry is new
  (class R1, `size == 0x1040`, `memory_is_meter`): the game reads and zeroes the block, so at lag 3 a read with no new entry sees its
  own zero and the meter hold counts it. New stat `again` in the rbring log line. To build and test (unit tests unaffected).
- The castle's GPU time is 5.5 ms a frame (`p2s1-c-off-1/game_log.txt`) against 8.3 ms frames, so the GPU has ~2.8 ms of slack: a
  win is possible; the question is the CPU contention between the replay's recorders and the game's job threads (13 threads on 8 cores).


Done:
- Stage 0 (`HL_SLACK`, on) and stage 1 (`RX_VK_ORDER_THREAD`, off) on perf/pipe2, tip 1758bb3b0 + this doc; tests: only the known
  environmental failures (test_nup_paths, test_nup_read_name, test_renderer_new_handler). Builds `build/s5/bin/pipe2a..pipe2d`
  (pipe2d = the tip's code).
- Stage 0 slack, main PC, slot runs (machine shared): castle off: main's present wait 1.31-1.60 ms a frame (85-98% of frames over
  0.5 ms), PT's hand-over wait 0.22-0.65: replay-bound. Kokiri off: present wait 1.62-1.66 ms (96-98%), PT 0.23-0.25: replay-bound.
  Market: not run yet.
- Stage 1 works (no crash, 0 flashes in function runs without shots, the meter not frozen) and the overlap happens (the PT waits for
  the main thread, the main thread never for the present). pipe2c / pipe2d: the order thread is now the bound (idle ~0.1 ms a
  frame), its replay slower than the PT's inline chain (8.1-8.5 ms a frame); the meter hold gives 15-25% of reads the last result
  (0% off). No clean fps yet: slot runs only (castle on 126.5 / off 119.9; Kokiri on 115.3 / off 118.0, shared machine).

Next (exact): the speed series that was stopped before its lease was granted (castle + Kokiri, 3 interleaved rounds, then a
`RX_VK_PROF_FINE` pair), then `python -I build/s5/pipe2/fps.py <tags>`:

    cd /e/OOT/HeyListen && A=(); A+=("p2s1-warm-c|castle-move|hyrule-castle|-"); for i in 1 2 3; do A+=("p2s1-c-off-$i|castle-move|hyrule-castle|-" "p2s1-c-on-$i|castle-move|hyrule-castle|RX_VK_ORDER_THREAD=1"); done; A+=("p2s1-warm-k|kokiri-idle|kokiri-forest|-"); for i in 1 2 3; do A+=("p2s1-k-off-$i|kokiri-idle|kokiri-forest|-" "p2s1-k-on-$i|kokiri-idle|kokiri-forest|RX_VK_ORDER_THREAD=1"); done; A+=("p2s1-pc-off|castle-move|hyrule-castle|RX_VK_PROF_FINE=1" "p2s1-pc-on|castle-move|hyrule-castle|RX_VK_ORDER_THREAD=1 RX_VK_PROF_FINE=1"); bash build/s5/pipe2/speed.sh s1 pipe2d "${A[@]}"

Then the Market (same form, save market-mid, scene market-spin), the tour (`bash build/s5/pipe2/tour.sh pipe2d "p2t-off|-"
"p2t-on|RX_VK_ORDER_THREAD=1"`: flashes, meter, maps), and if the gate passes (castle and Kokiri +8%, Market within the spread, 0
flashes, meter not frozen, pictures right) the PC 3050 list in `build/s5/pipe2/`. Slot leases at priority 1, speed at 2 (coordinator).

Open risks / leads:
- Why the replay is slower on the order thread: one slot profile (shared GPU, not trusted) showed vkQueueSubmit at 10 ms a frame
  against 2.5 off and the parallel segments 4x slower: check under a speed lease (the PROF_FINE pair above); suspects the GPU queue
  running ahead (no present pacing on the CPU side), contention with the PT's captures, the 64-72 jobs queued (registrations).
- The meter's held reads (15-25%): the ring at lag 3 or the readback join's narrowing; watch the picture's exposure in the tour.
- Reads outside the capture view (stage 2) not covered: texture uploads and collected writes read guest memory at replay time.
- `RX_VK_ORDER_RB_JOIN=1` (a readback waits for its own thread's submissions only) follows the inline replay's semantics; =2 is the
  conservative arm if pictures go wrong.
- Scripts: `build/s5/pipe2/build.sh <name> [tests]`, `func.sh`, `tour.sh`, `speed.sh`, `fps.py`.

## Stage 0: the stages' slack (`HL_SLACK`, on; =0 off)

`host/hos_slack.c`: the PT's blocking receive at lr 0x834a3084 on the presenting thread (the game's message-queue receive: the same lr
serves the module workers' and BaseProcExecutors' queues, so only the presenting thread counts) and the main thread's event wait at lr
0x81207a6c (the present wait, signalled by the PT), both timed from their start where they block (`nn_os_sync.c` event_wait,
queue_get). Every 600 presents: `slack (600 frames, X ms a frame): the PT waited A ms a frame for the main thread's hand-over, the main
thread B ms a frame for the present (P% of frames over 0.5 ms): replay-bound | game-bound | balanced`. `HL_SLACK_LRS=<pt>,<main>`
(hex) for other callers. Cost: two clock reads on waits that block anyway.

Gate for the later stages: present wait > 0.5 ms a frame.

## Stage 1: the order thread (`RX_VK_ORDER_THREAD=1`, off by default)

What it does (`vk_replay.cpp`, block after `cpu_wait_open`):
- `submit_q` (every submitting thread: the PT, and the main thread's held submits the PT flushes) takes the capture under
  `submit_order_mu`, gives the submission its value (`q_values`, so `rx_nvn_pushed` / `fence()` count handed-over submissions; the
  recording copies' lifetime follows `rx_nvn_replayed`, the GPU's), notes its waits (with the submission's value), tags it for the
  readback ring (`rb_note_value`) and pushes a job; it returns at once. The order thread runs the job as `submit_q` ran it inline:
  `sync_order_mu`, `q_last` / `value_queue`, `submit_job` (qruns, bursts), `update_blocked`.
- `present` hands a present job over (at most `RX_VK_ORDER_AHEAD`=2 not yet shown); the job waits (bounded, `RX_VK_ORDER_SIGNAL_MS`
  200) for the CPU's signal its own frame's stopped work waits for (FIF's rule, now limited to submissions before the present),
  drains the stopped queues and presents.
- Registrations (texture, sampler) and releases (texture, program) are jobs (their sync bodies run on the order thread).
- Joins (wait for the order thread's progress, not on the order thread itself): a fence wait waits for its submission's job
  (`ot_wait_for`, with the game's timeout; a poll is told "not yet": nothing of it is on the GPU; `RX_VK_ORDER_POLL_JOIN=1`: polls
  wait too); `wait_queue_empty` (nvnQueueFinish, texel reads and writes, the vmap and invalidate catch-ups) and every CPU readback the
  ring does not serve (`invalidate`) wait for all jobs handed over; the host's event polls (`nvnEventGetValue`) too, through the
  `mkwvk_order_join` export (`HOS_ORDER_EVENT_JOIN=0`: not), the core given up only when jobs are pending. `fence_q` answers from
  the handed-over submissions (`ot_q_last`) without `sync_order_mu`.
- Switches on with it: the CPU's signals in the capture sequence (`signal_capture_on`), the readback ring's frame clock
  (`rb_fif_on`) and lag 3 (`vk_rbring.cpp`, unless `HL_RB_LAG` says), the host's `HOS_PRESENT_NOWAIT` (the PT's present poll at lr
  805904a0 / 80590530 answered at once).
- `resume_queue`'s capture of a CPU-signalled wait (`memory_capture_now`) takes `submit_order_mu`: the submitting threads capture
  meanwhile, and the copy helpers serve one capture at a time.
- Log every 600 presents: `vk: order thread (...)`: its idle time, its queue's depth, the present's signal waits, and each join site's
  waited / asked counts and ms a frame.

## Attempts and measures

### 1. pipe2a, function runs (slot a, 23 Nov 15:12, machine shared: fps not comparable)

| run | fps | stage 0 slack (each 600-frame window) | order thread |
|---|---:|---|---|
| castle, off | 119.9 | PT waits 0.22-0.65 ms, main's present wait 1.31-1.60 ms a frame (85-98% of frames > 0.5 ms): replay-bound | - |
| castle, on | 121.1 | PT waits 7.6-8.1 ms, main 0.00: game-bound | idle 2.8 ms a frame; one readback a frame joined, 2.2-2.3 ms a frame |
| Kokiri, on | 73.4 | PT 11.0 ms, main 0.00 | idle 4.2-4.3 ms; one readback a frame joined, 3.7-3.8 ms a frame |

No crash, 0 flashes (the detector was off in these runs: no shots), the meter not held (0 of 2000). The overlap works (the PT waits for
the main thread, the main thread never for the present; fence waits, polls, catch-ups and event polls never had to wait for the order
thread) but one CPU readback a frame not served by the ring joined *every* job handed over, so the main thread waited for the replay
of the frame before again (Kokiri fell to 73 fps). Inline, a reader only had its own thread's submits replayed; the other threads'
(the PT's) were being replayed beside it. Fixed in pipe2b: `RX_VK_ORDER_RB_JOIN=1` (default) waits for the reading thread's own jobs.

### 2. pipe2b and pipe2c, function runs (slot a)

pipe2b (own thread's jobs): the main thread's one readback a frame (0x115bcf9580 +0x1b580, `RX_VK_ORDER_LOG`) still waited 2 ms a frame
(once 56 ms): its last job was a texture registration, queued behind the PT's frame. Inline, registrations never waited for the replay.
Kokiri on 117.6 against off 118.0 fps. pipe2c counts only the thread's submissions: readbacks 0 waits; now the order thread is the bound:

| run | fps | order thread | joins |
|---|---:|---|---|
| Kokiri on | 115.3 | idle 0.11 ms a frame, 64 jobs queued on average (138 at most) | fence waits 495 / 600 frames, 0.79 ms a frame |
| castle on | 126.5 | idle 0.07 ms a frame, 72 jobs queued (154 at most) | fence waits 511, 0.67 ms a frame |

The meter: 308-496 of 2000 reads given the last result again (0 in the runs before; not frozen: frozen is >= 1990). The order thread's
work, 8.1-8.5 ms a frame, is more than the PT's inline chain (submits + present, 6.7-7.4 ms in PIPE1's traces): the replay got slower
on its own thread.

### 3. The GPU's own work per frame: what the gate's +8% meets (clean runs, 23 Nov 19:20-20:15)

The engine logs the GPU's busy time a frame (`vk: GPU time X ms a frame`, the sum of the recordings' timestamp spans, every 120
presents; the gaps between recordings and the uploads are separate). In the two scenes the gate uses, on this PC, a frame of the played
scene is 88-95% GPU-busy:

| run (one run each) | fps | frame, the played windows (ms) | GPU busy a frame (ms) | GPU of the frame |
|---|---:|---|---:|---:|
| castle off, `p2s1-warm-c` (pipe2d) | 127.2 | 8.37 / 8.56 / 8.55 / 8.79 / 8.49 | 7.68 / 7.62 / 7.88 / 7.82 / 7.64 | 89-92% |
| castle off, `p2g-warm-c` (pipe2e) | 126.4 | 7.84 / 8.12 / 8.56 / 8.73 / 8.76 | 6.44 / 7.78 / 7.86 / 7.90 / 7.92 | 82-96% |
| Kokiri off, `p2b-f-off-kok` (pipe2b, shared machine) | 118.0 | 8.29 / 8.36 / 8.16 / 8.29 / 8.63 | 7.30 / 7.28 / 7.20 / 7.36 / 7.34 | 85-89% |
| Kokiri on, `p2c-f-on-kok` (pipe2c, shared machine) | 115.3 | 8.68 / 8.03 / 7.99 / 8.07 / 8.14 | 7.24 / 7.28 / 7.26 / 7.24 / 7.24 | 83-91% |

(each line: the last five 600-present windows of the run, and the GPU line's five 120-present windows that fall in each.)

(Title screen, for scale: GPU 1.7 ms of 2.8 ms frames.) The GPU's work a frame is the same in both arms (it does not depend on where
the replay runs), and it varies with what the camera sees: in the castle's fast windows 5.4-6.7 ms of GPU work against 7.2-7.5 ms
frames, in its slow ones 7.6-8.1 against 8.4-8.8.

What it means for the gate: **the frame cannot be shorter than the GPU's work plus the present's ~0.2 ms.**

- **castle**: the ceiling is 7.8-8.1 ms a frame (123-128 fps), and the two off runs are at 126.4-127.2 fps: **the scene is at the GPU's
  ceiling today**; the gate's +8% (7.9 ms frames from a 8.5 ms median, ~137 fps) would need the GPU's own work to drop by half a
  millisecond, which no CPU-side change can do. Some windows are already there (7.84 ms of frame against 6.44 of GPU in `p2g-warm-c`).
- **Kokiri**: the ceiling is 7.4-7.6 ms (132-135 fps) against 8.2-8.6: +8% (128 fps, 7.8 ms) is inside it, by ~0.3 ms.

So PIPE1's upper bounds (+10-16%, +16-21%, section 3 there) were read off the traces and did not include the GPU's share: **on this PC
the castle has ~0-3% of room and Kokiri ~10%**, not 10-21%. PIPE1's traced castle window ran at 7.59 ms a frame, which today's GPU work
(7.6-8.0) would not allow: the scene moment (the camera turns move the GPU's work between 5.4 and 8.1 ms a frame within one run) or the
builds differ; the series' own GPU lines say which.

## Dead ends

(none yet)
