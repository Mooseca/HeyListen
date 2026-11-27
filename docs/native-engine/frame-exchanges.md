<!-- Copyright (C) 2026 Sacrappy -->
# Frame exchanges: what one game frame and the renderer give each other (MAP1, 26 Nov 2026, phase 1)

Scope: the renderer's side only. Mechanisms, switches, block addresses and sizes, program keys, ages, defects. Nothing of the game's code or data is in
this file; what the blocks contain and which game functions fill and read them is kept in a local folder outside the repository. Evidence for each
statement is a file and line of this tree at main `7a78745ef`, a log row, or a count from a run; each is marked **proven** or **inference**. Nothing
was run for this phase: the counts are from the logs and notes of 21-26 November (named where used). Written for an engineer who has not seen this code.

Contents: A. the frame's timeline (A1-A7); B. GPU to CPU (B1-B12); C. CPU to GPU, inventory (C1-C7); D. open questions, ranked. Phase 2 (deeper
D and E) waits for review.

## A. The frame's timeline

**A1. Who records.** The game's threads record NVN command buffers in jobs: the module job groups run on the main thread and five ModuleSystemWorkers
(`gfx-record-job.md`), the presenting thread (PT) submits and presents. They call `nvnQueueSubmitCommands` (`nvn_native.c:2854`). Proven.

**A2. Hand-over.** With `HOS_NVN_HOLD=2` (default, `nvn_native.c:1134`) the submits of every thread but the PT are held and replayed ~20 us later by the
"hos held submits" thread, or by the PT before its next submit or present, or by whoever waits (fence wait, finish, flush, event poll). The PT's own
submits go straight in. Both end in `submit_q` (`vk_replay.cpp:9641`). Proven.
- Order thread **off**: `submit_q` takes the capture (`memory_capture_submit`, `vk_memory.cpp:2970`) and replays on the submitting thread
  (`submit_job` -> `run_submit` -> `replay_handle`).
- Order thread **on**: `ot_submit` (`vk_replay.cpp:9585`) takes the capture, gives the submission its value, tags it with the game's frame clock
  (`rb_note_value`), and `ot_push` (9290) hands a `JOB_SUBMIT` to the order thread; the caller returns. Job kinds: submit, present, texture and program
  release, texture and sampler registration (9073-9097), so registrations stay in order with submits.

**A3. Replay of one submission.** `submit_job` (5918) -> dry pass on one thread, then segments of about 160 draws recorded in parallel by workers
(`par_threads`, 3400: 4 workers with 8+ hardware threads, 5 with 16+; `RX_VK_EARLY_GPU=1` default sends each segment to the GPU as soon as it is recorded,
3760). The last part (`memory_end_submission_of`, `vk_memory.cpp:9588`) records, in this order: the readback ring's staging copies (`rbring_flush`, 9741),
the write-backs (mirror to guest memory), the guessed heads, the diff, the staged write-backs. Proven.

**A4. Present.** `nvnWindowAcquireTexture` (`nvn_native.c` 2980) is where the limiter sleeps. `nvnQueuePresentTexture` (2999) flushes the held submits and
calls `present` (`vk_replay.cpp:9804`): it adds 1 to `rb_clock` (only when the readback ring runs on the game's clock: order thread or
`RX_VK_FRAMES_IN_FLIGHT`>1, 9813); order thread on: a `JOB_PRESENT` (`ot_present`, 9609; the call waits when `RX_VK_ORDER_AHEAD`=2 presents are handed
over and not shown); order thread off: the PT takes `sync_order_mu`, `drain(0)` (whole frame), `do_present` (7498), which adds 1 to `presents_now`.
Then `hos_vi_native_presented` (`nn_vi.c:535`). Proven.

**A5. Limiter, held present, clocks, real-time step.**
- *Limiter* (`nn_vi.c:187-330`): the acquire sleeps until the display time of the frame `active` back (3 textures); the period is `1e9*m/limit`
  (`fps_period_ns`); a frame later than its time waits for nothing and the next time restarts from now (no catch-up burst). Proven.
- *Real-time step* (`realtime_step`, `nn_vi.c:297`): each present writes the rate of the last five display intervals into the graphics module's nominal fps, which
  the game's frame step reads (step at most 1/15 s, at least 1/60 s). `HOS_REALTIME_STEP=0` gives whole steps. Proven (comment and `main-loop.md`).
- *Held present* (order thread only, `ot_main` 9099, `ot_present_run` 9046): a present job is held while a CPU signal that a stopped submission waits for is
  not made (`cpu_wait_open`) or a queue is stopped before it; the thread runs the jobs behind it meanwhile; forced when the next present arrives or after
  `RX_VK_ORDER_SIGNAL_MS`=2000. Log lines: `order thread: the present after N forced`, `mtrace hold present` (`HL_METER_TRACE`). Proven.
- *Three clocks, not one*: `rb_clock` (game present calls; the ring's clock with the order thread), `presents_now` (frames the replay has shown; the ring's clock
  without it, `rb_frame_now` 9986), the host's pacing count (`nn_vi.c`). With the order thread `rb_clock - presents_now` is 0..2. A ring read at game frame c
  waits until `presents_now >= c - lag + 1` (`rb_wait_staged` 9995, 200 ms bound). Proven by code.

**A6. Diagrams.** M = game threads, PT, H = held-submit thread, W = recording workers, OT = order thread.
```
ORDER THREAD OFF (release default since 26 Nov; commit 0e10356ae on integ/main-1126h and i, not yet in main)
 M : jobs record -> submit (held) -> H replays it: capture, dry pass, [W segments], end part (ring copies, write-backs) -> GPU
 PT: acquire (limiter sleep), own submits inline, present: drain(0), do_present, vkQueuePresentKHR
 reads of GPU results happen in M's jobs; the replay of frame f is complete when frame f+1 reads: ring age = lag (2)

ORDER THREAD ON, early read-back (RX_VK_RB_EARLY=1, join 5, ring lag 3)
 M/PT/H: capture, ot_push, return.   OT: replays submits in order; copies behind each 0x3980 writer; present job held until the CPU signal is made
 M reads: R1-R3 from the ring (age 3; wait for the replay to have shown present c-2); R4 from the early copy; other ranges: join this thread's jobs

ORDER THREAD ON, RX_VK_RB_EARLY=0 RX_VK_ORDER_RB_JOIN=3 (clean by the owner's eye)
 as above, but R4 and every range that ever had a write-back waits for ALL jobs handed over before the read (9412-9416); R1-R3 stay on the ring
```

