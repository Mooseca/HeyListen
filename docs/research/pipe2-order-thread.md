<!-- Copyright (C) 2026 Sacrappy -->
# PIPE2: the stages' slack and the replay on an order thread (23 Nov 2026 -)

## Summary (this session, end of the gate series; 23 Nov 23:05)

1. **The gate does not pass on the fps conditions.** One clean speed lease, `pipe2e` (`0bb228966`), 3 interleaved rounds a scene, fps
   from play + 10 s: **castle-move +6.2%** (median 127.6 -> 135.5; rounds +0.6 / +7.0 / +4.9), **kokiri-idle +4.7%** (121.2 -> 126.9;
   +6.7 / +3.1 / +4.5) against the brief's +8%. **The Market is inside its spread** (the clean round +0.3%, its frame p50 equal within
   1%; the other two rounds hitched in both arms). **The meter is not frozen and not held: 0 of 2000 reads given the last result again
   in every on run** (308-496 before the fix in this session). Flashes and pictures: **not measured** (the tour was killed by my own
   doubled launch, its retry refused by runguard's RAM guard while another game held a slot, a third attempt queued behind the other
   streams' leases and still waiting).
2. **Why, from the same counters: the overlap works and the GPU's own work is the floor.** In every on run the PT waits 5.6-10.3 ms for
   the main thread's hand-over and the main thread 0.00 ms for the present (1.4-1.7 off); the order thread idles 0.01-0.18 ms in the
   replay-bound scenes and 1.9-2.9 in the game-bound Market. The CPU work above the GPU's own time per frame fell by 27-33% (castle
   0.73 -> 0.53 ms, Kokiri 1.04 -> 0.70). The GPU needs 7.6-7.7 ms a frame in the castle (94-95% of the on frame) and 7.1-7.2 in
   Kokiri (91-93%): **the castle's whole room is ~+6.7%** (the order thread takes +6.2% of it) and **Kokiri's ~+11%**, of which +4.7%
   is taken - Kokiri's +8% misses by ~0.3 ms of CPU above the GPU (needs 0.38, has 0.70). PIPE1's +10-16% upper bounds did not include
   the GPU's share.
3. **The meter's held reads are fixed** (`0bb228966`, section 4/5): the ring hands the meter's block its last applied entry back when no
   entry is new, which is the value the meter hold used to supply.
