# MEMO1: does the replay repeat the previous frame's draw work? (22 Nov 2026)

Branch `perf/memo1` from `refactor/integ4` (dcb8c7616). Main PC, RTX 5070 / Ryzen 7 7800X3D, speed leases (priority 2), `market-spin` from
`market-mid`, `castle-move` from `hyrule-castle`, `kokiri-idle` from `kokiri-forest`, the build's `HL_*` defaults, 110 s runs, windows of 600
presents, only windows with more than 800 draws a frame counted (the 75 s of loading and menus before "play: began" are left out).
Code: `RX_VK_REPEAT_STATS=1`, a diagnostic that only logs (`vk_draw.cpp`, namespace `repeat`; `vk_replay.cpp` numbers each draw and calls it at
each present). It costs ~1-2 us a draw plus the analysis at each present, so it is **not for fps** (fps with it on: market-spin 81.8,
castle-move 90.9, kokiri-idle 105.2); every figure below is a share, not a rate. Raw logs: `E:\OOT\HeyListen\build\s5\memo1v3-*` (version 3, the
tables below), `memo1v2-*`, `memo1-*` (version 1); scripts `E:\OOT\scratch-memo1\parse.py`, `tab.py`.

## Verdict

**NO-GO for reusing last frame's draw work as the +30% lever.** The bar was "more than ~50% of `draw()` time in repeatable spans":

- With the draw's whole identity (uniform contents left out): **14-22%** of `draw()` time repeats the frame before or the one before that
  (33-40% of the draws); 31-50% over the last 60 frames if a repeat inside the same frame counts too. Spans do not repeat by position
  (2-4% of the draws are identical at the same place in the frame) and whole passes hardly ever (1-6% of the time).
- The time sits in the draws that do **not** repeat: the 5-13 us draws are the ones whose **texture handle words and texture registrations
  change every frame** while everything else is the same (95-100% of their time repeats if textures are left out in castle-move and kokiri-idle, 18-98% in the Market, against 0-72% with them). The draws that
  do repeat strictly are the cheap ones (1.3-2.0 us, 300-500 a frame), where a reuse has ~0.3-0.5 us to win.
- Leaving the textures out of the key (a cache that re-resolves textures every draw) lifts the repeat to 52-86% of the time but saves only the
  non-texture part of `draw()` (~2.2 us of 5.8): **0.4-0.8 ms of the critical path (4-9%)**, against the ~2.5-3 ms the +30% needs. A reuse
  that hit every draw and made a hit cost 1 us (re-executed secondary command buffers) is the only form that reaches the bar, and it has no
  coverage to do it with.
- Cheaper partial wins are in section 5; the design asked for in step 2 is in section 6 for the record, with gain and effort. Not recommended.

## 1. What was measured