**A7. Waits that tie the CPU to the replay (order thread on).** Fence waits (`ot_wait_for`, 9568: polls are told "not yet"), `nvnQueueFinish`, catch-ups and
texel reads (`ot_join_all`), event polls (`nvnEventGetValue` -> `rx_order_join`), readbacks (B), the present slot, and `rb_wait_staged`. The present poll
(link-register 0x805904a0 / 0x80590530) is answered at once (`HOS_PRESENT_NOWAIT`). `ot_watch` (9245) logs a done mark stuck 3 s or no present for 5 s. Proven.

## B. GPU to CPU: every block the game's CPU reads that the GPU wrote

**How the CPU asks.** `nvnMemoryPoolInvalidateMappedRange` / `nvnBufferInvalidateMappedRange` (`nvn_native.c:421, 553`) end in `invalidate` (`vk_replay.cpp:6363`).
Its order, proven: learn the range (`rbring_note_read`, `rbearly_note_read`); if the ring serves it, skip every wait; if the early copy serves it, skip the old waits;
otherwise `ot_join_readback` (order thread), then the ticket wait, `memory_cpu_reads`, the write-back wait (`wait_recorded` / `wait_value`, strict bound for the meter's
page), `rbring_apply`, the meter hold, then the texel flush for textures the GPU wrote. The only other ways the game sees GPU work: `nvnTextureReadTexels` (about 0 in
play), `nvnEventGetValue` / fences, and the reports below.

**The list of read sizes** (invalidate sites by return address, sites counted by `HOS_RB_LR_LOG` in `build/s5/expo1-diag1` (301,549 calls) and `rb2-who-m` (252,441),
21 Nov builds, Market and warp tour; proven): 0x40 (75%, two sites), 0x2000 (9%, two sites), 0x9b040 / 0x8b040 / 0x44b040 (5%, one site), 0x1040 (3%, three sites), 0xc0
(two sites), 0x1b580 (1%, one), 0x3980 (3%, four), 0x80 (55 calls, one site, new), and a second 0x40 site (833 calls, new). Of these the last two were not in the 21 Nov ledger;
the list may still be incomplete for other scenes (open question 7).

| id | block | size, address or pool | GPU writers (program keys) | bindings a frame | read by (game function, thread) | game use |
|---|---|---|---|---|---|---|
| B1 R1 | exposure meter ring A, B, C | 0x1040 each: 0x113c88b000 (A), 0x113c88e000 (B), 0x113c891000 (C); 0xc0 companions | `592079442d7129da` writes A; `435a0138b9013040` writes B; C is never written; compute 1x1x1, one clear + one dispatch each, every frame | 1 + 1 | f_80357060 (7 callers), module workers and main | the meter's averages feed CPU light, fog and effect parameters (static scan; proven that the CPU consumes them, which parameter is inference). Block A reads zero most of the time in the day Field (1485 of 1835 reads: the program's own result, EXPO3) |
| B2 R2 | 0x40 result slots | 0x10508d8000, 0x105183f000, 0x10517fc000, 0x10518e4000 +0x40 (by scene), many ranges | `612a27de13e44e79`, `6214a97bec4cc0bf`, `0b4780da69a698b5` | 63 / 30 / 11 reads (Market / Kakariko / Field), about half hit ranges no program wrote | f_80354060, f_8007c120's job | a per-object GPU sample count turned into a 0..1 fraction (proven); what the fraction drives is not followed (inference: fades) |
| B3 R3 | 0x2000 pair | 0x113c895000 / 0x113c897000, alternate by frame | `6ccba775ea111ee9`, `abf896d5f74923a9`, `bc3ae540cf7abb61` | 2 reads a frame | f_8034f440 and its caller in f_8007c120 | small integers per request; zero in 96% of Market reads (proven); use not followed |
| B4 R4 | culling / view block | 0x3980 in 0x113b623000 and 0x113b628000, alternating by frame | eight compute programs in ONE job a frame, in order: `b612216258832b9c`, `44511d69b52282ad`, `93be496778e568b5`, `6344c53d07706e30`, `abccf81b45c5eb50`, `7984161db3e053b5`, `3018813b775edcb6`, `fd958faab99f20a2`; a ninth (`f78bce74159566cc` / `fcd994b5b6761630`) in some jobs | 8 per job (6+2 by thread in 66 jobs, 8+0 in 7); the job is the frame's last submission before the present, on queue 0x101004133020 | f_80365f00 (called by the culling job f_800998a0) | camera and frustum data, per-tile data and a frame stamp word; used for lights, ground fog, vegetation (inference; layout in the local map) |
| B5 R5 | big lists | 0x9b040, 0x8b040 (two halves 0x117cf04000 / 0x117cf9f040), 0x44b040, pool 0x1178000000 | the same writer job as B4 | several | f_80362ff0, a frame later | instance / draw data (inference); audit 3530 reads, 0 stale |
| B6 R6 | particle / debris state | 0x1b580 at 0x115bcde000 / 0x115bcf9580 (4 MB pool) | GPU compute, also CPU-appended | 1 | f_80364080 | cut-grass leaves (issue 50: inference); one STALE audit read seen |
| B7 R7 | occlusion reports | counter types 0, 1, 16 | none: written ON THE CPU in stream order at replay (`RX_VK_OCC_FIXED`=4096) | ~963 reports, ~445 conditions | render conditions in the dry pass | "everything visible" (proven, `occlusion.md`) |
| B8 | small ring-slot sites | 0x40 (833 calls) and 0x80 (55 calls) | not identified | | f_807068e0, f_809f43c0 | per-frame ring helpers (inference) |
| B9 | textures the GPU rendered | texel flush in `invalidate` (`texture_flush_to_guest`) | render targets | ~0 | none seen | none seen |
| B10 | events and fences | `nvnEventGetValue`, `wait_core` | the stream | many | main thread, PT | order |
| B11 | write-back of GPU-written pages (not an invalidate) | every written binding | every compute / pass | 10.8 spans, 53 MB a frame on the 5070 | whatever reads the memory next | see B12 |
| B12 | the protocol's own read-and-reset (meter, R2) | `memory_rb_refresh` | | 0.18 ms a frame (5070) | | the CPU's zero back into the mirror |

