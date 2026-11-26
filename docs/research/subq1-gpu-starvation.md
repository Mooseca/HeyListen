# SUBQ1: why the GPU queue sits empty (22 Nov 2026, branch perf/subq1 from refactor/integ4 582aba6a6)

## The finding
RTX 3050 PC, `RX_VK_PASS_TIMING=2`, 1440p, no upscaler (extracts in `E:\OOT\scratch-gprof1\<scene>-r100`, `market-r50`): the queue is empty
6.0-6.6 ms a frame (market: window 21.55 = busy 14.95 + empty 6.60), 6.49 ms of it before a buffer that starts with an upload barrier, in
18.6 gaps. 2 gaps a frame of 1-5 ms hold 3.44 ms, 5.2 gaps of 0.1-1 ms hold 2.68 ms. At 50% the idle grows to ~11 ms. Write-backs: 52-60 MB
and 0.75-1.4 ms of GPU a frame (market 0.76, kokiri 1.09, hyrule 1.37).

## What the profile cannot say
`RX_VK_PASS_TIMING` (any non-zero value) takes the serial replay path (`gprof_on()` in `replay_handle`) and waits for the GPU at every
timestamp: the replay's parallel segments, which are the shipped configuration, are off, and the CPU chain is longer than in play. The
6 ms is therefore an upper bound. The unprofiled instruments that already exist: the "GPU time ... gaps between recordings" line (always on,
per-recording first/last timestamps) and `RX_VK_FEED_LOG=1` ("GPU feed": the idle split into replay not ready / ready not sent / sent not
started / sent before the GPU went idle). New in this branch: `RX_VK_QUEUE_PICTURE` (default on, `=0` off, logging only), one line every
120 presents next to the "GPU time" line: busy, empty, and the empty time by gap length (<0.1, 0.1-1, 1-5, 5+ ms), from the same
per-recording timestamps, no profiler, no extra GPU work. The present's blit is not timed, so it counts as empty there.

## Where the CPU is when the GPU starves (read from the code and the earlier streams' measurements)
- A recording's two command buffers (upload first, then the recording's own) go out in ONE `vkQueueSubmit2` at the end of the recording
  (`submit_recording`, vk_replay.cpp); the upload buffer (msync scatter, rbrefresh scatter, barriers: 0.7 ms of GPU a frame) is filled while the
  recording is recorded and holds nothing the GPU could have started earlier. So "the gap before a buffer that starts with u barrier" is just
  "the gap before a recording": the label says which buffer the submit begins with, not what the GPU waited for. Sending the upload buffer
  separately and earlier cannot fill a 6 ms hole: its work is 0.7 ms, and it only exists once the replay has got that far.
- Submit mechanics are not the gap: batching sends at once while the GPU is idle (`RX_VK_BATCH_IDLE`, default), one queue, timeline
  semaphores already carry the order. ORDER3 measured on the RTX 5070 (docs/native-engine/replay-cost.md): idle 3.7 ms of a 10.9 ms frame,
  replay not ready 3.25 (88%), ready but not sent 0.07, sent and not started 0.29, sent before the GPU went idle 0.13. REPLAY2 split the
  not-ready time into seven steps of the submitting thread's serial chain (game's own time 0.2-0.3, capture 0.13-0.15, setup 0.2-0.25,
  small command buffers 0.4-0.45, dry pass 0.26-0.3, own segment 0.7-0.8, wait for the segments 0.24); FEED1 showed the replay already starts
  on each submit 5 us after the game hands it over.
- The late-page wait: the game's thread waits for the GPU once a frame (0.94 waits a frame in the profile) for a value whose busy tail is
  10-18 ms; after it the CPU has to produce the next submissions while the queue is empty. That is the 1-5 ms gaps (2.0 a frame, 3.44 ms).
  The tail holds `wb` spans of 0.25 ms (market), 0.97 (kokiri), 0.33 (hyrule): so deferring the write-backs (ReLink's `RX_VK_WB_LAZY`) can
  shorten that wait by at most 1-5% of it on these scenes, and ReLink's own bench found no fps beyond the noise on a fast link
  (relink vk_memory.cpp 3010-3120: "stays opt-in"; on by itself only where its PCIe probe says the link is slow).

## Reading
The GPU is not starved by a submit-path defect that a different submit order, merged command buffers, timeline semaphores or a transfer queue
would repair: the queue is empty because the serial CPU chain that produces the recordings (replay on the game's submitting thread) is
longer than the GPU's work, in an order the game fixes (a late-page wait once a frame ties the GPU's end of frame to the CPU's start of the
next). That is also why 50% resolution gains 3-6%: the GPU work shrinks, the CPU chain does not. The profile's 6 ms is inflated by the
serial replay; the unprofiled share on the 5070 is ~28-34% of the frame (ORDER3/REPLAY2), 3050 unprofiled numbers: asked, see below.

## Candidates and verdicts so far
| candidate | verdict |
|---|---|
| submit the upload buffer earlier / separately | no gain possible: 0.7 ms of work, available only at the recording's end |
| merge small submits, timeline semaphores, transfer queue for the scatters | the submit costs 0.04 ms each (REPLAY2/JOIN1 numbers) and the gaps are "replay not ready"; not built |
| defer write-backs (`RX_VK_WB_LAZY` from ReLink) | shortens the late-wait tail by <=0.25-0.97 ms of 10-18; touches the 8700-line vk_memory.cpp's write-back, guard and page-protection logic; deferred until the 3050 data shows the tail on the critical path |
| defer the join of the big command buffers' segments (JOIN1 `RX_VK_DEFER_JOIN`) | measured, no gain on the 5070: nothing can run beside pending segments (shared memory/texture globals) |
| make the serial chain shorter (the real lever) | stream-sized: per-recording memory/texture globals so a small recording can be recorded on a worker, see replay-cost.md JOIN1 and REPLAY2 |

## Measurements in this branch
- Main PC, RTX 5070: NOT RUN. The speed lease queue held 3 requests of priority 2 and a 45-minute lease at 18:35 (build behind them), and the new
  line needs a build. Not verified: that the queue-picture code compiles in the full build (the clang syntax check had no Vulkan headers
  outside the build tree); tests run: `test_queue_picture.py`, `test_switches_documented.py`.
- PC 3050: run list sent to the coordinator (unprofiled `RX_VK_FEED_LOG=1`, market/kokiri/hyrule, 100% and 50%, build integ4). Numbers pending.

## Dead ends
- PASS_TIMING as the idle measure (serial replay inflates it); PASS_TIMING=1 does the same.