4. **Next** (in order): the present out of the order thread's chain (a present thread, FIF's, without FIF's contention) for Kokiri's
   ~0.3 ms; the tour for the flashes and the pictures; a valid PROF_FINE pair on the on arm (`series.sh`'s comma bug is fixed); the PC
   3050 list, which the coordinator routes.


Branch `perf/pipe2` from origin/main 4b599eb04 (PIPE1 merged, `RX_VK_TOUCH_FAST` on). Worktree `E:\OOT\HeyListen-wt\pipe2`. Design:
`pipe1-frame-overlap.md` section 3 (stages 0-3 with their gates). Main PC (RTX 5070); PC 3050 runs are routed by the coordinator.

## State (PIPE2 continues; last edit 23 Nov ~23:10)

Where it stands: **the gate series is done** (`pipe2e`, `0bb228966`, one clean speed lease 22:19-22:57, 19 runs, sections 4-5): castle
+6.2% (median), Kokiri +4.7%, Market inside its spread in the clean round, the meter at 0 held reads; **the fps gate does not pass** and
section 5 says why (the GPU's own 7.1-7.7 ms a frame; the castle's whole room is ~+6.7%). The flashes/pictures are still unmeasured: a
slot lease for the tour (`build/s5/pipe2/tour.sh`, tags `p2t2-*`, `RX_VK_SHOTS` per arm under `E:\OOT\scratch-pipe2\shots`) is queued
behind foot2-T9's and zone4's speed leases (ticket `20261123-230212-pipe2-slot-e6c9`). Runner: `build/s5/pipe2/series.sh` (a tag with
a valid result is skipped, so a cut series resumes by re-requesting); list `E:\OOT\scratch-pipe2\tmp\s1-series.sh`, log
`build/s5/pipe2/series-s1.log`; launches through `E:\OOT\scratch-pipe2\tmp\launch.py` (a detached bash; the harness's shell alternates
between Git bash and PowerShell, so a plain `nohup ... &` is not dependable - a doubled launch cost one tour and one lease today). Gate
table: `python -I E:/OOT/scratch-pipe2/tmp/gate.py "p2g-*"`.

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

- **castle**: the off frame is 8.43 ms against 7.70 of GPU work: 0.73 ms of CPU above the GPU, of which the present needs ~0.2. So the
  best possible frame is ~7.9 ms (126.6 fps) and the off fps 127.6 is already there in the run's average: **the castle has at most
  ~+6.7% of room**, and the on arm takes +6.2% of it (section 5). The +8% the gate asks for needs a frame of 7.85 ms, which is below
  the GPU's own work in the scene's slow windows (7.6-7.7 + 0.2).
- **Kokiri**: the off frame is 8.24 against 7.20 of GPU work: 1.04 ms of CPU above the GPU, so a frame of ~7.4 ms (+11%) is the
  ceiling and +8% (7.58) needs 0.38 ms of overhead. The on arm gets to 0.70 (7.90) - +4.7%, i.e. half the room is still there.

So PIPE1's upper bounds (+10-16%, +16-21%, section 3 there) were read off the traces and did not include the GPU's share: **on this PC
the castle has ~6.7% of room and Kokiri ~11%**, not 10-21%, and of that the order thread as built (the present in its own chain) takes
+6.2% and +4.7%. PIPE1's traced castle window ran at 7.59 ms a frame, which today's GPU work
(7.6-8.0) would not allow: the scene moment (the camera turns move the GPU's work between 5.4 and 8.1 ms a frame within one run) or the
builds differ.

### 4. The first clean on/off pair (castle-move, pipe2e, 21:21-21:27: the lease was cut by another agent's game after three runs)

| run | fps (play + 10 s) | frame p50 / mean (ms) | >50 ms | slack: PT waits for main / main for present | GPU time | order thread |
|---|---:|---|---:|---|---:|---|
| `p2g-c-off-1` | 137.8 | 6.68 / 7.26 | 18 | 0.21 / 1.10 | 5.0 | - |
| `p2g-c-on-1` | 138.6 | 6.38 / 7.22 | 26 | 5.63 / 0.00 | 5.4 | idle 0.18, fence join 0.40 |
| `p2g-c-off-2` | 126.6 | 7.83 / 7.90 | 6 | 0.32 / 1.43 | 7.5 | - |
| `p2g-warm-c` (off) | 126.4 | 7.92 / 7.91 | 0 | 0.24 / 1.55 | 7.9 | - |

Three things:
- **The overlap works and its cost is small**: the on arm's frame median is 0.30 ms shorter than the off arm's (6.38 against 6.68) and
  the CPU work above the GPU's own time is halved (frame - GPU: on 0.66 ms, off 1.39 ms). The PT waits 5.63 ms for the main thread and
  the main thread never waits for the present; the order thread idles 0.18 ms; the fence join costs 0.40 ms.
- **The fps of the two arms is the same within the noise (+0.6%)** because the GPU's own work differs between the runs: the walk's
  camera turns move it from 5.0 to 7.9 ms a frame, and a run's window covers a different stretch of the walk (`c-off-1` and `c-on-1`
  saw 5.0-5.4 ms of GPU, `c-off-2` and the warm-up 7.5-7.9). The interleaved rounds are the only way to compare: one round is not
  enough, and the hitches (18-26 frames over 50 ms, max 300-450 ms: a load hitch inside the window) are in both arms.
- **The meter's fix holds**: `p2g-c-on-1`'s log has `exposure sums: 2000 reads, 0 of them given the last result again` in every window
  (the runs before the fix gave 308-496 of 2000 on the on arm, 0 off): `0bb228966` does what it says.

### 5. The gate series (pipe2e, one clean speed lease, 22:19-22:57, 19 runs, 3 interleaved rounds a scene, fps from play + 10 s)

| scene | round | off | on | on/off |
|---|---|---:|---:|---:|
| castle-move | 1 | 137.8 | 138.6 | +0.6% |
| | 2 | 126.6 | 135.5 | +7.0% |
| | 3 | 127.6 | 133.8 | +4.9% |
| | **median** | **127.6** | **135.5** | **+6.2%** (mean 130.7 -> 136.0, +4.1%) |
| kokiri-idle | 1 | 120.9 | 129.0 | +6.7% |
| | 2 | 123.1 | 126.9 | +3.1% |
| | 3 | 121.2 | 126.7 | +4.5% |
| | **median** | **121.2** | **126.9** | **+4.7%** (mean 121.7 -> 127.5, +4.8%) |
| market-spin | 1 | 101.3 | 101.6 | +0.3% |
| | 2 | 84.7 (34 frames over 50 ms) | 86.9 (21) | +2.6% |
| | 3 | 99.1 (10) | 87.5 (22) | -11.7% |
| | **median** | 99.1 | 87.5 | -11.7% (mean 95.0 -> 92.0, -3.2%) |

Warm-ups (off arm): castle 126.4, Kokiri 121.8, Market 103.2 fps. The PROF_FINE pair at the end does not count: `series.sh` passed
`RX_VK_PROF_FINE=1,RX_VK_ORDER_THREAD=1` as one `export`, so the "on" prof run had neither switch (its slack line is the inline arm's:
PT waits 0.27, main 1.65); it is a fourth off sample (127.9) and the comma is now turned into a space in `series.sh`.

The counters behind the numbers (medians of the last five 600-present windows, `python -I E:/OOT/scratch-pipe2/tmp/gate.py "p2g-*"`):

| | castle off | castle on | Kokiri off | Kokiri on | Market off | Market on |
|---|---:|---:|---:|---:|---:|---:|
| frame (ms) | 8.43 | 8.13 | 8.24 | 7.90 | 9.89 | 10.50 |
| PT waits for the main thread | 0.23 | 7.75 | 0.40 | 7.20 | 1.39 | 9.67 |
| main waits for the present | 1.52 | 0.00 | 1.62 | 0.00 | 0.39 | 0.00 |
| GPU time (ms) | 7.70 | 7.60 | 7.20 | 7.20 | 7.20 | 7.00 |
| frame - GPU (CPU above the GPU) | 0.73 | 0.53 | 1.04 | 0.70 | 2.69 | 3.50 |
| order thread idle (ms) | - | 0.01 | - | 0.16 | - | 2.30 |
| fence join (ms) | - | 0.82 | - | 0.80 | - | 0.15 |

**The gate does not pass: castle +6.2%, Kokiri +4.7% (the brief's +8%), the Market inside its spread in the one clean round (+0.3%,
the other two rounds hitched on both sides: the Market's frame p50 is 9.3-9.6 ms in every run while the mean is 9.8-11.8), the meter at
0 held reads.** What the overlap does is exactly what section 3 predicted: the CPU work above the GPU's own time falls by 27-33%
(castle 0.73 -> 0.53, Kokiri 1.04 -> 0.70) and the PT's wait moves from the present to the main thread (1.52 -> 0.00 present wait,
0.23 -> 7.75 hand-over wait). What is left above the GPU is 0.5-0.7 ms, the present (0.18-0.2) and the last submission's latency in
the frame. **The castle's +8% is not there at all**: its whole room is ~+6.7% (section 3), and the order thread takes +6.2% of it.
**Kokiri misses +8% by ~0.3 ms**: +8% needs 0.38 ms of CPU above the GPU and the arm has 0.70. The next lever for that 0.3 ms is the
present out of the replay's chain (a present thread of its own, FIF's, without the contention FIF met) or the replay's tail; behind
both sits the GPU's own work (94-95% of the frame in the castle's slow windows, 91-93% in Kokiri's).

