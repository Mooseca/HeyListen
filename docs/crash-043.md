# v0.4.3 crash reports: causes, evidence, status (CRASH43, 2026-11-22)

Source: the telemetry server's `signatures` table (read only), 15 signatures of v0.4.3 with 17 reports, and one player log
(report 148766, RX 6800 XT). The lifted code read here is the build of 2026-11-22 in `builder-work/sa/gen` (same lifted
code as the reports' `7a90fd06b3` for the functions below: the host code of `f_80a30a00+0x69` matches the report's offset).
Guest names are `f_<guest address>`; "guest X" in a fault is the address the lifted code used.

Reading the reports: **no register or memory row travels in a report** (`hos_crash_report_line` drops them on purpose), so
what is known of a bad pointer is its value in the fault line and what the lifted code says it was. Nothing below was
reproduced: the owner was playing and no game ran for this work.

## Summary

| Signature | Reports (0.4.3; before) | Where | Cause | Status |
|---|---|---|---|---|
| process exit: `libc++abi: terminating` (player log 148766) | 1 log | window closed, exit | a file-scope joinable `std::thread` (the profile's CPU sampler) destroyed by `ExitProcess`'s static destructors | **fixed** (46f5f103e) |
| `f_80a30a00` +0x1ef x3, +0x376, +0x69; `f_80a31030+0x550` x2; `f_803b44e0+0x607` x2; `hookshot+0x12c89068` (Linux, = `f_80a30a00+0x318`) | 10 (0.4.2: 8) | Crater, Fire, Spirit, Phantom Ganon; main thread and ModuleSystemWorker2-5 | the module system's end-of-frame release walks containers that were freed or overwritten (heap corruption or a use after free); who wrote them is not known | **not fixed, needs repro** |
| `f_8572f300+0x31` x2 (+ `HeyListen.exe+0xd64711` in 0.4.1/0.4.2) | 2 (0.4.2: 14, 0.4.1: 3) | title, first seconds, main thread | `new(0x268)` returned null in nnMain's boot, `memset(NULL)` | **not fixed, needs repro** |
| `f_80a9e750+0x2d4`, `f_83b51a00+0x255` | 2 | title, main thread | a null object (arg of a module constructor; a null vcall target) in the same boot chain | **not fixed, needs repro** |
| `f_83bb8420+0x7b` x2, `f_804fc320+0x36e` | 3 | Crater (SceneLowPriority), Water Temple | the scene's resource release / check meets a resource whose buffer is null and size 0 (reported loaded) or an array overwritten with small integers | **not fixed, needs repro** |
| `f_80ab8e00+0x1b7` | 1 | Hyrule Field, after 504,007 presents | the per-thread allocator's slow path returned null (arena full), the caller does not check and writes the block header at guest 0x3c | **not fixed, needs repro** |
| `KERNELBASE 0xe06d7363` | 1 (0.4.2: 1) | title, "GPU: ?" | `vkCreateInstance` fails, the host falls to the WebGPU renderer, which panics in `wgpu_native.dll` | **fixed** (428ec7ea1): clear fatal, VkResult logged; the reason `vkCreateInstance` fails needs the player's log |
| `mkwvk::tprof_collect+0x5d` | 1 | Hyrule Field | the profile's slots array read before it exists | already fixed on main (d9a3da38f) |
| `renodx-mfgunlock.addon64+0x2b58e` | 1 | Kakariko | third party (RenoDX frame generation addon) | not ours |

By players hit (reports over 0.4.1 to 0.4.3, same code): the **null `new` at the title** (19) and the **module system's
release** (18 over 0.4.2 and 0.4.3) are the two big families; then the scene resource checks (3), the Vulkan failure (2),
the others one each. By certainty of the cause: the exit terminate and the Vulkan fall-through are certain; the rest are
a precise place and a mechanism, not a culprit.

## Player report 148766: "crashes in the first scene"

**The process did not crash.** The log has no `CRASH:` line. Its last lines are `display: window closed, exiting`
(`hos_window_closed_exit`, called by the window's close, so the player or the OS closed the window) then
`libc++abi: terminating`. The first is a clean exit; the second is `std::terminate` with no exception in flight.

Cause: `gpu/vk/profile_run.cpp` held `std::thread sampler;` at file scope. The profile was on (the log has
`performance profile on: CPU sampler running (250 Hz)` at present 3120 and, at the end, the profile's last batch written by
`perf_report_final` with no `performance profile off` after it, so `profile_stop` never ran). `ExitProcess` runs the
renderer DLL's static destructors with the sampler still looping: `~thread` of a joinable thread calls `std::terminate`.
It only happens when the performance profile runs (opt-in telemetry row on), on every exit.

Fixed in 46f5f103e: `perf_report_final` stops and joins the sampler after the profile's last batch (outside the report's
lock), and the file-scope holder detaches a thread that is somehow still joinable. Test:
`engine/tests/test_profile_exit.py`. Not built or run (no lease); the code is small and the test reads the source.

**Could the intro have hung? No, by the log.** 16,680 presents at 60 fps = 4.6 minutes:
- presents 120 to 10,920 (3 minutes): 2 to 6 draws a frame at a steady 60.0 fps: the title screen waiting for input
  (`Select` and `Start` were pressed at log lines 1386-1387);
- present 11,280: one 4.1 fps present (405 draws, "gaps between recordings ... the longest 1686 ms"): a scene load;
- presents 11,640 to 16,680 (about 1.5 minutes): 700 to 1,200 draws, 51 to 60 fps, the game running.
The threads were not stuck (counters and presents moved to the last 5 s). The window was closed by the player, and the
terminate line after it looked like a crash. The RX 6800 XT is also not a candidate for the other families here.
(`storage buffer NOT bound (reads zeros)` repeats in the log: a program bound to a null storage address, not a hang.)

## Family A: the module system's end-of-frame release (10 reports)

Stack in every report: `f_83b78d80` (a job wrapper: runs a delegate on a thread, marks its thread slot) calls `f_82c20a40`
(the module system's frame end for a manager: takes the manager's mutex at +208, walks its list of per-thread contexts) which
calls `f_80a31220(context[+824])` per context; `f_80a31220` releases ten ring-like containers (counts at +1452, +1524,
+1596, ... decremented without atomics, each reaching 0 calls `f_80a31030` for an array of 0x90-byte elements with
0x28-byte sub-elements, or `f_80a30a00`, the element's destructor). Threads: sead::MainThread (inside
`hl_gate_80070b20` / `hl::bridge::Stages::wait` / `JobGroup::run`, so the native module job group), and
ModuleSystemWorker2 to 5.

What the faults show (decoded from the disassembly of `f_80a30a00`: +0x69 is `x8 = load8(x0 + 75)`, +0x1ef is
`x8 = load64([x19+16])`):
- `+0x69`: the element pointer is garbage (non-canonical, reported as -1);
- `+0x1ef` x3 (3 PCs, three GPUs): `[element + 16]` reads as **0x90** (the element size) and the next load faults at guest 0x90;
- `+0x376`: guest 0x10; the log line just before is `skipped an indirect call to 0 (lr 0x80a30ae4)`: the element's callback
  object had a vtable whose first slot was 0, so it was a freed or zeroed object;
- `f_80a31030+0x550` x2: a pointer read as `0xd500465542` and in 0.4.2 `0x16b00465542`: ASCII `BUF` and a NUL, then
  another byte: **data of another object where the array of pointers should be** (the same four bytes on two PCs);
- `f_803b44e0+0x607` x2: `f_803b44e0` is one of the heap entry points `hl_trace.c` gates (`mem_gates`): the crash is
  inside the heap's own free, reading -1 where heap metadata should be: the heap's structure was overwritten;
- Linux `+0x318`: guest 0xfffff00000000000, the same family.
So the containers were freed and their memory reused, or overwritten by someone else, while the release still walks them.
Values seen are zeros, -1, the element size (0x80/0x90) and an ASCII tag: reused memory, not one wrong constant.

Not shown by the evidence: **who writes**. Candidates in the engine, none proven:
1. the back end's write-backs into guest memory (`nvn_gpu_write`) landing in a pool's range after the game freed the pool
   and reused the memory (RX_VK_POOL_FINALIZE is off by default: the back end hears of pools being made, never ended; a
   chunk is retired only by a larger import or pressure);
2. the native module job group (`HL_JOBGROUP`, `HL_MODSTAGES`, `HL_JOBS`, default on since 0.4.0) running a release job
   at another time or on another thread than the guest's order allows (the release is not atomic: it relies on the
   manager's mutex at +208 and on being the only runner per context);
3. a game race that the console's core pinning hid (vcores approximate it).
The family exists in 0.4.2 (8 reports at `HeyListen.exe+0xfe8d...`/`0xfe96...`, same map set), so it is not new in 0.4.3.

**Needs a repro**, with `HL_TRACE=2` (`host/hl_trace.c`): at the crash it says which heap block the faulting address and
each register are in, live or freed, allocated and freed by whom, and which back-end write-back, mirror or import covered
it. Crater, Fire Temple or Spirit Temple for some minutes with it on, and an A/B with `HL_JOBGROUP=0` (or `HL_MODSTAGES=0`)
if the trace names a job. Nothing was changed for this family: no evidence picks one of the three.

## Family B: the title crashes (4 + 19 earlier reports)

`f_8572f300+0x31` x2 is the biggest family over three releases: `HeyListen.exe+0xd64711` (0.4.2: 14, 0.4.1: 3) is this same
function at the title (the offset is stable because the early lifted code does not move). Chain: nnMain's boot
(`f_81222ce0` > `f_80f48c30` > ... > `f_83b79e88` > `f_83b7a838` > `f_83b7b47c` module list) > `f_83bb6eb0` > `f_80c4afa0`,
which does `p = new(0x268, 8)` (`f_8005ebe0`) and `memset(p, 0, 0x268)` (`f_8572f300`): **p is null**, the write
faults at guest 0. In `f_8005ebe0` null comes back when the sead heap manager has no current heap for the thread
(`thread[+136]` is 0 or the heap lookup fails) or the malloc fallback fails (`f_850fd330`, `ENOMEM`). The log of every
report ends at `nvn: window of 3 textures` or a few lines after: the crash is in the first seconds of nnMain, on the main
thread, after the window is made. Hardware in the 0.4.3 pair: RX 580, 16 GB, 2.4 GB swap, window 2560x1440; the 14 in
0.4.2: RX 6700 XT, 32 GB, window 2560x1440 (the same player 14 times, probably). Both AMD with a QHD window; RAM does not
decide it (32 GB with the used-memory report off crashed too).

`f_80a9e750+0x2d4` (4060 Ti, 48 GB) and `f_83b51a00+0x255` (RX 9070, 32 GB) are the same boot (`f_83b7b47c` in both
chains): a null object read at +8 and +0x1030. In both, the last log line is `[ARes Loading 0] prompts: ... icons`,
the new button-prompt files built by `host/prompts.c`; the RX 580 reports end before that line, so the prompts are not
the common cause. The boot's module constructors run while the loading threads start: a timing difference between the
main thread and a loading thread is the open candidate (a thread-local current heap set late, or a module list read
before its entry exists).

Status: not fixed, **needs a repro on the reporter's setup** (QHD window on an AMD card at start-up) or a log with
`HL_TRACE=2`; the cheap next step is `HL_TRACE=2` with the window at 2560x1440 on an AMD card. No evidence
for a change was found in the host: `new` is the game's own allocator.

## Family C: the scene's resource checks (3 reports)

`f_83bb8420+0x7b` x2 (RTX 3050 OEM, Crater, thread SceneLowPriority, two reports, one body kept) and `f_804fc320+0x36e` (4090, Water
Temple, ModuleSystemWorker4) are the same code (`f_8329e940`, and an inlined copy in `f_804fc320`): resources with a count at
+356 (CAS decrement); at zero the manager's `vtable+32` check is called and, when it answers true, the code writes a NUL at
`buffer[size - 1]` where `buffer = [res+56]`, `size = [res+64]`.
- `f_83bb8420+0x7b`: the write goes to guest `-1` (0xffffffffffffffff): **buffer 0 and size 0**, a resource that the check
  called loaded has no data and no size (a failed or empty read reported as success, or a field published after the check).
  Two reports from the same GPU model at the same zone: possibly deterministic on that PC (a file that does not read on that PC: disk, antivirus
  or a missing file in its romfs). The log tail has no `fs:` or `hl stream` line.
- `f_804fc320+0x36e`: after the free call at `0x804fc6dc` the loop reads the next array entry and gets 0x80 (so a read at
  +0x10 = guest 0x90): the array of pointers was overwritten with small integers, as in family A.
Not fixed: the loader's layers (`nn_fs.c`, `hl_stream.c`) were not shown to report success on a failed read (hl_stream's
decode errors go to the translated function). Needs the player's log from the run (`fs:` and `hl stream check` lines) and a
look at that PC's romfs.

