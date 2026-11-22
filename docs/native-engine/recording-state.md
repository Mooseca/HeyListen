# Recording state: what a recording shares with the workers still recording the one before (stream REC1, 22 Nov 2026, branch refactor/rec1 from refactor/feed1)

Why: on the RTX 5070 the frame is a serial chain (game draw code ~1.7 ms, replay ~7.7 ms, present). Inside the replay the recordings run one after the other, because the
next recording's begin changes state that the workers of the last one read (`replay-cost.md`, JOIN1). The ceiling of overlapping them is about +28% on the 5070, +14% on the
PC 3050. This note lists each piece of that state, who writes it, who reads it, the rule it follows now, and what is done.

Vocabulary: a *recording* is a `Recording` slot (command buffer + uploads) that one thread records; a *group* is one big command buffer's segments (`EarlyGroup`: a dry pass
on the replay thread, segments on the pool's workers, the last one on the replay thread or, with `RX_VK_DEFER_JOIN`, on a worker); a *join* is the replay thread waiting for the
group's segments (`early_join`) and what follows from it; a *submission* is one `run_submit` (`replay_mu`), made of recordings; `memory_begin_submission` /
`memory_end_submission` bracket it in `vk_memory.cpp`.

## Stage A: the state, piece by piece

| piece | state today | done in REC1 |
|---|---|---|
| `table_defer`, `table_pending` | per thread already | note + test |
| segments' init command buffers (`seg_inits`) | was global, replaced per group | **moved: `SegTable` per group** |
| uniform updates' list positions (`ub_limit`, a segment's `ub`, ...) | were places in a deque that `ub_prune` shifts | **moved: absolute positions** |
| `par_conds` / `par_conds_reset` | one vector for the dry pass in progress | rule + counter |
| `ub_prune` | pops the front | rule + counter (positions done above) |
| `memory_end_submission` | needs every worker's write-backs | rule + counter |
| `memory_begin_submission` | bumps `mirror_epoch`, clears `mirror_synced`, `writebacks` | rule + counter |
| `mem_rec_value` | one global | **moved for the segments' workers: their own value** (check) |
| `mirror_epoch` | one global | **moved for the segments' workers: their own epoch** (check) |
| `synced_epoch`, `sync_seg` (a pool's) | one pair a pool | epoch side follows the line above; the pool's pair not moved (design below) |

Every piece was read from the code, not from the JOIN1 list; the first row corrects it.

### 1. `table_defer` / `table_pending` (`vk_memory.cpp`, `guest_pages_set`, `memory_table_begin`, `memory_table_flush`)
- JOIN1 listed them as global and written by the workers' `texture_uploads_recorded`. They are `thread_local` (declared at `vk_memory.cpp` ~613). `memory_table_begin` runs from
  `texture_begin_recording` on the thread that begins a recording (the replay thread in `begin_recording`, a worker at the start of its segment's job) and `memory_table_flush` from
  `texture_uploads_recorded` on the thread that ends it, so each thread flushes only the changes its own recording made, into its own upload command buffer.
- Writers: `guest_pages_set` (a pool made, merged, dropped: any recording thread). Readers: the GPU, through the page table; the CPU never reads the pending list.
- Rule: one recording is recorded by one thread from `texture_begin_recording` to `texture_uploads_recorded`; its table changes go into that recording's uploads, after its mirror copies.
  A thread that is not recording (`table_defer` false) writes the table at once. Nothing to move; `tests/test_recording_state.py` keeps it `thread_local`.
- What stays true under overlap: the GPU reads the table in the queue's order, so a recording's table changes must be submitted in the recording's place: the in-order submit below.

### 2. The segments' init command buffers (`vk_texture.cpp`, `SegInit`, was `seg_inits` under `seg_init_mu`)
- Was: `texture_segments_begin` replaced a global vector at each group's start and `texture_segments_begin(nullptr, 0)` cleared it at the join; a worker found "the earliest open segment" by its
  segment number in it. A group that begins while workers of the last one still record would have replaced what they index.
- Now: `texture_segments_begin` returns a `SegTableRef` (`std::shared_ptr<SegTable>`: the vector and its mutex). The `EarlyGroup` (and the older path's local) holds it; `texture_segment_worker(table, index)` puts
  a raw pointer in the worker's `thread_local tl_seg_table` for the time it records the segment; `texture_segment_end(table, index)` ends one init command buffer. The clearing call is gone: the table dies
  with its group (the pool's jobs hold the group).
- Writers: the replay thread (begin), each worker (`used`, `open` under the table's mutex). Readers: the same workers, `InitRedirect`. Rule: a table belongs to one group; nothing outside the group reaches it.
  Same calls, same command buffers, so no command stream changes.

### 3. The uniform updates' list (`vk_replay.cpp`, `ub_updates`, `ub_limit`, `ub_first_of_recording`)
- Was: positions in the deque. `ub_prune` (`pop_front` at each submission's start) shifted every kept position: `ub_first_of_recording` was decremented to follow it, but a worker's `ub_limit`, a segment's `ub` and a
  dry-pass point's `ub` were not, so nothing could be pruned while workers read.
- Now: `ub_base` counts the entries popped; a position is `ub_base + index`; `ub_end()`, `ub_at(pos)` (the only reader of the deque's `[]`); every stored position is absolute. A prune moves nothing a recording that has
  begun holds. Entries are only pruned when their submission's value is completed, and a worker's segment belongs to a submission whose value is not.
- Writers: the replay thread (append in the dry pass or serial replay under `UbGrowGuard`, prune at a submission's start). Readers: workers (`ub_overlay`, `ub_read`, under `UbReadGuard` only while `ub_growing`).
- Still to do for overlap: a prune pops the deque's front while a worker may index it: the deque's start moves, so the prune must hold `ub_grow_mu` exclusively and every worker's read must take it shared for as long
  as any group is pending (today only while `ub_growing`, the dry pass). Counter: `ub_prune` beside pending segments.

### 4. `par_conds` (`vk_replay.cpp`)
- One vector of the dry pass's render conditions; workers read `par_conds[cond_at]` bounded by `par_conds_n` under `UbReadGuard`. `par_conds_reset` clears it at each dry pass's start.
- Rule: reset only with no group pending; with one pending the next dry pass continues from `par_conds_n` (`cond0`, built in JOIN1). Per-group conditions (the vector in `EarlyGroup`, the segment's `cond` an index into it) remove the
  rule; not done. Counter: `par_conds_reset` beside pending segments.

### 5. `memory_end_submission` (`vk_memory.cpp`)
- Writers of its input: a binding written in place (`vk_memory.cpp` ~6467: `writebacks.push_back`, and `wb_pages_note`), from every recording thread. It records the write-back copies into the submission's last command buffer.
- Rule (unchanged): it runs after the join of every group of its submission (`finish_recording`, `split_part`, `occ_sync`, the present). `run_submit` makes the join at the end of its command buffers' loop. Under overlap
  the submission still ends where it ends; what can move is the *next* submission's start (below). Counter: `memory_end_submission` beside pending segments.

### 6. `memory_begin_submission` (`vk_memory.cpp`)
- Bumps `mirror_epoch`, sets `mirror_upload`, clears `mirror_synced` and `writebacks`, reaps and makes mirrors. Called at a submission's start, at a recording split (`split_part`, `occ_sync`) and at the present.
- Rule: not while a group of the recording before is pending (it clears the write-backs those workers add and changes `mirror_epoch`, below). Counter: `memory_begin_submission` beside pending segments.

### 7. `mem_rec_value` (global; set by `memory_recording_value` in `begin_recording`) - moved for segment workers
- Readers: every binding (`p->last_value`), the write-back notes, imports and mirror frees. A worker read the replay thread's value, which `begin_recording` changes at the next submission.
- Now: every read in `vk_memory.cpp` goes through `rec_value_of()`: a thread that called `memory_recording_thread(value, epoch)` (a segment's worker, from the start of its job to its end, with the
  `Recording::value` of its segment's recording and the epoch its group took when it began) reads those, every other thread (the replay thread, game threads, a worker outside a segment) reads the global,
  as before. With no recording beside another the two are equal at every read; `RX_VK_REC_OVERLAP_CHECK=1` counts the reads where they are not (logged with the join check: "reads of the submission's value
  and epoch by segment workers ... differed"), and it must be 0.

### 8. `mirror_epoch` and `synced_epoch` / `sync_seg` - the epoch moved for segment workers, the pool's pair not
- `mirror_epoch` is written only by `memory_begin_submission` (under `pools_mu`), read at ~70 sites, of which the worker's binding (`memory_bind`, the unlocked fast path against `p->synced_epoch`, and `mirror_sync`), the readback ring (`rb_*`),
  `mirror_make` and the idle give-back. A pool's `synced_epoch`/`sync_seg` say "this pool's mirror holds the CPU's pages as of this submission, copied by a recording before queue position `sync_seg`".
- The pre-sync of the next big command buffer marks pools `synced_epoch = mirror_epoch, sync_seg = 0`; a pending segment of the same submission that binds such a pool later reads it as synced by a copy that sits *behind it* in the queue.
- Epoch side: done as for `mem_rec_value` (`rec_epoch()`, the group's `memory_epoch()` taken at its begin; the same check). Pool side, to build: a segment's check is against its own recording's `(epoch, order)`: the thread-local epoch carries it, and the pre-sync stamps `sync_seg` with the order of the recording that holds its copy (`par_seq`), so a segment of
  an earlier order finds the pool not synced for it. The pool then needs a short list of (epoch, order) syncs, not one pair, because two recordings' copies are both live in the queue. This is the largest change in `vk_memory.cpp` and is
  not made.

### 9. The capture (`vk_memory.cpp`, `memory_read_as_submitted`, `cap_entry`, `cap_bufs`, `cap_view_gen`) - found in this pass, not moved
- Every uniform word, handle and storage-buffer word the replay reads on the CPU for the GPU's sake (`ub_read`, the descriptor code, program lookups) comes from "guest memory as it was at the submission": a page's newest
  capture (`cap_entry(page)`, valid while `e.gen == page_gen(page)`), else guest memory. The table is global, and `memory_capture_submit` (the capture of the next submission, ~0.13-0.2 ms, in the "setup" before the first
  command buffer) replaces its entries. A worker still recording the last submission's segment would read the next submission's pages.
- Rule to build: a capture view per submission, taken by the group like the epoch (the table's entries keep the generation they belong to: a read for submission N must take entries with generation <= N's and skip newer ones, or
  `cap_bufs` keep the older version until the group is joined). `cap_view_gen` and the `submitted_pages` caches key on the view already, so they follow. This is the piece that decides whether the next submission's capture can run beside
  the last one's segments, and it is not small: do it before anything below.

## Stage B: what is needed, from the code (not built)

Stage B is not built: a recording may not begin beside the workers of the one before until pieces 8 (the pool's sync pair) and 9 (the capture) are per submission, and `memory_begin_submission`'s lists below are per submission too. What was
learned, so the next session need not read it again:
- `RX_VK_DEFER_JOIN` (JOIN1) already runs `begin_recording` beside pending segments, and the dry pass of the next big command buffer beside them is built (`par_conds` continued, `ub_grow_mu`). In the frames measured the join is
  always forced at once (JOIN1); `RX_VK_REC_OVERLAP_CHECK` now says by which step ("joins made by"; see the results below).
- The gain is in the steps between one big command buffer's join and the next recording's first need of the GPU's order: the next submission's capture and setup (0.13-0.2 + 0.2-0.25 ms), its small command buffers (0.4-0.45 ms), the dry pass of
  its big one (0.26-0.3 ms), per REPLAY2's split of what the GPU waits for. They sit behind `finish_recording` (`memory_end_submission` of the submission before, which needs every write-back the workers note) and behind `memory_begin_submission`.
- The join would then be made by the last worker to finish a segment (completion-driven: its group's in-order submits are already made by whichever thread finishes one, `early_submit_ready`), which runs `finish_recording` of its submission under a lock
  that orders it before the next submission's first `submit_recording`. The next submission's first submit waits for that order (the queue's order: N's segments, N's last recording, then N+1's first). The write-back list, the synced list and the
  write-back notes (`writebacks`, `mirror_synced`, `wb_pages_note`'s per-value ranges) would be per submission with the epoch.
- Not touched: `vk_draw.cpp` and the descriptor code (DRAW1's). A state move forced no change there: the workers read the value and epoch through `vk_memory.cpp`'s accessors; the draw code calls `memory_*` as before.

## Results (main PC, RTX 5070, `HL_RB_LAG=2 HL_GFX_VAR=1 RX_VK_FEED_LOG=1`, `market-spin` from `market-mid` unless said; build rec1 against join1 (= feed1's code, switches off))

Stage A, no behaviour change (the speed series lost round 3 to another agent's build, runguard exit 11, and A round 2 to a failed copy of the exe; round 1 of rec1 R was a slow start of a new exe: the play window began at 89 s, 105 frames):
| arm | fps (rounds with a clean window) | p95 ms | GPU feed: busy / idle / replay not ready ms | draws, dispatches, passes, barriers, submits a frame |
|---|---|---|---|---|
| A join1, off | 82.2 | 17.0 | 7.54 / 3.63 / 3.12 | 2364 / 160 / 169 / 167 / 6 |
| R rec1, off | 83.8 | 16.4 | 7.56 / 3.75 / 3.19 | 2327 / 165 / 166 / 167 / 6 |
| C rec1 + `RX_VK_REC_OVERLAP_CHECK=1` | 73.8 (a 2.1 s hitch), 85.3 | 17.5, 17.0 | 7.49 / 3.42 / 2.81 and 7.55 / 3.54 / 3.04 | 2352 / 159 / 165 / 165 / 6 and 2426 / 166 / 167 / 168 / 6 |
Same frame, same speed within the spread (fps is a sanity figure). The proof of an unchanged command stream is the check: with every switch off, 13,800 joins in one run, **0 segments differ from the dry pass's plan**; 41.8 million reads of the submission's value and epoch by segment workers, **0 differ** from the replay thread's. The same in Kakariko, Lost Woods and Inside the Deku Tree (`kokiri-idle`, 14-48 million reads each, 0 differences). Pictures were not compared: `RX_VK_SHOTS` writes nothing in these windowed bench runs (JOIN1 saw the same; not investigated again), the rb ring's hash log is not run-to-run deterministic in the harness scenes (`readback-ring.md` 4.2), so the draw, dispatch, pass and barrier counts and the plan check stand for the command stream. No crash, hang, device loss in any of the 11 runs (no validation layer was on).

Stage B, what forces the join (`RX_VK_DEFER_JOIN=2 RX_VK_REC_OVERLAP_CHECK=1`, Market, Kakariko, Lost Woods, Deku Tree, ~9,000 joins in Market): per join, **1.00 made at the end of run_submit's command buffers loop, 0.00 by every other cause**; steps beside pending segments: recording begun 1.00, serial small command buffer 0.00, dry pass 0.00; ub_prune, par_conds_reset, memory_begin_submission, memory_end_submission beside pending segments 0.00. The big command buffer is the last of its submission in every scene, so there is no next command buffer in the same submission to overlap with: **the overlap has to cross submissions**, which needs pieces 8 and 9 and the per-submission write-back and synced lists first (above). Numbers for the deferred arm are not a gain figure (it is the JOIN1 diagnosis): Market 75.3 fps against 77.0, Kakariko 70.3 against 97.1 (a lost round for the plain arm in the same place: other runs of that scene gave 97-100), Lost Woods 83.4 against 83.0, Deku Tree 135.4 against 128.1.

`RX_VK_REC_OVERLAP` (Stage B) is not built.
