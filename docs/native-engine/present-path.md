# The presenting thread's path (PRESENT1, 21 Nov 2026)

Evidence: a WPR trace of the Market on the PC 3050 (i5-10400F), 1215 frames of 24.3 ms. The presenting thread (the one that
calls `nvnQueueSubmitCommands` and `nvnQueuePresentTexture`) runs 4.2 ms of each frame on the critical path and is blocked 19.6 ms:
10.5 ms waiting for the replay's order thread (`sync_order_mu`, owned by the order stream), 3.3 ms for a pool worker, 2.1-2.4 ms in
about 1.5 timed waits of 1.0-1.6 ms (0.5 ms timer ticks, not GPU completions), 1.1 ms for the capture copy worker.

## What the thread does each frame

1. `nvnWindowAcquireTexture` (nvn_native.c): gives its virtual core up, `hos_vi_native_acquire` (the frame pacing sleep, `nn_vi.c`;
   none when the frame is slower than the limit), takes a core again.
2. Its own `nvnQueueSubmitCommands`, about four a frame (`HOS_NVN_HOLD=2`: the main thread's submits are held and replayed by the
   presenting thread or the "hos held submits" thread): core given up, `flush_cs` taken (waits while the held-submit thread
   replays), the held submits replayed first, then `rx_nvn_submit_q` -> `vk_replay.cpp submit_q`: `sync_order_mu`, the submit's
   capture (`memory_capture_submit`: the write-mark scan `collect_in`, the page copy on the helpers) and `submit_job` ->
   `run_submit` -> `replay_handle` on this thread (37% of its samples), core taken again.
3. `nvnQueuePresentTexture`: a flush of what is held, `hos_wide_ui_tick`, the renderer's `present`: `drain`, `do_present`
   (`dead_targets_sweep` 4% of its samples, texture eviction, the blit and `vkQueuePresentKHR` in `present_image`:
   fence wait of the blit three presents back, `vkAcquireNextImageKHR`, `vkQueueSubmit2`, `vkQueuePresentKHR`; 22% win32u and
   15% kernel leaf samples are those driver calls), then `hos_vi_native_presented` (pacing bookkeeping, `realtime_step`).

Its samples (SampleProf, 6121): win32u 22%, kernel 15%, `collect_in` 10%, nvoglv64 10%, ntdll 7%, `dead_targets_sweep` 4%.

## The timed waits

Every call above gives the virtual core up for its block and takes one back (`hos_vcore_away` / `hos_vcore_back`, hos_thread.c).
`vc_acquire` queues the thread and waits on its condition variable with a **1 ms timeout**. A release hands the core over at once
(`vc_grant` wakes it), but when all six cores are held by threads of the same priority (the six job executors spin and keep
their cores) nobody is asked: equal-priority holders are kicked only after `HOS_VCORE_SLICE_US` (2 ms) of waiting, so the wait
ends by the 1 ms timeout of the loop, one or two of them, quantised to the timer tick. That matches the trace (1.0 and 1.4-1.6 ms
peaks, woken from a timer DPC, about 1.5 a frame) and is the only timed wait on this thread's own path in the code: the
pacing sleep is not reached at 41 fps, the Vulkan waits are infinite fence waits, the Reflex sleep is off by default.
Not proven by the trace (it has no wait stacks): the first thing to check with HL_PRESENT_LOG.

## Switches (both default off; off is exactly the previous behaviour)

- `HL_PRESENT_CORE=1`: the presenting thread's returns to a core are urgent (`hos_vcore_urgent`): it waits as a starved thread does
  from its first moment (served first by `vc_grant`, the worst holder on its cores asked at once whatever its priority), so the
  wait ends by a grant, not by the timeout. Cost: another thread gives up a core for a moment at each of its returns.
- `HL_PRESENT_LOG=1`: every 600 presents, per frame: ms in the acquire, in its submits, in the present, and this thread's waits for
  a core (count, ms, how many ended by the 1 ms timeout: the new `cc_vcw_to`). One line, `hl present: per frame over 600: ...`.

## What was not changed, and why

- The 10.5 ms wait for the order thread is the order stream's (`sync_order_mu`, `sync_watch`).
- The capture scan and copy (`collect_in`, ~0.3 ms a submit, ~1.7 ms a frame at six submits) was studied in TICK-061: `RX_VK_COLLECT_FAST=1`
  gives -30% of the scan (0.12 ms a frame), still off; adopting it is a measurement matter (it is in the exe, no stamp).
- `dead_targets_sweep` runs every present (`RX_VK_DEAD_EVERY=1`); `RX_VK_DEAD_EVERY=2` halves its ~0.2 ms a frame: an A/B, not a change.
- Skipping the core hand-off for short submits was not done: a thread that keeps its core through an unexpected long replay
  (zone loads, hundreds of ms) starves the waiters until the 2 s escape.

## To validate when machines are free (PC 3050 first: the trace was taken there)

1. `HL_PRESENT_LOG=1` alone: the core waits a frame and how many end by timeout (expect ~1.5 a frame, 1-2 ms, if the reading above is right).
2. `HL_PRESENT_CORE=1 HL_PRESENT_LOG=1`: timeouts to ~0, the acquire/submit/present parts shorter by that time; the other threads'
   `HOS_VCORE_LOG=1` lines (waits, ms a second) must not grow much; game-speed ratio near 60; shots right.
3. A/B on the 3050 and the main PC, castle-move x3 first (the short screen), then 3x6 only to confirm an adoption.
4. `RX_VK_COLLECT_FAST=1` and `RX_VK_DEAD_EVERY=2` on the same screen, as separate A/Bs.