Counts per section: A 12 exchanges (A1-A7 with 6 job kinds), B 12, C 7.

### B-mechanisms (what serves a read), by class

**The ring (`HL_RB_LAG`, default on, `rb_ring.h`, `vk_rbring.cpp`; classes R1 meter, R2 0x40, R3 0x2000).** A range the CPU reads is learned; a binding for writing that is
exactly that range is not written back; the submission's end copies its bytes into an engine-owned 4 MB ring with the tag `rb_tag_for(value)`; a read at frame c applies the
newest unapplied entry with `tag + lag <= c` (`rb_ring::pick`), waiting only if the GPU is not past it (`HL_RB_LAG_WAIT_MS` 200). Ranges nothing writes are answered with no wait after
8 reads; a tainted range keeps its write-backs; a range moved to the old path by a direct write is taken over again with a settle value (`rb_ring.h:106`). **Age:** order thread off:
lag 2, every applied R1 entry exactly 2 frames old (`readback-ring.md` 4.4, 3000-read windows 0/2400/0/0); order thread on: lag 3 (`vk_rbring.cpp:35`), with the clock `rb_clock`.
`HL_RB_LAG=1` is the old path bit for bit (0 differences in ~90,000 reads); `HL_RB_LAG=0` is the old waiting path (the owner: more and stronger flicker, w7r arm 3). Branch
`fix/expo3-rbclasses` adds `pick_steady` (`HL_RB_PICK`) and `HL_RB_CLASSES`; not in main. The meter's block with no new entry gets the last applied value back (kind 2).