At the draw (`draw()`, once the program is known) each draw is hashed from: the program (key, variant); the pipeline state (blend, colour,
channel mask, multisample, polygon, depth-stencil, vertex attributes and the streams they read, restart, the targets' formats, colour types);
the dynamic state (viewport 0, depth range, scissor, stencil, polygon offset, blend colour); the **texture and sampler handle words** the program
reads (`handle_of`; a handle table by its size); the same handles **resolved** (the registered texture's initialization serial and view, the
sampler's parameters); the vertex buffers of the streams in use and the index buffer; the draw's arguments; the render targets (texture
pointers, levels, layers, size); the storage buffer words (address and size as read from the constant banks); and the **sizes** of the uniform
buffers the program reads. Left out and kept apart: the uniform buffers' **addresses** (and the bytes of HL_UBO_INLINE binds). Uniform contents
are never read: the game writes most of them after the recording (99.3% of the changing binds, `host/nvn_native.c`). The draw's number in its
frame is the stream's draw serial since the last present. A *pass* is a run of draws into the same targets.

At each present the frame is compared with the two before it (N-1, N-2; the game's double-buffered rings may repeat every other frame):
the draws identical at the same place; the draw's hash found **anywhere** in that frame (a multiset match, so a shifted stream still matches);
the same with groups of components left out (leave-one-out and combinations); whole passes identical; and the **age** of each draw's hash, how
many frames ago a draw of the same identity was last seen (a table of the last 120 frames; "earlier in the same frame" its own age). Time is
`draw()` whole, hashing excluded, summed over the recording threads (BIND1's definition; 13.7 ms in BIND1's Market run); a hit is weighted by
its own time. Per-program tables: the costliest programs and how much of their time repeated.

Scenes in the v3 runs: market-spin 2,075 draws a frame (14.8 ms of `draw()`), castle-move 1,348 (5.6 ms), kokiri-idle 2,123 (11.2 ms). Version 2
(no resolved textures) was within 2 points of these everywhere.

## 2. Repetition (share of draws / share of `draw()` time, mean of the play windows)

| identity, looked for | market-spin | castle-move | kokiri-idle |
|---|---:|---:|---:|
| same place in the frame, identical to N-1 (v2) | 2.1% / 0.6% | 2.1% / 0.8% | 3.1% / 1.0% |
| same place, identical to N-2 (v2) | 1.9% / 0.8% | 1.8% / 1.2% | 4.0% / 1.4% |
| **anywhere in N-1 or N-2, strict** | **32.8% / 14.4%** | **37.0% / 21.6%** | **39.7% / 18.8%** |
| the same, handle ids left out, resolved textures kept | 34.5% / 16.3% | 40.9% / 26.0% | 39.8% / 18.8% |
| the same, textures and samplers left out entirely | 53.4% / 44.5% | 77.2% / 75.6% | 74.5% / 71.2% |
| the same, and vertex/index and storage buffers left out | 60.6% / 53.2% | 82.7% / 81.7% | 79.8% / 77.4% |
| program and pipeline state only (everything else left out) | 78.5% / 70.7% | 89.0% / 88.9% | 83.2% / 80.8% |
| one component left out, the others kept: vertex/index buffer | 33.0% / 14.5% | 37.0% / 21.6% | 39.7% / 18.8% |
| ... storage buffer | 34.9% / 15.7% | 40.6% / 24.5% | 41.9% / 20.1% |
| ... pipeline state | 41.2% / 19.3% | 41.3% / 24.3% | 50.1% / 23.0% |
| ... render target | 38.1% / 18.6% | 39.9% / 25.2% | 41.9% / 21.0% |
| whole passes identical to N-1, strict (v2) | 4.7% / 1.9% | 2.3% / 2.2% | 1.5% / 1.1% |
| whole passes identical to N-2, textures left out (v2) | 7.2% / 6.3% | 25.6% / 26.2% | 13.8% / 17.5% |
| passes a frame (runs into the same targets) | ~118 | ~60 | ~80 |

Age of the draw's hash (share of `draw()` time), strict: same frame earlier 5.5 / 11.5 / 29.2%, 1 frame ago 8.0 / 10.8 / 7.6%, 2 frames 4.9 /
7.6 / 6.0%, 3-8 frames 2.3 / 2.8 / 2.0%, 9-60 frames 10.7 / 9.2 / 4.9%, **not seen in 60 frames 68.6 / 58.2 / 50.4%** (market / castle / kokiri).
With textures and samplers left out: same frame 6.0 / 15.2 / 33.0%, 1 frame 10.0 / 14.3 / 9.8%, **2 frames 31.2 / 49.9 / 37.2%**, 3-8 frames
5.1 / 5.2 / 6.2%, 9-60 frames 12.1 / 8.9 / 6.0%, new 35.5 / 6.5 / 7.8%.
Of the strict hits from earlier frames, those whose uniform buffer addresses are the same as when the hash was last seen are 59% / 46% / 35% of
the time.

What the table says:

1. **The stream is not positionally stable.** Its draw count differs from the frame before's in ~100% of the frames (culling), so "draw i is draw
   i of last frame" holds for 2-4%: spans can be matched only by hash. (Aligned by position, the first difference was the program for 65-79% of
   the draws: misalignment, not content.)
2. **Only 14-22% of the time repeats strictly against N-1/N-2.** The draws that repeat are the cheap ones: 33-40% of the draws, 14-22% of the time.
   What is new in 60 frames is 28-46% of the draws and **50-69% of the time**.
3. **The texture handle words (and, with them, the texture registrations) are what stops the match.** Leave textures and samplers out and the
   match goes from 14-22% to 45-76% of the time; leave the handle ids out but keep the registered texture (its initialization serial and view)
   and it stays at 16-26%: the registrations differ as much as the handles. Everything else (vertex/index and storage buffers, pipeline state,
   targets, dynamic state) moves it by 1-4 points each. The matches that textures hide come from N-2 more than from N-1 (castle-move: 49.9% of
   the time at 2 frames, 14.3% at 1): the rest of the draw is double-buffered (period 2), the textures follow no such period.
4. **The time is in the draws with churning textures** (the per-program table, last play window): castle-move's 5.6-8.4 us programs
   (`e6f53b8a` 110 draws, `46c14f8e` 48, `be0194ae` 13, `7ee6b6b7`, `f76f4610`, `b34e16d5`) are 8.9 + 5.2 + 1.6 + 1.8 + 1.5 + 1.3% of the time and
   repeat **0.0%** strictly and 95.8-100% with textures left out; kokiri-idle's 12-13 us programs (`eaa82471`, `23bd92f6`, `bd375eef`, `fde16ed1`,
   `cd9e931f`) and `46c14f8e` (183 draws, 6.0 us, 11.5% of the time) repeat 47-72% strictly, 99.1-99.8% without textures; market-spin's
   (`2fd8c7ca` 128 us a draw, `46c14f8e`, `7b8eefac` 18.5 us, `9a5edb88`, `be0194ae`, `17c69696`) 0-1.6% strictly. The cheap programs
   (`ffb53ed1`, 337-501 draws a frame at 1.4-1.6 us a draw, 5.7-8.2% of the time) repeat 77-98% strictly: there is almost nothing to save in them.
5. **A third to a half of the strict repeats are inside the same frame** (kokiri-idle: 29.2% of the time, 41.5% of the draws): identical draws one
   after the other, which need no cache across frames.
6. **Uniform addresses move**: of the strict repeats from earlier frames only 35-59% keep the uniform addresses; a reuse has to rewrite the rest.

## 3. What typically differs

For the draws that do not repeat: the texture handle word(s) of the program's slots, and the registration behind them (a new initialization
serial and view); for the others, the uniform addresses (the per-draw block moves in the game's ring), and for the period-2 data the storage
buffer words and vertex buffers, which alternate between two frames. Draw counts (culling) and the pass layout shift every frame. The pipeline
state, dynamic state, draw arguments and targets are the same. (Version 4, built but not run for lack of machine time, hashes the registered
texture's *storage* (its GPU address and description) beside the serial, to tell a texture object re-initialized every frame over the same
storage from a really different texture: `[age, texture storage kept, no handle ids or serials]` in its log. If the storage repeats, the
heavy draws repeat after all once textures are keyed by storage, and the question becomes how cheaply a handle resolves to its storage.)

## 4. What a reuse could give

`draw()` is 5.8 us in the parallel replay (BIND1, section 2b). What a hit could skip per draw (parallel us a draw): program lookup 0.77,
pipeline lookup 0.17, pre-lookup, checks and hazards ~0.6, the descriptor build's bookkeeping, and the texture resolution 1.55 if the key
carried the textures. What stays: the uniform ranges (0.47) and banks (0.19) whose addresses move and whose banks hold the texture handle
tables, the storage buffers (0.30), the push call (0.26), the pipeline bind (0.31) and the draw call (0.09). A hit with textures in the key
saves ~3 us (half); a hit with textures out of the key saves ~2.2 us (38%) because the texture resolution stays. Critical path = summed
saving / 4.4 (the recorders' effective parallelism, BIND1).

| | market-spin | castle-move | kokiri-idle |
|---|---:|---:|---:|
| `draw()` a frame, summed | 14.8 ms | 5.6 ms | 11.2 ms |
| strict repeats, seen in the last 8 frames or earlier in the frame | 20.7% | 32.7% | 44.8% |
| saved at 3 us a hit (50%), summed / critical path | 1.5 ms / **0.35 ms (3%)** | 0.9 ms / **0.21 ms (2%)** | 2.5 ms / **0.57 ms (6%)** |
| key without textures: repeats seen in 8 frames or the same frame | 52.3% | 84.6% | 86.2% |
| saved at 2.2 us a hit (38%), summed / critical path | 2.9 ms / **0.67 ms (6%)** | 1.8 ms / **0.40 ms (5%)** | 3.7 ms / **0.83 ms (9%)** |
| ceiling: every draw repeats, 50% saved | 7.4 ms / 1.7 ms (16%) | 2.8 ms / 0.63 ms (7%) | 5.6 ms / 1.3 ms (13%) |
| ceiling: every draw repeats, a hit costs 1 us (secondary command buffers) | 2.8 ms (26%) | 1.0 ms (12%) | 2.1 ms (22%) |

The percentages are of the frame (10.6 / 8.6 / ~9.5 ms). The +30% needs ~2.5-3 ms off the chain. Only the last line, with 100% coverage, reaches
it, and the coverage measured is 21-45% (strict) or 52-86% (textures out, but then a hit is not 1 us).

## 5. Cheaper partial wins the data shows (not built)

1. **A cache of the texture resolution that does not depend on the program's slot**: the costly draws are the ones whose handles change, so the
   per-program slot (a few ways by handle hash) misses on them ("another handle in the slot" 0.87 of the 1.0 slots resolved again a draw, BIND1),
   and each miss goes through view and sampler lookups under ParLock (1.56 ms summed, 1.1 ms of it ParLock waits). A per-thread table keyed
   by (handle word, registration version, sampler version, destroy generation) -> (view, texture, sampler), answered without ParLock (the touch
   once per texture epoch moved out of the lock), attacks the 5-13 us draws directly. BIND1 estimated 0.2-0.5 ms of the critical path for
   the lock-free touch and THIN_TEXSEC; this adds the hit for handles that came back (N-2: the rest of the draw is period 2, the handles are
   not, so how often a handle comes back is the thing to measure first, with version 4).
2. **Program lookup (1.8 ms summed, 2x dearer in parallel than serial)**: the costly programs repeat their program and pipeline state at 99%
   once textures are out of the question, so the pick can be answered from the program front (RX_VK_DRAW_PROGFRONT, off by default: "answers a
   third of the draws, no gain measurable") if the answer is made independent of the texture slots that did not change the variant's questions;
   today it is keyed by `bind_gen` with a `tex_gen` exception. Est. 0.2-0.4 ms.
3. **Same-frame duplicates**: 5.5 / 11.5 / 29.2% of the time is a draw identical (but for its uniform address) to an earlier one of the same
   frame. Whether those are adjacent was not measured; if they are, "this draw is the draw before's but for its uniform block and first/count"
   is a cheap test over a few words (no hash), which skips the program/pipeline/texture work the way the DRAW1 and THIN_* switches already
   skip parts of it. Est. 0.1-0.4 ms on kokiri-like scenes, little on the Market.
4. **The dry pass (2.35 ms serial)**: 0.65 ms is the clear-ds marks and 1.2 ms its other ops (BIND1, 2a). A hash walk cannot replace it: a
   span's effect on `NvnState` and on the written-target marks depends on the state going in, and the state is what the walk would have to
   compute. Repeats of whole passes (1-6% of the time) are too rare to pay for the digest.

## 6. Design of a reuse, for the record (not recommended on these numbers)

**What is cached.** Per recording thread (no sharing, so no lock), a table of *draw records* keyed by the draw's identity hash (section 1's
strict key, or the texture-free key of section 4): the program object and its pipeline entry (`Program*`, `PipeEntry*`, the pipeline handle
and layout), the dynamic-state words (viewport, scissor, stencil, blend colour, depth range) as already emitted, the vertex/index bind
(buffer, offset, size) and the push-constant template, the list of the program's uniform slots (stage, slot, size read), and for the
strict form the whole descriptor write template (textures included). A hit replays the record's commands and fills in what moves: the
uniform ranges (addresses, through `uniform_range` and the HL_UBO_MEMO answers), the banks (a draw's c0/c2 are made from the texture handles and
state, compared with the last as today), the storage bindings; with a texture-free key it still resolves the texture slots.

**Key and gate.** Hashing the state at the draw costs what it saves (the diagnostic's hash is 1-2 us a draw). The key has to come from the
op stream: the dry pass (serial, every op) keeps running digests per state group (program bind, vertex/index binds, pipeline-state binds,
targets, dynamic state), updated at the state ops and read at each draw to form the key, no re-hash of the whole state. The gate is exact, not
the hash alone: the record stores the digests' inputs it was made from (about 150 bytes: program serial, the state generations, the
buffer addresses, the sizes) and a hit compares them word for word with the draw's, so a collision cannot show a stale picture; texture and
uniform parts are not part of that comparison because they are re-derived. A check mode (proposed name `RX_VK_REPEAT_CHECK`): every hit also worked out the old way and compared (as
`RX_VK_DRAW_CHECK` does for the DRAW1 switches), the way a stale entry would be found before it is ever a picture.

**Uniforms and banks.** User uniform buffers are bound by address into the guest pools' mirrors (the contents are written by the game after the
recording and synced by the memory work, `vk_memory.cpp`), or by stream copies with overlays for in-stream updates; none of that is in a record:
a hit calls `uniform_range` for each slot as a miss does, so a moved address, an overlapping update or a mirror rebuilt (`gpu_bind_stamp`)
is seen. Driver banks c0/c2 stay per draw (they are the texture handle tables). The one thing a record could add is the memo of
an unchanged slot that HL_UBO_MEMO already keeps.

**Invalidation.** A record is dropped when: the program cache stamp moves or the program's variant answers change (texture type
answers); its pipeline entry is replaced or not ready; the pipeline layout changes (`ensure_layout`); the render target changes (`rt_serial`,
the target textures' pointers, formats); pool memory moved (`gpu_bind_stamp`, the buffer's mirror generation); a texture it names is
destroyed (the destroy ring, `destroy_gen`, only for the strict form); the sampler book retires a sampler (`samp_retired`); the registrations
move (`registrations_generation`, strict form). The strict form therefore dies on every texture registration change, which on the churning
draws is every frame: this is why the texture-free key is the only one with coverage.