## Hyrule Field after 504,007 presents: `f_80ab8e00+0x1b7`

`f_80ab8e00` is a heap's aligned allocation. Its caller (`f_81973300+0xf4ab`, the thread-local work arena of
BaseProcExecutor0, a 0xa8-byte element array) takes the fast path when the arena has room and the slow path
`f_80ab8e00` otherwise; the slow path **returned 0** and the code writes the block's header at `((0 + 64) & ~63) - 4 = 0x3c`
(the fault's guest address). An unchecked allocation failure after about 2.3 hours of frames (the report says 4.8 h
wall time): the arena (or its parent heap) filled. Hyrule Field child at 85% of the VRAM heaps. A leak or fragmentation in a
guest heap over hours; `host/hl_heap_retry.c` is the precedent (a retry in the parent heaps for four call sites of the
OptimizeChangeBank thread), but this site's heap is not known. Not fixed, needs a long run with `HL_TRACE=2` or the heap's
free size logged near the end.

## Vulkan fails, WebGPU panics: `0xe06d7363`

Log of the report: `vk: vkCreateInstance failed`, `rx: the Vulkan back end did not start: WebGPU`, then `wgr_start` inside
`wgpu_native.dll` raises 0xe06d7363 (a Rust panic, as it shows on Windows) with no handler: the unhandled-exception filter
reports it. Same chain in v0.4.2 (one report). The WebGPU renderer is the old TOTKPort one. Fixed in 428ec7ea1: on the default
path a failed Vulkan start ends in `hos_fatal` with "no usable Vulkan driver", `HOS_VK_FALLBACK_WEBGPU=1` (or
`RX_BACKEND=webgpu`) keeps the old way; `vkCreateInstance`'s VkResult is logged with its usual meaning (-9 incompatible
driver, -3 initialization failed, -6/-7 layer or extension). Why Vulkan did not start on that PC (Ryzen 5 5600G, Windows 11
build 26300, "GPU: ?") is not known: the VkResult will say at the next report.

## Not ours, or already fixed

- `tprof_collect+0x5d`: d9a3da38f (on main, 21 Nov): the slots array published after the query pool.
- `renodx-mfgunlock.addon64+0x2b58e`: RenoDX's addon (an `.addon64` loaded by ReShade or the like); not our module.

## What the owner can do

1. A game run at the Crater or the Fire Temple with `HL_TRACE=2` (and, if it names a job, `HL_JOBGROUP=0`), kill after a
   crash: the trace names the writer of the bad container (family A, and the array in family C).
2. For the title family: ask the 6700 XT / RX 580 players for their `hookshot_log.txt` and whether a 2560x1440 window and a
   non-default setting is involved; or try a QHD window on an AMD card.
3. The player of the 3050 OEM: the log of a Crater run, and whether a file of the zone fails to read.

Raw bodies: `E:\OOT\scratch-crash43\b\`.