**The early read-back (`RX_VK_RB_EARLY`, 1 with the order thread, `vk_rbearly.cpp`, `rb_early.h`; class R4, size 0x3980 only, 8 ranges at most, 32 slots each).** Every written binding of a served range
takes the next slot; a copy plus a stamp (`vkCmdFillBuffer` of the sequence number) are recorded right behind the dispatch (`rbearly_after_dispatch`); the binding's write-back is left out; the copy is
"final" when the job's binding count reaches the learned count (the largest of the last 8 jobs: 8). A read needs the job `ot_present_sub` (the last submission before the newest present): it takes the
newest final slot of that job or later, else waits (30 ms, then 200 ms, then guest memory as it is: "STALE") for the order thread's recording and the GPU's stamp, writes it into guest memory ONCE, and
leaves guest memory alone for a read with nothing newer. `RX_VK_RB_EARLY=2` runs the old path and compares. Age: 1 game frame (the target job is the previous frame's). Known: "final" is the 8th
writer; the exact value (join 3, below) was the copy before the 7th (`RX_VK_RB_EARLY_BEFORE`, off); a ninth writer in some jobs makes the 8th copy final early.

**The order thread's joins (`ot_join_readback`, `RX_VK_ORDER_RB_JOIN`, default 5).** 0 none; 1 this thread's jobs; 2 all jobs; 3 all jobs for a range that ever had a write-back, else this thread's; 4 all jobs for 0x3980
only; 5 this thread's jobs plus the last whole frame's jobs up to the learned place of the 0x3980 writer in its frame (`ot_note_r4_writer`, 9429). Ring-served and early-served reads skip it.

**The write-back paths (`vk_memory.cpp`).** Every written binding queues a write-back (`gpu_buffer_bind`, 7305; order of tries: early copy, ring staging, else `writebacks`); at the submission's end it is copied
mirror to guest memory. Variants: *lazy* (`RX_VK_WB_LAZY`, a pool never read or written by the CPU keeps its GPU words in the mirror; `kLazyWarm`=600 submissions), *eager* (`RX_VK_WB_EAGER=1` all;
`RX_VK_WB_POOL_EAGER` default on: the first CPU write to a game pool makes it eager; `RX_VK_WB_SMALL_EAGER_KB` 4096), `RX_VK_WB_MAX_KB` (bindings above a size are not written back), *guessed heads* (a bare
storage entry's guessed head is written back checked, never over a CPU write: `RX_VK_WB_GUESS_CHECKED`, on the GPU `RX_VK_WB_GUESS_GPU`), the diff (`RX_VK_WB_DIFF`, compare against a shadow), staged
write-backs (`RX_VK_POOL_MIRROR`). *Strict* waits: `RX_VK_READBACK_STRICT` and `RX_VK_STRICT_BOUND` (4 ms, for the meter's page). The wait of a read for a write-back: `memory_writeback_value` gives the value
to wait for, `wait_recorded` waits on the recordings' timeline, `wait_value` for the GPU.

### B-ages in one table (frames between the GPU's write and the read; proven where the log is cited, inference otherwise)
| class | order off | order on, default (early, join 5) | order on, RB_EARLY=0 + JOIN=3 |
|---|---|---|---|
| R1-R3 | 2 (ring, lag 2) | 3 (ring, lag 3) | 3 |
| R4 | 1 or 2, timing dependent (inference; RB_PROF: 0 pending) | 1, value after the 8th writer | 1, value as the copy before the 7th in 218 of 300 reads (k3) |
| R5, R6 | 1 (write-back landed) | 1 (JOIN=5 waits this thread's jobs) | 1, but every such read waits for all jobs |


### B-stamp: the 0x3980 block carries its own frame stamp (MAP1 part 2, 26 Nov evening; builds map1a / map1b on branch `fix/map1-stamp`, `HL_STAMP_TRACE=1`)

Proven (a `vk: stamptrace` row per read: the stamp handed to the game, the reader's frame counter read from guest memory at the call, the reader's rule, the stamps of the copies in the range's slots):
- The block holds one 32-bit frame stamp (offset 0x1540). It is written by the eighth of the job's eight writers (`fd958faab99f20a2`): copies 1 to 7 of a job carry the previous
  stamp of that range, the eighth the new one. No CPU code writes it. The ranges alternate, so a range's stamp rises by 2 between two of its jobs.
- The game's reader keeps a frame counter in the view object it fills. On each read it accepts the block of the first buffer only if the stamp equals the counter minus 1; otherwise it
  tries the other buffer and accepts a stamp equal to the counter minus 2; if neither matches it keeps the copy it already had.
- Age the game gets, Hyrule Field, 60 limit, EXPO3's walk, 200 s (counts of frames; reader = first buffer, age 1; other buffer, age 2):

| mode | frames | age 1 | age 2 | neither | age changes per 1000 frames |
|---|---|---|---|---|---|
| order thread on, early read-back (default of the branch) | 5051 / 5602 / 8814 | 99.2% / 97.9% / 99.1% | 0.7% / 1.7% / 0.8% | 0.1% / 0.4% / 0.1% | 14 / 38 / 17 |
| order thread on, `RX_VK_RB_EARLY=0 RX_VK_ORDER_RB_JOIN=3` | 5243 | 9.8% | 90.0% | 0.2% | 147 |
| order thread off | 7994 | 0.2% | 99.8% | 0.1% | 4 |
| `HL_STAMP_PICK=2` (order thread on) | 8055 / 8823 | 0.01% | 99.98% | 0.01% | 0.4 / 0.3 |
| `HL_STAMP_PICK=1` (order thread on) | 5633 | 99.4% | 0.5% | 0.02% | ~11 |

The early read-back therefore hands the game a block one frame fresher than both clean modes do (age 1 against age 2), and rarely steps back to age 2. Join 3 steps between the two ages
far more often (147 per 1000 frames) and is clean by the owner's eye, so the stepping alone is not the flicker's cause. The scripted walk does not reproduce the owner's flicker (9-18 luma
jumps in 2500-4400 shots in the default arm, like the clean arms): only his eye can judge a fix.
- Why the early path rejects 0.8-2.1% of its first-buffer reads: in about 0.5% of jobs the copy marked "final" (highest bind order) is not the eighth writer (two recording threads bind out of
  command order), and in some frames the reader and the writer job are one range out of phase.
- `HL_STAMP_PICK=2` (branch `fix/map1-stamp`, tip a3d1708b1): serves the first buffer a block of 3 frames ago, which the reader refuses, so it always takes the other buffer's block of 2 frames ago:
  the clean modes' pattern (99.98% age 2) with the order thread on. `HL_STAMP_PICK=1` serves the fresh block (age 1) and does not remove the stepping. The copies waited for cost about the same as
  today's (0.7-0.8 ms each, 25-30% of reads). Not judged by eye yet.


### B-writers: what each of the eight programs changes (build map1c, `HL_STAMP_DUMP`, 47 complete jobs, Hyrule Field; proven)
Words of the 3680-word block changed by each writer's copy against the copy before it: writers 1 to 6 (`b612216258832b9c`, `44511d69b52282ad`, `93be496778e568b5`, `6344c53d07706e30`, `abccf81b45c5eb50`,
`7984161db3e053b5`) change none; writer 7 (`3018813b775edcb6`) changes about 380 of the 1152 per-tile words and 430 of the 576 per-tile depth words a job; writer 8 (`fd958faab99f20a2`) changes about 24 words of the
camera header and the stamp. About 3000 words (projection constants, a template, the grid size, a zero tail of 1728 words in this scene) are changed by none of them. Layout of the block: header 144 words, tile
pairs 1152, constant template 64, stamp header 12, depth grid 576, tail 1728 (detail in the local map).
Consequence for the early read-back (renderer side; deduced from the stamps, expo3e itself was not re-run: inference): the copies behind writers 1 to 6 are the block of the SAME RANGE'S PREVIOUS JOB (two frames old), which is what the clean modes' first-buffer read gets
(EXPO3's "the exact read equals the copy before the 7th writer") and what the game's reader refuses; the block the game uses in the clean modes is the OTHER range's complete block. EXPO3's expo3e served the copy
before the 7th writer on both paths: the other range's block then carried a stamp the reader also refuses, so the reader kept its previous data for a while (the grass flickered, then recovered, w7v). That run
therefore did not test "the exact block"; `HL_STAMP_PICK=2` is the faithful emulation (first range: the old block, other range: its complete block).


### B-R5: the 0x9b040 "stale" reads are harmless (MAP1 phase 3, corrected; `RX_VK_ORDER_RB_AUDIT=1`, `HL_AUDIT_ALL=9b040`, build map1e; proven)
Audit = after each read the ring does not serve, wait for every job handed over and see whether the range's write-back value moved ("stale"). In the default (order thread on, early read-back, join 5) the two ranges
`0x117cf04000` and `0x117cf9f040` (+0x9b040) are flagged stale in 2060 of 2539 and 2039 of 2539 reads (81%, 80%); the other R5 ranges 0 to 1. With `RX_VK_ORDER_RB_JOIN=3` and the early read-back on, 0 in 1897.
**But the bytes the game reads do not change**: in a second run (6778 audited reads of the 0x9b040 ranges) the first four words of the range, captured as the game got them and again after the order thread caught up, were identical in 6778 of 6778 reads,
stale or not. The reader copies only a few count words from the list headers (the lifted code: word 3 of up to three 16-byte headers) into its own structure and zeroes them; the 61 records after the header are consumed by the GPU. The write-back value
advances with every frame's job even when the header bytes do not change, so the audit's flag overstates. R5 is not a cause of the flicker; the join-3 audit result is a property of the audit, not of the picture.
List content (dump): header (4, 0, 0, 61), then 61 records of 64 bytes at offset 0x4b040: three unit vectors and a position with w = 1 (object instances, inference). Cost of the join in the audit run (early read-back on, join 3): about 1 wait per frame of about 1.1 ms (592 of 4217 reads waited, 1.2 ms a frame), against none in the default and 674 waits / 8 ms a frame with join 3 and the early read-back off.
Pages the replay read from guest memory after their capture's copy (`HL_LATE_TRACE`, order thread on, 2655 reads, 25 distinct pages): in every one the bytes equal the capture's copy: also harmless in that run.


### B-join: which reads the join makes wait, and whether their used bytes ever differ (MAP1 phase 3, branch `fix/map1-joinmask`, build map1h; Kakariko still, order thread on; proven)
Switches added there: `RX_VK_ORDER_JOIN_STATS=1` (per read size: reads that reached the join, how many waited, mean and worst wait), `RX_VK_ORDER_RB_JOIN_MASK=<hex>` (per class: bit 0 meter 0x1040/0xc0, 1 the 0x40 slots, 2 the 0x2000 blocks, 3 the 0x3980 block, 4 the big lists 0x9b040/0x8b040/0x44b040, 5 the 0x1b580 state, 6 the 0x80 site, 7 any other size; a class in the mask takes the join of `RX_VK_ORDER_RB_JOIN=3`, the others join 5), and in the audit one row per size: reads, behind, flagged stale, and reads whose USED bytes (the first 64 bytes, the first 64 KB) differ before and after the order thread catches up.
Reads that reach the join with the ring and the early copy on (the others are answered without it): only the big lists (0x8b040, 0x9b040, 0x44b040: about 856 reads each in the run), 0x1b580 (428) and a few 0x40.
| size | reads | join 3: waited (of those) | mean / worst wait | default (join 5): waited | used bytes differ, default (64 B / 64 KB) |
|---|---|---|---|---|---|
| 0x9b040 | 856 | 396-398 (46%) | 1.5-1.6 ms / 3.4-5.6 ms | 0 | 0 / 0 of 855 (flagged stale 397) |
| 0x8b040 | 856 | 0 | - | 0 | 0 / 0 of 856 |
| 0x44b040 | 855 | 0 | - | 0 | 0 / 0 of 855 |
| 0x1b580 | 428 | 0 | - | 0 | 0 / 0 of 428 (1 behind) |
| 0x40 | 2 | 1 | 0.28 ms | 0 | not audited |
| 0x1040, 0x2000, 0x3980 | 0 (ring / early copy) | | | | |
In the owner's own run (Hyrule Field, early + join 3, `w7x-ej3`): readbacks waited 619 and 602 of 4213 and 4210 per 600 frames, 2.7 ms a frame in all; the default has none. So the ONLY read whose wait matters is the 0x9b040 pair's (one wait of 1.5 ms about every second frame), and its used bytes never differ in the default: the cure of join 3 is not a data cure of any audited class.
Flash detector (Mooseca's settings, `RX_VK_FLASH_*`, `RX_VK_SHOT_EVERY=1`), Kakariko standing still, 150 s: order thread on 4 flashes; early + join 3: 1; default with the audit on (its own catch-up wait paces the thread): 2. Walking in Hyrule Field the detector saturates (400 flashes in both arms: content motion). A flash frame is brighter over the whole picture (+3 to +16 of 255, the right and lower part most) for one frame.

Per-class arms (Kakariko still, 270 s, order thread on, flash detector as above, build map1h): default 3 flashes, join 3 on every class 4, join 3 on the big lists only (`RX_VK_ORDER_RB_JOIN_MASK=10`) 5, join 3 on every class but the big lists (`ef`) 6. At 3 to 6 flashes in four minutes the detector does not separate the arms here; the mask joins only its class (the big lists waited 401 of 856 reads at 1.49 ms in the first, nothing waited in the second). No class stands out by this measure or by the used-bytes comparison (0 differing reads in every audited class); the owner's clean window with early + join 3 is not reproduced by the detector on this machine.

### B-decisive: join against sleep against off, with the strict flash count (Kakariko standing still, order thread on, 600 s each, build map1i; proven)
Counting only flash lines where at least 20 of the 2304 cells got brighter (the weak lines and the "region flash" lines occur in every arm, order off included): default (join 5) 5, `RX_VK_ORDER_RB_JOIN=3` 1, a plain 1500 us sleep taken instead of the join on the 0x9b040 reads when the order thread is behind (`RX_VK_ORDER_RB_SLEEP_MASK=10`; 28817 of 183000 reads slept) 5, order thread off 0. Shorter arms agree (150 s: on 4, early + join 3 0; 270 s: default 2, join on all 2, big lists only 1, all but the big lists 0).
So the cure is the dependency the join makes (every job handed over replayed before the reading thread goes on), not the delay: an equal sleep does not cure. No audited class's used bytes differ in the default, so the join orders something later in the same thread's step. Hypothesis (inference, not measured): the reader zeroes the list headers after reading them (read-and-reset of the GPU's append counter) and the zero can be overtaken by the late write-back of the writer's job when the order thread is behind; the readback refresh that carries a CPU zero back into the mirror covers only ranges read with at most 0x4000 bytes, and the 0x9b040 ranges are larger. A measure that would decide it: log the mirror's header word before each dispatch of the list's writer (expected 0), default against join 3.


### C-detail: the cost of each CPU-to-GPU step per frame (Hyrule Field walking, order thread on, 60 limit; the log's own counters; proven)
- Capture (per submit, about 6 a frame, on the submitting thread under `submit_order_mu` with the order thread): 0.10-0.11 ms all, of it the texture shadow 0.09 ms; 24 capture buffers kept (153 MB), 44,379 texture pages copied over the run; copies by claiming on the helpers.
- Mirror syncs: 143 regions and 0.72 MB a submit, one scatter dispatch with 187 entries (0.73 MB, the readback refresh included); about 4.96 MB in 990 copies a frame; every dirty page is served from a capture (0 from live guest memory in 600 submits).
- The replay's categories a frame (they overlap): draw 7.79 ms, submit 5.63, commands 3.08, descriptors 2.86, programs 1.12, memory sync 1.04, dispatch 0.67, present 0.39, pipelines 0.26, queue submit 0.24, texture lookups 0.12, uploads 0.01.
- Uniform updates: 80 a frame, 56 overlays; the others written at the end of the recording with two full barriers. Write-backs: 8.4 MB a submit copied (1.4 MB left in the mirrors); by kind, MB a submit: outside the game's pools 0.52, pools the CPU reads 1.58, other written pools 5.16, uncached 1.14. Uploads: 0.2 to 3.0 a frame (0.1-0.9 MB), 2527 textures (2472 MB) resident.
- Where the stutters live (cited, not remeasured): the 3050's readback waits on the 0x3980 reads (phase "record": the read waits for the replay to record the write-back; 110-125 hitches a tour), texture uploads with page faults, and render time the log does not split (`stut3-stutters-3050.md`); on the owner's 23 minutes page-fault stutters are 132 of 223 over 50 ms and the Market's entry holds 40 of its 53 (`stutters-owner-integ4.md`).

### A-pacing: where the 60 limit waits (proven by code)
The limiter sleeps only at the acquire, until the display time of the frame three back; a frame longer than the period waits for nothing and the next time restarts from now. `HOS_NO_PACING=1` removes the sleep. The "Frame pacing" option (`opts.pace`, `RX_VK_PACE`) belongs to the frame-generation presenter: each shown frame, the game's and the made ones, gets a place on an even line of the recent frame time, an early frame waits for it, never more than one game frame behind; off, frames are shown as they arrive. With frame generation off nothing else reads the option (grep: `vk_framegen.cpp:490` and the menu presets). The held present adds no sleep to the game's thread; it can delay the showing of a frame by the jobs the order thread runs behind it. With the order thread the game runs one frame ahead of the replay at the culling reader (f - p = 1 at 96-98% of reads; 0 with the thread off or join 3).

### B-fix: the first fix attempt, olj1 (branch `fix/order-rb-list-join`, tip cf36bb34c; proven numbers, not proven as a cure)
`RX_VK_ORDER_RB_LIST_JOIN` (1 with the order thread, 2 every job, 0 off; bounded by `RX_VK_ORDER_RB_LIST_WAIT_MS` 200): the read of the big lists waits until the newest present's last submission is replayed.
- Flash detector, Kakariko still, 600 s each: default 5, olj1 4, every job joined for all classes 1, equal sleep 5, order off 0; confirming mask arms 2 (lists only) and 2 (everything but them). Single digits: only the order off and join-all arms differ from the default with any weight, and olj1 shows no improvement.
- The header trace (list header words at each read and present; Kakariko still, count constant at 53): the order thread is behind the writer job at 10,700 of 11,976 reads in the default and at 0 with join 3; the header is zero at 96% of presents in the default and non-zero at 50% with join 3 (the new count has landed). The trace does not show an overtaken zero and does not refute it: the count does not move in a still scene.
- Cost of olj1 against join 3: Kakariko 0.89 waits a frame of 0.87 ms (0.78 ms a frame) against 0.92 of 2.73 ms (2.5 ms a frame); Market with the camera turning 0.66 of 0.49 ms (0.32 ms a frame) against 0.91 of 0.98 ms (0.89 ms a frame). Five starts: all reached play, none hung; five reads gave up at the bound, all at the end of a run.
- A form with no wait exists (a ring class for the three sizes: a 16-byte copy at the writer's dispatch, no write-back of the range, the reader answered two or three frames late): about 10 lines, risk the age of the count.

## C. CPU to GPU, inventory
C1. *Capture* of the pages the game wrote, at each submit (`memory_capture_submit`, 2970; copy helpers; `RX_VK_SYNC_CAPTURE`=1). C2. *Mirror syncs* (`mirror_sync`, 6259): dirty pages from the capture, earlier
captures or guest memory, before the segments (presync) and at bindings; scatter dispatch. C3. *Uniform updates*: `NOP_UPDATE_UB` into `ub_updates`, written at the end of the recording
(`flush_ub_updates`, vk_replay.cpp:2208) or overlaid at the bind. C4. *Readback refresh* (B12). C5. *Texture uploads* (first and re-uploads, `memory_as_submitted`). C6. CPU event signals, registrations, report
counters written on the CPU. C7. The meter's companion blocks. Measured in play (Hyrule Field, order thread on, `d-dump` run): 80 uniform updates a frame (56 overlays), 6 submits a frame, 143 mirror regions and 0.72 MB synced a submit, 0.1 to 0.9 MB of uploads a frame, 8.4 MB written back a submit; 2.72 M replay reads of guest memory as submitted, of which 308 K took a page written after its capture. Details in the local map; relative timing: C1-C3 happen at the submit (order off: the submitting thread; on: the capture at hand-over, the rest on
the order thread, so reads falling back to guest memory can see the NEXT frame's page, counted by `replay reads of guest memory as submitted`).

## D. Open questions, ranked (the measure that would answer each)
1. What differs for the game between order thread off / join 3 and the early read-back, beyond the 0x3980 value? New: the early read-back gives the reader a block ONE FRAME FRESHER (age 1) than the clean modes (age 2); everything else
   the game computes from this block (the camera it was made with, the lights and fog) may be built for age 2: what else in the frame is one frame behind (the view matrices used with the tiles, the light lists, the fog)? Measure: log, per frame, the stamp of the view data the culling job itself uploads and the stamp of the block it reads; compare in each mode. EXPO3's inference: join 3 makes every read-back with write-backs wait for all handed-over jobs,
   so those reads are a frame fresher and the CPU is paced against the replay. Not the held presents, not the lag, not the 60 limit (`measures-2026-11-26.md`). Measures: (a) order on, join 3, early read-back
   off, ring lag 2 and lag 3 (does the ring age matter?); (b) `HL_RB_CLASSES` masks one class at a time on the expo3 branch; (c) log `rb_clock - presents_now` at every R4 read in each arm.
2. Why does the join 3 value of the 0x3980 block equal the copy before the 7th writer when the end-of-job block holds the finished data? Dump, at one read: guest memory after the join, the 8 early copies, the
   mirror at the submission's end; compare per word group.
3. Which program stores the block's frame stamp, and what does the game do when the stamp is not the expected frame (the reader tests it)? Log the stamp of every early copy.
4. Who reads the per-tile depth data in the block? A static scan plus a load trace.
5. What each of the eight programs computes (shader dump of the keys; per-program diff of the copies, which the early ring already holds).
6. The consumers of B2 and B3's results (loads of the object fields the fetchers store).
7. Is the list of read sizes complete? A fresh `HOS_RB_LR_LOG=1` run in the Field, Kakariko, Kokiri (gate: chain14.done).
8. Contents of B5 and B6.
9. The hang at start of `RX_VK_RB_EARLY=0` (2 of about 8): an unbounded `ot_wait_until` in `ot_join_readback` with a held present (EXPO3's inference). Bound it and count.
10. The ninth writer of the 0x3980 range in the warp tour: the learned count per job kind.

## E. The replay's CPU path (MAP2, 27 Nov 2026; read from the code of main aba453fcf and the documents, nothing run)

Evidence: **P** proven (file and line, or a number with its source), **I** inference. This is the renderer's side of one frame: what the replay does on the CPU, in order, and where it could be cut. Machines: PC 3050 = i5-10400F + RTX 3050, 5070 = Ryzen 7 7800X3D + RTX 5070.

### E1. What the shipped replay is (and a pitfall)
- The game turns on, unless the environment sets them, a list of switches that `docs/SWITCHES.md` shows as "off (unset)": `host/hos_main.c:521-533` (RX_VK_SEG_EARLY, MSYNC_FAST, DRY_LEAN, WORK_LOCAL, SEG_SETUP_PAR, CAPTURE_PRECOPY and others). So the replay of a big command buffer is `replay_handle_early` (`vk_replay.cpp:4295`), not the older loop of `replay_handle` (`:4713-5158`) that the older documents describe. **P**
- `RX_VK_SEG_SETUP_PAR` (segment command pools reset and begun by the recording thread) is read only in the older loop (`:4898`); the early path begins every segment's command buffers on the replay thread (`:4339-4365`). **P**
- With the order thread off (the release default) the replay runs on the thread that submits (the Presentation Thread, or the held-submits thread), under `replay_mu`, pinned while it replays to the host's reserved core (both its hardware threads, `hos_thread.c:825-866`, `vk_replay.cpp:5499-5525`). The recording workers (4 on 8 to 15 logical processors, `vk_replay.cpp:3400`) have no affinity (`:3468`). **P**

### E2. One frame, stage by stage (S serial, P parallel)
| Stage | Thread, lock | S/P | Per frame | Cost (machine, source) | Counters |
|---|---|---|---|---|---|
| 0 capture of the game's writes (`memory_capture_submit`, `vk_memory.cpp:2970`) | submitting thread, `sync_order_mu`, copy helpers | S + helpers | ~6 | 0.10 + 0.06 ms a submit (5070 Field) | "a submit's memory work" |
| 1 submission entry: `submit_memory_work` (`vk_replay.cpp:5281`: pool list, `take_capture`, `collect_written`), `begin_recording`, `memory_begin_submission` | replay thread, `replay_mu`, `pools_mu` | S | 13 `run_submit` | memory work 0.46 (5070 Market), 1.04 (5070 Field), 0.7 -> 2.0-2.2 ms (3050 Field, normal -> slow frames) | `memsync_ms`, `late_wait_ms`, PROF_FINE `memory work` |
| 2 small command buffers recorded whole (dry pass then `record_segment`, `:4610`, `:3583`) | replay thread | S | ~17 (10 empty) | 0.85 (5070 Market), 1.46-1.86 (castle), 1.94 (3050 Market, before MID_SEG) | RX_VK_SMALL_LOG, `recorded whole here` |
| 3a mirror pre-sync of every imported pool (`memory_sync_mirrors_before_segments`, `vk_memory.cpp:8446`, `mirror_sync :6259`) | replay thread, `pools_mu` | S | 2.5-3 | first big cb 1.3 ms, 2.5 a frame (3050 castle, 15 Nov); Market and Field now: not measured | RX_VK_PRESYNC_STATS, PROF_FINE step 1 |
| 3b segment recordings and init buffers begun (`:4339-4367`) | replay thread | S | 20-30 slots | 0.26 ms (5070 Market, BIND1) | PROF_FINE steps 3 and 4 |
| 3d dry loop (`:4443-4452`, `replay()` in `Mode::Dry`): every op in order, reports, conditions, uniform updates, target marks, state copies at the boundaries | replay thread | S | 2.5-3 | 2.35 ms (5070 Market, marks 0.65 of it), 2.6 (3050 castle, 15 Nov) | PROF_FINE `dry loop`, `ops of the dry pass` |
| 3e segments (`early_record_job :4043`, `draw()` in `vk_draw.cpp:8365`) | 4 workers + replay thread, ParLock (one global recursive mutex) | P | 20-25 | `draw()` 13.7 ms summed (5070), 19-22 (3050); effective parallelism 4.4 (5070), about 3.5 (3050, I) | PROF_FINE, RX_VK_PARLOCK_STATS |
| 3f own last segment and join (`early_join :4096`) | replay thread | S | 2.5-3 | 2.89 + 0.6 (5070 Market); segments + wait 6.3 (3050 Market) | `its own segment`, `waits and submits` |
| 4 end of the submission (`finish_recording :5471`: uniform-update flush, `memory_end_submission`, queue submit) | replay thread, `pools_mu` | S | 13 | not split in any document | `recordings ended` |
| 5 present (`do_present :7498`) | replay thread | S | 1 | 0.39 (5070) | `present_ms` |

The 3050's "dry pass 4.3 ms" (fine profile, Market) is measured from `vk_replay.cpp:4311`, before the pre-sync (`:4323`): it holds stages 3a, 3b and 3d. **P**

### E3. Facts that decide what is worth cutting
- A saving of S ms summed over the recorders shortens the chain by about S / 4.4 (5070) or S / 3.5 (3050, I); serial work counts in full. The 3 ms the 0.1 % low needs would be 10-13 ms summed, over half of all `draw()` time: per-draw micro-levers give 0.1-0.3 ms each (`DESC_PATCH` 0.9 ms summed gross gave 42.7 against 42.4 fps; `TEXRES` 0.05-0.17 critical). **P**
- A segment's draws cost 9.95 us for draws 0-31, 6.53, 5.69, 5.28 and 1.89 us from the 288th (5070 Market, before TOUCH_FAST); the same worker for the same draws changed nothing. **P**; the cause of the cold start is not known (**I**).
- On the 3050 more concurrency made it slower (the overlap switch: `draw()` 24.1 against 14.2 ms, -6 %). **P**
- The slow frames (20-23 ms) grow in every category together while the GPU is flat, and the submit wall grows more (+22 %) than the summed draw time (+14 %): the signature of contention and of the replay thread's own steps growing, not of one more step. **I**

### E4. Candidate cuts, ranked (gain in ms of the replay chain)
1. **Recorders and capture helpers off the replay thread's core** (`par_worker_main :3468`, as `thread_prio.h` does for the compile threads): 0.4-1.4 ms and the scatter; 0.5-1 day. The replay thread has both hardware threads of one core but nothing keeps the recorders off its sibling; the host measured 1.7x for a shared core, the compile threads' pinning gave +4.7 % cold. First test with no code: `RX_VK_PARALLEL_IDEAL=1` on the 3050. Risk: the workers lose 2 of 12 logical processors (jobs workers pinned: -1 % warm).
2. **`RX_VK_MID_SEG` 128 -> 96 (or 64)**: 0.3-0.8 ms by arithmetic (the Market's 105-work command buffer stays whole at 128, `segment_plan.h:33`); the only 3050 run had 96 (+12 % Market). 0.5 day.
3. **Split `memsync_ms`, then cut what the slow Hyrule frames add** (+1.3-1.5 of their +3.0 ms): instrument 0.5 day, cut 1-3 days; the late-page wait in `take_capture` (`vk_memory.cpp:4090-4170`), the page walk of `memory_collect_written`, the copy helpers. Needs the frame trace's `late_wait_ms` of slow against normal frames first.
4. **Segment setup on the recording threads in the early path** (`begin_segment_slot` / `segment_begin_here`, `:3532-3553`): 0.2-0.4 ms; 1 day.
5. **A pre-sync that visits only changed pools** (after PRESYNC_STATS shows the split): 0.3-0.9 ms guessed; 3-4 days; not "pools no binding uses" (storage binds are known only at the draw).
6. **Texture registrations that change nothing no longer bump the slot version** (`vk_bank.cpp:149-183`): 0.2-0.9 ms; 2 days; stops at the source what TEXRES cached on the recorders' side.
7. **Descriptor sections kept across builds** (THIN_TEXSEC finished, a storage section): 0.4-0.8 ms; 3 days; after 6.
8. Smaller: TEXRES with TOUCH_FAST re-measured (0.1-0.4), dry-pass target marks (0.1-0.2), one staging copy for the stream's uniform updates (0.1-0.2 CPU, 80 GPU barriers), fewer queue submits (0.1-0.3).

The first five together plausibly give 1.5-3 ms (I); the order thread (FLICK1) is a different kind of gain (+5 to +9.6 % on the 3050) and stays under all of them.

### E5. Tried, no gain, not to be proposed again without saying what is different
Bindless textures (0.15-0.3 ms), reuse of last frame's draw work (14-22 % of `draw()` time repeats), `DESC_PATCH`, `TEXRES` (before TOUCH_FAST), `PROGFRONT`, `PIPEFAST`, thinned push constants and the Vulkan-call census (nothing over 1 ms), `NO_DRY_MARKS`, `DRY_LEAN`, `PARALLEL` 5 and 6, worker affinity (5070), `POOL_SPIN`, `SEG_TAIL`, `COMPLETION_THREAD`, the pre-sync on a worker beside the dry loop, small command buffers on a worker beside the next dry pass, deferring the segment join, submission overlap and lanes (every early group is the last big command buffer of its submission), parallel dry pass (analysed, not built), the present thread. Sources: `docs/research/bind1-replay-cpu.md`, `memo1-replay-reuse.md`, `small1-small-cbs.md`, `docs/native-engine/replay-cost.md`, `perf-plan-2026-11.md`, `build/s5/night/MORNING.md`.

### E6. Not established, and the run that would
The 3050's chain split in the shipped path (PROF_FINE: `replay_handle_early's steps` and the replay-thread wall line, Market and Field, normal against slow frames); the pre-sync's share and pool count (RX_VK_PRESYNC_STATS); who runs on the replay core's other hardware thread (a WPR CPU trace); the per-segment cold-start premium after TOUCH_FAST (RX_VK_PARLOCK_STATS prints draws by place); the cost of stage 4 on the 3050.