**Fit with the parallel replay.** The records live in each recording thread's table and are filled by whichever segment drew first; a segment
on another thread does not see them (a hit rate lower by the number of recorders: 5, over the 20-60-frame life of an entry, a second warm-up
each). A shared table would need the ParLock the texture path already waits on (1.1 ms summed). The dry pass gets the digest updates (+0.1-0.3
ms on the serial 2.35, on the critical path): that cost eats a third to half of the gain.

**Expected saving.** 0.4-0.8 ms of the critical path with a texture-free key, 0.2-0.6 ms with the strict key (section 4), before the dry
pass's added digests (-0.1 to -0.3 ms): **0.2-0.6 ms net, 2-6% fps**, against the +30% target.

**Effort.** Digests in the dry pass and the key plumbing 3-4 days; the record, the gate and the invalidations 4-5; the check mode and picture
comparison in 6 scenes (shots and framelog) 3; AMD / Intel / PC 3050 runs 2+. **~12 days to default-off, plus the risk below.** Memory:
2-4 KB a record x ~1,500 live records x 5 threads = 15-30 MB, bounded by an LRU of 4,096 a thread.

**Risks.** (1) A stale record shows as a wrong picture or a device loss (a destroyed view, a moved pool): the gate and the check mode are
the defence, and neither has been measured to be cheap enough to leave on. (2) The records hold pointers into program, pipeline and
mirror objects whose lifetime is not the recording's: each invalidation above is a place for a mistake. (3) The gain is inside the
run-to-run spread of the scene (87.4 / 85.6 / 86.9 / 86.5 fps for one build in BIND1). (4) A hit rate that depends on the game's own
double-buffering (period 2 here) could change with another zone or with frame generation on.

