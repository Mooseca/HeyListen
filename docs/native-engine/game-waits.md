# Where the game's other threads wait, spin and poll (GAMEWAIT1, 21 Nov 2026)

Evidence: the Market trace on the PC 3050 (i5-10400F, 6 cores / 12 threads; 1215 frames, 24.3 ms a frame): the game's
threads use 4.8 cores; "other game threads" run 4.1 ms of the critical path and a pool worker 1.7 ms; the six BaseProc
executors burn about 9 s of CPU each in 30 s; the order thread shared its physical core with a busy sibling 42% of its time,
the presenting thread 28%, the replay workers 73%. The CPU is not oversubscribed (wake-to-run median 13 us). The trace has
no stacks for the executors, so the map below comes from the code; what a switch is worth is not measured yet.

## The map

| Where | What | Cost |
|---|---|---|
| Polling lane of every stage (`Dispatcher::Rings::poll`, `bridge/Dispatcher.cpp`) and of the module group (`JobGroup::Heap::poll`, `bridge/JobGroup.cpp`) | The context on the scheduler's `poll_lane` never sleeps on its wake event: with nothing to take it sleeps ~100 us (`timed_sleep` -> the guest's SleepFor) and looks again. | On Windows a sleep under 1 ms is `SwitchToThread` in a loop (`sleep_ns`, `HOS_SHORT_SLEEP_TIMER` off): the lane is a busy logical CPU for every stage with no work, twice (actors, modules). It is the SMT sibling of a critical thread whenever the scheduler puts it there. |
| Other job contexts | Sleep on their wake event (`sleep_on_event`), woken by `Context::wake` after a take. | Blocking already. |
| nn::os waits (`nn_os_sync.c`: events, semaphores, queues, mutex hand-over) | `spin_until_set` / `spin_until_free`: up to `HOS_SPIN_US` (20 us) of `_mm_pause`, adaptive per object (after 4 misses one wait in 32 spins), then a blocking wait. | Bounded: 3-5% of the executors' samples. Not changed. |
| Guest yields (`YieldThread`, `SleepThread(0)`) | Virtual core handed over; `SwitchToThread` only with `HOS_OS_YIELD=1`. | Already cheap by default. |
| Guest sleeps under 1 ms (`sleep_away`/`sleep_ns`) | Yield loop; `HOS_SHORT_SLEEP_TIMER=1` moves them to the timer, `HOS_SHORT_SLEEP_PAUSE=1` to a PAUSE loop. | The polling lane's 100 us sleeps are the main user. |
| Placement | `hos_thread_pin`: every game thread is kept off the replay's core (`hos_reserved_cpus`, the last physical core); the presenting thread (the one that calls `nvnQueuePresentTexture`) and the job threads otherwise roam the other five cores, with whatever sibling is busy. | The 28% / 73% sibling sharing above. |

## Changes (all off by default)

- `HL_POLL_WAIT=<us>` (default 0): the polling lane waits **blocked** on one word (`hl/bridge/PollGate.h`) that every native
  push, hand-over to a lane and stage/group end bumps, and returns at once when that happens; at the latest after `<us>`
  (try 1000) when a producer did not bump it (a translated push for a job with a hook is bumped after the guest's push; a
  context flagged "not to run" by the guest is seen at the span). Nothing else changes: the take, the lane status, job order and
  the run are the same code; only the wait's end is earlier or the lane off the CPU. A bump with no waiter costs one load.
  The wait runs through the host (`hl_host.c` `cb_block_wait`: a lock and a condition, the thread's virtual core given up as
  a guest sleep does). The word is read before each look for work, so a push between the look and the wait is not lost.
- `HL_SMT_POLICY=1` (default 0; only with 8-12 logical processors, SMT, and a reserved replay core): the presenting thread
  gets the physical core just below the replay's as its own (ideal processor on it, affinity every processor but the replay's
  core), and the job threads (names containing BaseProc or ModuleSystem) get every processor but the replay's core and the
  presenter's. The replay's core was already free of game threads. On 6 cores that leaves 4 physical cores for 12 job
  threads, which mostly wait.

## To validate when the machines are free

1. Function and picture in the three scenes with `HL_POLL_WAIT=1000` (log line `hl jobs: the polling lane waits blocked`,
   `HL_JOBS_LOG=1` counters: polls, wakes; `HL_DISPATCH_CHECK=1`, `HL_JOBGROUP_CHECK=1`: invariants 0).
2. On the PC 3050 under a SPEED lease, Market: CPU per thread (`HL_THREAD_CPU`) of the executors with and without
   `HL_POLL_WAIT`; frame time with each switch alone and both; the order thread's sibling-busy share (WPR) with
   `HL_SMT_POLICY=1`. Also `HL_POLL_WAIT` + `HOS_SHORT_SLEEP_TIMER=1` for what is left of the yield loops.
3. On the 7800X3D the same two, as a sanity check: no loss expected (16 threads, nothing starved).
