# The writers of the per-draw uniform blocks, and the native uniform writer (WRITER1, 2026-11-21)

Step 2 of `refactor-plan.md` ("direct rendering of the heavy passes") cannot be done pass by pass (`direct-pass-prototype.md`): in the
heavy passes 81-97% of the uniform binds are not final when the draw is recorded, they are written after `EndRecording`, so capture,
mirror sync and replay stay until a native module writes those blocks. This note names the writers, says what they compute, validates
`HL_GFX_VAR=1` (the other half of step 2's first unit), and designs the native uniform writer. Branch `refactor/writer1` from
`refactor/step2p`, worktree `E:\OOT\HeyListen-wt\writer1`. Main PC (RTX 5070, Ryzen 7 7800X3D), scene `market-spin` from `market-mid`,
`dlss=0 upscaling=0 resolution=1 hdr=0 vsync=0`, no frame cap. Guest addresses and sizes only; nothing of the game is quoted.

## 1. Who writes the per-draw blocks (measured)

**Method.** Two diagnostics (new, off by default), one run, `RX_VK_PARALLEL=0`:

- `HL_UBO_CHECK=1` with `HL_DIRECT_PASS_MAP=1` now also lists, per pass, **the guest pages of the binds whose bytes changed after the
  recording** (`hl pmap:   different binds by guest page (...)`: `<page hex>:<binds>`, 24 pages a line, the hottest first, up to 250 pages a pass).
- `HOS_POOL_TRAP=<s> HOS_POOL_TRAP_FLAGS=22 HOS_POOL_TRAP_MS=40 HOS_POOL_TRAP_LOG=<path>`: the `0x022` ring pools' resident pages are made
  `PAGE_NOACCESS` every 40 ms and **every first touch by guest code is logged with its page and the four host frames** (a lifted
  function is `f_<guest address>`). 805,562 write records on 7,596 pages in the 35 s window. (The handler also had a race: a second
  thread faulting on a page the first had just opened was let through to a crash at the short period; fixed.)
- Join by page: `tools/bench/writers.py` (a pass's different binds, each split over who touched its page first) and the chains of frames.
  Run `w1-trap1`; the tool output is in "Reproduce" below.

**The writers.** For the pass **647395d4** (the heavy Market scene pass, 54-60 draws and 270 different binds a frame), by the chain of
host frames at the first touch of the page of each different bind (25% of the binds are on pages with no write in the window and are left
out of the shares):

| Share | Chain (leaf < caller, guest functions) | What it is |
|---:|---|---|
| 37% | `0x81500200` < `0x8009bb80` < `0x800998a0` < `0x80083960` | the **skin palette writer**: for each joint of a pose, a 3x4 matrix product of two 48-byte matrices (indexed by int16 tables), stored into the pose's palette array |
| 25% | `0x8575cdc0` < `0x814f2c80` < `0x8009b7b0` < `0x8009bb80` | a vector-copy helper under the instance record builder `0x8009b7b0` |
| 20% | `0x8009bb80` itself (< `0x800998a0` < `0x80083960`) | the object batch job's own stores (helpers inlined) |
| 13% | `0x8050ee60` < `0x800d43d0` < `0x800cdbe0` < `0x82c43780` | a second job type, not under `0x8009bb80` |
| 4% | `0x8009ba60` < `0x8009bb80` | the instance loop |

Shares are per page: each different bind counts once, split over the functions that first touched its page in the 35 s window (the
page-weighted first version of this table said 62% for the palette writer: too high, the hottest pages are rewritten the most).
Over the heavy passes the same functions return; **`0x8009bb80` is the ancestor of 80-90% of the binds** (instanced pass 0b3bf877: its
instance loop `0x8009ba60` 66%, `0x800a9540` 16%, `0x800a8ae0` 7%):

| Pass | Different binds a frame | Writers (share of its different binds, %) |
|---|---:|---|
| 647395d4 (scene) | 271 | `0x81500200` 37, `0x8575cdc0` 25, `0x8009bb80` 20, `0x8050ee60` 13, `0x8009ba60` 4 |
| c9e43b88 (scene) | 223 | `0x81500200` 35, `0x8009bb80` 19, `0x8009ba60` 16, `0x8050ee60` 14, `0x8575cdc0` 5 |
| ef317a54 (scene, every 2nd frame) | 89 | `0x8009ba60` 70, `0x800a9540` 15, `0x800a8ae0` 8, `0x8009bb80` 4 |
| 0b3bf877 (instanced, 456 draws) | 288 | `0x8009ba60` 66, `0x800a9540` 16, `0x800a8ae0` 7, `0x81500200` 3 |
| a3667776 (character) | 52 | `0x8575cdc0` 37, `0x81500200` 22, `0x80364ee0` 18, `0x8009ba60` 10 |
| 4e1998ea | 124 | `0x81500200` 40, `0x8009bb80` 25, `0x8575cdc0` 17, `0x8050ee60` 16 |

About **1,900 different binds a frame** in the 14 heaviest passes (of 2,980 binds; the frame is ~2,500 draws).

**Why they are written after the recording.** `0x8009bb80` (18,700 lifted lines, ~40 callees) is one job per drawable batch. It calls the
recorder `0x806002e0` (the function the map's recorder column shows with the largest bind population: 3.4 million binds a run), which
records the draw's `BindUniformBuffer` calls with the addresses of the blocks, and writes the blocks in the same job afterwards, through
mapped-range wrapper objects. The blocks' destination is the **pointer a wrapper's virtual call returns** (`0x800a8df0`: begin write,
returns the mapped pointer; `0x800a9510`: end write, flush when the wrapper's flag byte says so, a no-op in the native NVN layer). So the
address is chosen when the draw is recorded and the bytes arrive later in the same function, on the ModuleSystem worker threads (the
first touches are on `ModuleSystemWorker*` and the main thread; `0x80083960` is the job runner).

## 2. What the writers compute

- `0x81500200(pose, joint count)`: a loop over joints: loads the pose's index tables (int16), two 48-byte 3x4 float matrices, multiplies them
  lane by lane with the game's FMA ordering (the lifted code's fast blocks), stores 48 bytes at a 64-byte stride into the output array; a
  second pass handles odd counts. Pure function of guest data and the FPCR; the output range is the pose's palette (the 2.9 KB binds).
- `0x8009ba60(array, mask)`: a loop over 112-byte entries (+28 count, +32 base, +40 entries): per entry whose flag bytes (+90, +13,
  +120) say so, calls the per-entry record writer `0x814e86b0` (or `0x814e7dc0`): it asks the wrapper for the mapped pointer, **transposes
  a 4x4 matrix into a 3x4 (48 bytes), stores the entry's key byte (+90) at +48, marks the 52 bytes written, copies the entry's payload
  (a pointer at +80, a 34-bit signed size at +88, rounded down to 4) to +64, and ends the write**. Data movement only, no arithmetic.
- `0x800a9540` / `0x800a8ae0`: the instanced path's per-instance blocks (not read in detail).

## 3. Design: the native uniform writer

**Unit.** The batch job `0x8009bb80` and the three kernels under it above (skin palette, entry record, payload copy), **not** a draw
function. A native module owns: the order "choose the block address, write the block, record the bind". That is the only order in which a
bind can carry final bytes (inline, `NOP_UBO_INLINE`) or a range the capture does not need to scan, which is what removes capture, mirror
sync and the per-range replay work for these blocks. Writing the kernels natively without owning the job order removes only their
translated CPU (worker threads), not the replay's.

**Bricks, in order (each with its check):**

1. **K: the kernels native, in place.** `hl::uniform` (new, `engine/native/src/uniform/`, bit-exact like `hl/math/Exact.h`): `skin_palette`
   (`0x81500200`), `entry_record` (`0x814e86b0`, with `0x814e7dc0`'s variant), `payload_copy`. The bridge answers the guest function
   (`HL_GATE` style, like `hl_math.c`) and calls back into the translated wrapper methods (`0x800a8df0`, `0x800a9510`) for the mapped
   pointer. Switch `HL_UNIFORM_NATIVE=0|1` (default 0). Check `HL_UNIFORM_NATIVE_CHECK=1`: each call runs native into scratch, then the
   translated function for real, and compares the **bytes it wrote** (the ranges the lifted code marks with `A64_MARK`, which the build
   already tracks), 0 mismatches over the three scenes and the Market. Declined when the FPCR or a value is outside the exact rules
   (`Exact.h`'s `Why`).
2. **L: the writer ledger.** Every native write goes into a per-submit ledger `(address, size, serial)`; the replay reads a bind's bytes
   from the ledger when the bind's range is covered, the capture skips the pages only the ledger covers (`RX_VK_CAP_ONLY_GPU`'s left-out
   ranges are the model: 0 reads into them, checked). Check: the existing `HL_UBO_CHECK` (the ledger's bytes against what the replay reads
   as submitted: 0 different).
3. **J: the job.** `0x8009bb80` itself native (its 40 callees: sphere, frustum test, render-state, recorder `0x806002e0`), recording with
   `RecordWriter` and writing before binding. Then the binds carry inline bytes, `NOP_UBO_INLINE` (built and clean in `direct-emission.md`
   section 9). Check: the records compared with the NVN call records (`HL_GFX_REC_CHECK`'s mechanism).

Brick K alone is the smallest working unit and the first to build; L and J are what step 2 needs.

## 4. HL_GFX_VAR=1 (the key-0xa0 draw function, native on its plain entries): validated

**Pictures** (`RX_VK_SHOTS`, build `writer1-b`, slot lease, `kokiri-idle` from the saves `market`, `kakariko-village`, `lost-woods`,
`inside-deku-tree`, `HL_GFX_VAR=0` then `=1`, a shot every 900 frames, 17-22 shots a run): the Market, Kakariko, the Lost Woods and the
Deku Tree look the same with it on: the same scene, geometry, shadows, grass, UI, no missing object, no flicker. The first 12 shots of
a run are identical to 0.002 mean luminance (the load screen); after that the two runs differ the way two runs of the same arm do (Navi's
position, a dialogue box, the time of day's shadows: mean luminance difference 5-9, 5-15% of the pixels over 16 levels), so no
pixel-exact comparison is possible with a free-running game; looked at side by side for each zone, last shots. No crash line in any
run. The native path was taken: `key loop` log lines of 2.7-3.1 M native entries a run in the Market, Kakariko and Lost Woods
(`native 3,116,884 / masked 5` in the Market; the Deku Tree, 242,297 native / 70,480 masked, the least).

**Speed** (speed lease, build `writer1-b`, slot b, `market-spin` from `market-mid`, `dlss=0 upscaling=0 resolution=1 hdr=0 vsync=0`,
no frame cap, `HL_THREAD_CPU=1`, 3 rounds interleaved g0 g1 g0 g1 g0 g1; "Render resolution: 100% chosen, drawn at 100% with Upscaler 0"
in the logs). Frame time of the steady part (from 55 s after the first present, ~3,000-3,750 frames a run):

| Run | mean ms | p50 | p95 | p99 | fps |
|---|---:|---:|---:|---:|---:|
| off 1 / 2 / 3 | 11.57 / 11.86 / 11.41 | 11.14 / 11.34 / 11.00 | 15.3 / 16.3 / 15.4 | 20.2 / 20.8 / 18.7 | 86.4 / 84.3 / 87.6 |
| **on** 1 / 2 / 3 | 12.44 / 11.82 / 11.45 | 11.99 / 11.26 / 10.98 | 16.8 / 15.9 / 15.4 | 20.4 / 25.7 / 20.6 | 80.4 / 84.6 / 87.4 |

Means of the three: off 11.61 ms (p50 11.16), on 11.90 ms (p50 11.41); **without the first "on" run 11.64 / 11.12**, the same as off.
CPU a frame (`HL_THREAD_CPU`, the last windows): all threads 70.5 / 70.2 / 69.8 ms off, 70.5 / 67.3 / 70.6 on; the replay workers
7.5-10.7 vs 8.3-11.3 ms: the same. **Verdict: clean, and in steady state not slower and not faster** (as `gfx-record-job.md` section
14 measured: 1,557 ns an entry translated, 1,565 native). Its use is the building block the uniform writer needs, not a gain.

**The 23 fps run of STEP2P, found.** Three things stacked, none of them the native path's steady cost:
1. That run was serial replay (`RX_VK_PARALLEL=0`) with the map and fine sections: its base run (`s2p-map2`) was 59.6 fps, not 80.
2. **The first run of an executable with `HL_GFX_VAR=1` pays a start-up**: my first "on" run logged `start-up: pipelines 3148 of 7664`
   (the first 25 s of its trace at 5.7-6.6 ms an interval against 2.9-3.0 for the "off" runs, the zone load at 27 ms against 13) and ended at
   69.7 fps over the run's window; the next two runs of the same arm did not (78.6 and 77.0 fps over the window, steady-state equal to
   "off"). STEP2P's run was the first one of that build with the switch on.
3. Both arms have load-time hitches (the longest frame of a run: 676-899 ms off, 672-1,674 ms on; one "on" run had a 3.1 s stall
   at the zone's load, which none of the three "off" runs had, and 14 frames over 200 ms): the whole-run fps (which includes the
   load) moves 70-82 fps between identical runs. **Compare steady-state windows, not the run's mean.** Not explained: whether the "on"
   arm's loads hitch more (one stall in three runs against none in three is not evidence).

## 5. What the uniform writer would remove (measured, bounds)

- **Replay CPU:** the per-draw uniform ranges are `user uniform buffers` 0.71 ms a frame of `draw()` (9.7% of its 7.3 ms) and, with
  the descriptors built from them, part of 0.69; the maps' `different` binds are ~1,900 a frame (of ~2,980 in the 14 heaviest passes). Not
  measured as a ceiling (no run left the ranges out); the sections bound it at about 0.7 ms of the 11.6 ms frame on the replay workers.
- **Mirror sync and capture:** the `0x022` and `0x024` ring pools' pages: 2.3-2.7 MB in 306-315 copies a frame in the small target
  families, ~1,000 pages a frame in the capture (`direct-emission.md` section 9: 4-5% of the capture's pages are the uniform pools').
- **The writers' own CPU (game threads), sampled** (`HOS_PROFILE=1 HOS_SAMPLE_ALL`, every game thread every 2 ms for 20 s of `market-spin`,
  speed lease, run `w1-samp1`, 79 fps; stacks are cut at 16 frames, so the callers are under-counted): of the busy game samples
  (19,950) the batch job `0x8009bb80` and what it calls are **3.1%** (its leaves `0x8009bb80` 1.9%, the skin palette `0x81500200`
  0.2%, the instance loop `0x8009ba60` 0.1%, the vector copy `0x8575cdc0` 0.3%, `0x80364ee0` 0.1%): about **2 ms of the 70 ms of CPU a
  frame**, spread over the five ModuleSystem workers and the main thread (not the critical path). Their caller `0x800998a0` is 12.5% of
  the samples (7.3% as the innermost lifted function), the item body `0x80084de0` 4%, the key-0xa0 function `0x8008d640` 1.1%. **So
  brick K alone (the kernels native) can remove at most ~0.3% of the game's CPU (the kernels' own samples), ~2 ms a frame at the very
  most if the whole subtree went native: it is not worth building by itself.** The writers are cheap to run; what costs is what the
  engine does because they write after the recording (capture, mirror sync, the per-range uniform work, above).
- **The order thread:** its 1.4-2.0 ms of CPU a frame here (9.0 ms on the critical path on the PC 3050, `refactor-plan.md`) is the
  submit-order work; it does not depend on who writes a block. A writer module changes it only through the capture it spares.

## Reproduce

    # the writers (a slot lease is enough, functional run):
    bash build/s5run.sh --slot <s> --save build/s5/savelib/market-mid <tag> market-spin HL_DIRECT_PASS_MAP=1 HL_UBO_CHECK=1 RX_VK_PARALLEL=0 \
         HOS_POOL_TRAP=72 HOS_POOL_TRAP_FLAGS=22 HOS_POOL_TRAP_MS=40 HOS_POOL_TRAP_REPORT=106 \
         HOS_POOL_TRAP_LOG=<E: path>/trap.log HOS_POOL_TRAP_OUT=<E: path>/trap.txt
    python -I tools/bench/writers.py <trap.log> build/s5/<tag>/game_log.txt <bin dir> [pass prefix]
    python -I tools/bench/writers.py --chains <trap.log> build/s5/<tag>/game_log.txt <bin dir> 647395d4

## Hand-over

- Branch `refactor/writer1` from `refactor/step2p` (5a50b9532), worktree `E:\OOT\HeyListen-wt\writer1`. Commits: `diag(vk): the different
  uniform binds by guest page, and HOS_POOL_TRAP_LOG, a page-level writer log` (`vk_ubo_check.cpp`, `vk_draw.cpp` `PmapAgg::ubo_pages`,
  `host/hos_memsplit.c` `trap_log*`, `HOS_POOL_TRAP_MS`, the handler's two-faulting-threads fix), and this note with `tools/bench/writers.py`
  and the regenerated switch lists. No push, no merge.
- **Not built: `HL_UNIFORM_NATIVE` and `HL_UNIFORM_NATIVE_CHECK`.** The measurement above says the kernels are 0.3% of the game's CPU:
  a native `0x81500200` or `0x814e86b0` with its byte check would be a working module that changes nothing measurable (and each needs the
  translated wrapper methods `0x800a8df0` / `0x800a9510` called back for the mapped pointer, and the exactness rules of `Exact.h` for the
  palette's FMA chain). The real unit is the batch job (brick J), which is 18,700 lifted lines and ~40 callees, i.e. a module of its own
  (it contains the recorder `0x806002e0`, the bounding sphere `0x800a8400` that is already native, the frustum test `0x80029240`, and the
  render-state work of `gfx-record-job.md`). **What the next owner should do first**: read `0x800998a0` (the caller, 12.5% of the game's busy
  samples and 7.3% as a leaf: the largest single lifted function by self time in the sample (next: `0x805902c0` 5.9%, `0x80df2680` 3.5%), and the one that
  decides what `0x8009bb80` is called with), then write brick L (the ledger) as a measurement before any kernel: per submit, the ranges the
  writers wrote after the recording (`A64_MARK` already marks them; the OS layer would have to log the ranges, not only the pages) against
  the ranges the replay binds, with the share of binds covered (the `HL_UBO_CHECK` columns above are the baseline: 95% of 647395d4's binds).
- Builds: `build/s5/bin/writer1-a` (first, crashed in the trap at the 40 ms period), `build/s5/bin/writer1-b` (all measurements). Logs and
  scripts (local, not in git): `build/s5/w1-trap1`, `w1-pic-*`, `w1-g0-*`, `w1-g1-*`, `w1-samp1`; `E:\OOT\scratch-writer1\` (`trap1.log`,
  `trap1.txt`, `samp1.txt`, `sampan.py`, `steady.py`, `buckets.py`, `cmp.py`, the run scripts).
- Not verified: the PC 3050 (no game was run there: the 3050 runs to route are the three below); the writers' shares come from one 35 s trap
  window in the Market (first touches of 7,596 pages, 25% of the heavy passes' binds on pages with no write in it); the CPU shares from one
  20 s sample with stacks cut at 16 frames; `HL_GFX_VAR=1`'s pictures were compared side by side, not pixel-exact (free-running game),
  and its steady-state speed on three rounds on the main PC only.
- 3050 runs to route (the main PC's numbers do not transfer): (1) `HL_GFX_VAR=0` against `1`, `market-spin`, three rounds interleaved,
  `HL_THREAD_CPU=1`, steady window only (`E:\OOT\scratch-writer1\steady.py` needs `present_trace.csv`); first run of the build discarded
  (it re-prepares pipelines); (2) the same sample run (`HOS_PROFILE=1 HOS_SAMPLE_ALL=... HOS_SAMPLE_NS=1`, `sampan.py`) to see whether the
  writer subtree is a bigger share of a 6-core CPU; (3) nothing else: the trap needs the main PC.