## 7. Dead ends and caveats

- **Version 1 compared by position** (draw i of N with draw i of N-1) and found 2-4% repeats and "program" as the first difference in 65-79%: the
  draw count changes every frame and shifts the stream. Everything after it matches by hash.
- The first build failed to compile (`return void(...)` in a destructor); the second and later ones were syntax-checked first with the build's
  own flags (`clang++ -fsyntax-only`, no lease needed: reads only). Machine queue: each build and its speed lease waited 30-60 minutes behind
  other streams, which is why there are three runs of the diagnostic (v1-v3) and a fourth built but not run.
- `RX_VK_REPEAT_STATS` hashes the handle words through `handle_of`, so draws whose handles are computed per pixel (handle tables) are keyed by
  their size only; texture buffers are included, storage images are not.
- The time shares are of `draw()` summed over the recording threads, with contention and cold caches inside (5.8 us against 3.2 serial): what a
  hit saves on the critical path is a fraction of it, applied in section 4 as the 1/4.4 of BIND1.
- Not measured: the PC 3050 (its own session), a run with the Market camera still, the repeat across zone changes, the share of the
  same-frame duplicates that are adjacent, the texture storage identity (version 4, built into the branch, not run).

## 8. Reproducing

`RX_VK_REPEAT_STATS=1` (any value but 0/off) in the game's environment; the log gets `vk: repeat N presents ...` blocks every 600 presents, the
last play window's costliest programs and a dump of the texture words of the five costliest programs (draws 1, 2 and 20, this frame and the two
before). `python E:\OOT\scratch-memo1\parse.py <game_log.txt>` averages the play windows. Series: `E:\OOT\scratch-memo1\runs3.sh` (one speed lease,
three scenes, slot c, restored afterwards).