The gate, condition by condition:

| the brief's gate | measured | verdict |
|---|---|---|
| castle-move +8% or more against off | +6.2% median (+4.1% mean; +0.6 / +7.0 / +4.9 by round) | **no** |
| Kokiri +8% or more against off | +4.7% median (+4.8% mean; +3.1 / +6.7 / +4.5) | **no** |
| Market not below the spread | the clean round +0.3%; the frame medians 9.28-9.57 (on) against 9.39-9.47 (off), inside 1%; the run means are hitch-dominated on both sides (frames over 25 ms: off 8 / 126 / 35, on 13 / 156 / 81) | yes |
| the meter not frozen, M near 0 | 0 of 2000 in every on run and every window against 308-496 before `0bb228966` (off: 0-1) | yes |
| 0 flashes over a warp tour, pictures right | not measured: the tour's first attempt was killed by a doubled launch, the second refused by runguard's RAM guard (another game in a slot); a slot lease for it is queued behind the other streams' speed leases | no data |

The overlap's own evidence in these runs: the PT waits 5.6-10.3 ms for the main thread's hand-over in every on run and the main thread
0.00 ms for the present (1.4-1.7 off); the order thread idles 0.01-0.18 ms a frame in the replay-bound scenes (it, not the GPU queue,
was the bound) and 1.9-2.9 ms in the game-bound Market; the fence join (the game's own `nvnSyncWait` on the PT's fence, answered when
the order thread reaches it) costs 0.40-0.86 ms a frame on the main thread's side.

## Dead ends

(none yet)
