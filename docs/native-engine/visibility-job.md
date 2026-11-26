# The visibility / render-list job 0x800998a0: specification for `hl::vis`

What the module job at guest `0x800998a0` is, how it is reached and shared between threads, what its body `0x8009bb80`
loops over, what it calls and where its time goes, which units are taken natively first and with what exactness, what is
built (`hl::vis`, behind `HL_VIS`, off), and which runs settle what is left open. Read from the user's local translation
(`%LOCALAPPDATA%\HookshotBuilder\sa\gen`, `sa\image`) and re-aggregated from the three sampled castle-move runs of
`hot-functions.md` (`build/hotfn/r1..r3`, the per-sample records). Addresses are guest addresses, offsets are in bytes.
No translated code is quoted (README, rule 4). Static work: no game was run for this document.

Conventions as in `gfx-record-job.md`: **ms** is ms of CPU per frame, mean of the three runs, under the sampler (shares
are what to read, not absolute speed). "Read" means read in the lifted code; *(inference)* marks what is concluded, not
read. The scratch scripts are listed at the end.

## The answers in short

1. **`0x800998a0` is an item body of the module job-group runner `0x8007fe60`** (call at `0x80081268`; one more direct
   caller, `0x80083960`), called directly: it is not reachable through `a64_lookup_replaced`. **Several threads enter the
   same item** (4 to 6 at once, `gfx-record-job.md` 1): the item is a small scheduler of its own that shares its work out
   by atomic bit masks and counters.
2. **Its CPU is 4.37 ms a frame** where the root is within the sampler's 16 frames (module workers 3.61, the main thread
   0.76; the `hot-functions.md` jobs table counts workers only). **The body `0x8009bb80` holds 2.30 ms** of it (1.43 ms its
   own code), the bounds/view leaf `0x808226e0` 0.46 ms, an indirect path `0x800763b0` -> `0x80494360` -> `0x80494700`
   0.37 ms, and **0.47 ms is the root's own calls into the OS layer that end in the system (YieldThread, SleepThread:
   threads waiting for each other inside the item)** *(inference: the sampled leaf is in ntdll under the root's SDK call
   sites; which of them was not told apart)*.
3. **The work is two-level**: the item's object J holds a list of views (J+48 count, J+56 pointers); each view V holds a
   list of pass items (0x5548 bytes each, V+304 count, V+312 base) and two lists of drawable-node chains (V+12936 /
   V+12944 and V+12864 / V+12872). Every list is handed out by an atomic counter on V; **the body runs once per drawable
   node** with the view's culling context and the thread's worker index.
4. **The box/plane test `0x80029240` is fully read** (42 instructions): a box against a culling volume of up to six
   planes, with an optional box-overlap prefilter. It is 0.25 ms under the body (0.21 ms in the whole game's profile) and
   is called from six functions, the recording job `0x80084de0` among them. **It is native now (`hl::vis::box_visible`,
   plain and AVX2, behind the gate `HL_VIS`, off; check `HL_VIS_CHECK=1`).**
5. **The vector kernel `0x800a8400` is the model's bounding sphere, already native** (`HL_MATH`, unit "sphere",
   `physics-loops.md` 8); under this body it is 0.04 ms.
6. **The body is not a numeric kernel**: 18,715 lifted lines, 283 calls of which 182 indirect (70 through a vtable's
   first slot), 79 atomic operations, a 2,496-byte frame, and ARM reciprocal estimates (`recomp_fp_estimate` in its
   samples, FRECPE in TICK-044's probe). Its numeric part found so far is the sub-mesh loop at `0x800a0940`: per
   sub-mesh box the frustum test and a distance test against a limit, both written natively (the second not wired).
7. **Outputs are written through the node kinds' handlers** (function-pointer tables at module data, the worker index
   passed down) and through atomically bumped counters; **who reads them was not traced** (the recording job
   `0x80084de0` runs after this job in the frame and calls the same box test itself). Because items are handed out by
   atomic counters between 4 and 6 threads, any list built in the order items are taken is ordered by thread timing in
   the translated code too *(inference)*: the native job owes the same entries, and the same order only where the
   translated order does not depend on timing (to be settled when the outputs are found).

## 1. Shape of the job

### How it is reached

| What | Read |
|---|---|
| Direct callers | `0x8007fe60` (the module job-group runner, call at `0x80081268`), `0x80083960` (1,534 lines; not seen in the samples) |
| Sampled parents | module workers through the runner (3.61 ms), the main thread through `0x80070b20` -> `0x8007fe60` (0.76 ms) |
| Text hashes (for gates) | `0x800998a0` `4d0f7cc37da30d22` (`code_hot_7.c`), `0x8009bb80` `c51a84d5360780ee` (`code_hot_4.c`), `0x80029240` `d5406b5472f5d9f5` (`code_hot_7.c`), `0x808226e0` `d351ad65c2d032f5` (`code_hot_5.c`) |
| When in the frame | 9-14 ms after a present (`gfx-record-job.md` 2, deciles of the sample instants), before the recording job `0x80084de0` (11-15 ms) and the recording job `0x8006cd60` (0-4.4 ms of the next frame) |
| Threads at once | 4 to 6 in the same sampling round (`gfx-record-job.md` 1) |

### What the root does, phase by phase (`0x800998a0`, 2,338 lifted lines, 320-byte frame)

The root takes J in x0. Every thread that enters runs the same phases; a phase's work is shared by atomic operations on
J and V, and a thread that finds nothing left waits (YieldThread, or SleepThread for a span computed from the tick) for
the flags the other threads set. The thread's **worker index** is its TLS slot value less one (`GetTlsValue` of the slot
whose number is at GOT `0x84ca2d60` -> `0x84e9fca8`); a thread whose slot holds 0 takes other paths (not read).

| Phase | What (read) | Shared state |
|---|---|---|
| A. prepare the views | for each view i of J (J+48 signed count, J+56 pointers): `0x8034dac0`(V, a small record with the worker index); when the record's flag byte comes back 1, bit i is set in J+472 | atomic OR on J+472 |
| B. set the views up | for each view whose bit is in J+472: the first thread to set bit i in J+476 runs `0x8035c940`(V) and then sets bit i in J+480 | atomic OR (J+476 claims, J+480 done) |
| C. the pass items | for each view done in phase B: an atomic counter at V+0x3c5c hands out k below V+304; pass item P = V+312 + k * 0x5548. For P: flags into V+13704 and P+0x54dc, `0x803637c0`, `0x8035a240` (the pass's +720 / +736 / +1128 fields for up to three sub-passes of 0x480 bytes), **`0x80365f00` (a GPU memory invalidate: `rx_nvn_invalidate`)**, `0x804e61f0`, **`0x80822260`(P+448, P'+1544) -> `0x808226e0`**, `0x8025b910`, `0x80099050`, an indirect call (vtable +72), `0x800ac7a0`; then two done counters | atomic add per view |
| (waits) | YieldThread between phases; SleepThread(ConvertToTimeSpan(tick)) while an acquire-loaded byte's bit 0 is clear | |
| D, E. more per-view work | claimed the same way: `0x800adc20`, `0x800994b0` or an indirect call, `0x80099350`, `0x807ce270`, `0x800991c0` (not read further) | atomic add / OR |
| F. **the drawable nodes** | for each view whose bit is in J+520: (1) an atomic counter at V+0x32d8 hands out k below V+12936; the chain at V+12944[k] is walked (node +16 next); each node's +30 bit 2 is cleared and, for a node whose +48 count is 1 or more, each object of its vector (+32 .. +40) gets a virtual call (slot 0) with the float at C+13760 and C+15148 first; then **the body** (site `0x8009ab00`); the chains done are added to V+0x32dc. (2) The same with the counter V+0x32c0 below V+12864 over the objects at V+12872 (their +576 / +577 flag bytes decide; bit 3 of +577 is cleared), **the body** at site `0x8009ac4c` per node of their chains | atomic add |
| G. the rest (lines 1,640-2,338) | `0x800ad2b0` (-> `0x800ad840` -> `0x81270c20`: 0.17 ms), `0x807f6960`, `0x800995a0` (a third caller of the body), `0x835afcb0`, `0x836286f0`, `GetCurrentCoreNumber` six times, two static guards | not read |

**The body's arguments** (both sites, read): x0 = the node's object N (chain node +0), w1 = a 16-bit pass mask (V+12960),
x2 = the view's pass array (V+12928; 0x830-byte entries), w3 = a byte (V+12962; the number of passes, used below 4 / 3),
x4 = the view's culling context C (V+12912), w5 = the worker index.

### What the body loops over (`0x8009bb80`)

Read as far as the structure goes; the node kinds' handlers were not followed.

| Step | Read |
|---|---|
| Entry | N+22 bit 0 cleared; N+18 bit 0 sends the call to a path not read; M = N+56 (its +24 zeroed, +33 bit 0 tested); N+8 ANDed with C+15148; N+16 ANDed with w1; with bit 7, N+20's two low bits cycle modulo its bits 2-3 |
| Pass selection | for each pass j below w3 (at most 3 or 4), when the pass entry's u16 at x2 + j * 0x830 has the bit the node's mask selects, j is written to a list on the stack (+2240) |
| Kind dispatch | a function pointer from a table at module data indexed by five flag bits, compared with three known implementations (inlined) or called indirectly with (N, x2, pass list, C, mask, worker index) |
| Sub-mesh loop (one inlined handler, `0x800a0940`..) | over a model's sub-meshes (56-byte descriptors, u16 at +52): each sub-mesh's 32-byte box (array at the model's +64, 32 bytes apart) against the pass's culling volume (`0x80029240`; section 2) and, unless bit 31 of the sub-mesh's table entry +4 is set, the distance test of section 4.3 against the pass's culling context (+840 plane, +1696 limit); runs of consecutive sub-meshes that pass are merged (the loop's indices). What a run produces was not read |
| Counters | atomic adds on +3380 of a per-view object, on +240 and +32 of a per-pass object (one and a triangle count), and a node pushed on a list at +104; stats-like *(inference)* |

### Call tree with sampled time (CPU, all threads; inclusive within the 16-frame stacks)

| Function | inclusive ms | share of the job | what |
|---|---:|---:|---|
| **`0x800998a0`** | **4.37** | 100% | root; its own code 0.08; **0.47 in the system under its SDK calls** (the waits) |
| `0x8009bb80` | 2.30 | 52.7% | the body; its own code 1.43 |
| -- `0x80029240` | 0.25 | 5.7% | the box test (all its time is its own) |
| -- `0x805879e0` (-> `0x80361c80`, `0x80587c80`) | 0.14 | 3.1% | not read |
| -- `0x81500200` (-> `0x80361c80`) | 0.11 | 2.5% | not read |
| -- `0x8009ba60` (-> `0x80587c80`) | 0.07 | 1.5% | not read; calls `nvnBufferMap` |
| -- `0x83647b20`, `0x812342c0` | 0.04, 0.04 | 1.0%, 0.8% | both are GPU memory invalidate sites (`memory-boundary.md`) |
| -- `0x800a8400` | 0.04 | 0.9% | the bounding sphere (native: `HL_MATH`) |
| -- `0x8009b7b0`, `0x836698b0`, `0x83650800` | 0.02-0.03 each | | not read |
| `0x80822260` -> **`0x808226e0`** | 0.47 / 0.46 | 10.5% | per pass item; 2,912 lifted lines, 116 FMADDs, 18 FDIVs, three copies of 64 / 96 bytes in, two `GetSystemTick` calls *(inference: the view's matrices and the volumes derived from them)* |
| `0x800763b0` -> `0x80494360` -> `0x80494700` (-> `0x8049dd00`) | 0.37 | 8.5% | reached through an indirect call of the root; `0x8049dd00`'s own code 0.25 |
| `0x800ad2b0` -> `0x800ad840` -> `0x81270c20` | 0.17 | 3.9% | phase G |
| `0x8034dac0` (-> `0x80364ac0` -> `0x80364ee0`) | 0.16 | 3.7% | phase A |
| `0x80365f00`, `0x80362ff0` | 0.11, 0.06 | 2.5%, 1.4% | GPU memory invalidates (`rx_nvn_invalidate`, the system under it) |
| `0x80731040` (-> `0x80732f40` -> `0x80733120`) | 0.10 | 2.3% | through an indirect call; not read |

Leaf kinds under the job: lifted code ~3.0 ms; the system under SDK calls of the root 0.47; under `rx_nvn_invalidate`
~0.14; the rest small. *(The 16-frame cut hides little here: the body is 3 to 5 frames below the thread's root.)*

## 2. Inputs

| Structure | Offsets read (as far as read) |
|---|---|
| Item J (x0 of the root) | +48 view count (signed), +56 view pointers, +472 / +476 / +480 / +520 bit masks (one bit a view), more fields in phases D-G not read |
| View V | +304 pass items' count, +312 their base (0x5548 bytes each), +7024 / +7040 / +7048 (tables indexed by a pass's byte +8), +12288.. the node lists: +12864 / +12872 (second list), +12912 the culling context, +12928 the pass array, +12936 / +12944 (first list), +12960 u16 pass mask, +12962 u8 pass count; counters +0x32c0, +0x32d8, +0x32dc, +0x3c5c; +13704, +15124 / +15128 / +15140 flag words, +15176 / +15184 |
| Culling context C (x4 of the body) | +3464 (a sub-structure), +13760 float, +15148 u32 mask, +15224 pointer |
| Pass entry (0x830 bytes, x2 of the body) | +0 u16 mask (the rest not read) |
| Sub-mesh loop's per-pass objects | the culling volume is loaded from +248 of one object and the distance test's context (+840 plane, +1696 limit) from +2072 of another, both picked by the pass index; which structures these are was not settled |
| Node N (x0 of the body) | +8 u32, +16 u16, +18 u16, +20 u16, +22 u8, +56 M, +72, +80, +96 / +104, +144, +360 |
| **Culling volume** (x0 of `0x80029240`) | +0 box minimum (4 floats), +16 box maximum (4 floats), +32 + 32 i plane i's normal (4 floats) and +48 + 32 i its offset (i < 6), **+224 the plane count (signed)**, **+228 a non-zero word: test the box first** |
| **Box** (x1 of `0x80029240`) | +0 minimum (4 floats, w included), +16 maximum |

**Who writes them, and when**: not read. The volume's planes are the likely product of `0x808226e0` in phase C
*(inference: one call per pass item, before the nodes of phase F, with FMA-heavy matrix work)*. **Read in place by
gameplay**: not searched.

## 3. Outputs

Read: the body's counters (atomic adds), N+22 / N+18 / N+20 / M+24 written, a node pushed on a list at +104 of an
object, the stack list of passes; the kind handlers (through tables) receive the worker index and the pass list and are
where the render lists are written *(inference)*. **Not established**: the render lists' layout, their readers (the
recording job `0x80084de0` is the first candidate: it runs next in the frame and reads the same culling volumes through
`0x80029240`), and whether any gameplay function reads what this job writes.

## 4. The units read whole

### 4.1 `0x80029240`: a box against a culling volume

Arguments x0 = the volume V, x1 = the box B; result w0: 0 culled, 1 visible. No memory written.

1. When V+228 is not zero: if any of the four lanes of V's minimum compares greater than the same lane of B's maximum
   (FCMGT, the lanes summed by ADDV and the sum tested for zero), 0. Then the same with B's minimum against V's maximum.
2. n = V+224: when n, signed, is below 1, the result is 1.
3. For each plane i in order (i < n): the corner c with lane k = B.min[k] when normal[k] >= 0 (FCMGE against zero: -0
   counts as >= 0; a NaN takes the maximum), else B.max[k]; m = normal * c on four lanes; s0 = m2 + m0, s1 = m3 + m1;
   t = (s0 + s1) + offset. **When t > 0 the result is 0** (the box lies wholly on the plane's positive side). After the
   last plane, 1.

The w lanes take part in both steps. With a NaN the compares are false (step 1 does not cull; step 3's FCMP is unordered:
not > 0). Flush-to-zero (the guest's FPCR.FZ) changes compares with subnormal operands and products or sums near the
smallest normal.

### 4.2 Callers

`0x8009bb80` (2 sites, the sub-mesh loop), `0x80084de0` (4), `0x80078fc0` (2, the cluster paths of the sub-mesh
submission, `gfx-record-job.md` 9), `0x8008b3e0` (2), `0x8008d640` (2), `0x836063a0` (2).

### 4.3 The body's distance test (`0x800a0968`..`0x800a0a2c`, and again at `0x800a0a64`..)

On the sub-mesh's box B and the pass's culling context's plane (n0..n3 at +840..+852) and limit L (+1696), h = 0.5 (a
register the body sets before the loop): cx = h (B.min.x + B.max.x), cy = (B.min.y + B.max.y) h, cz likewise;
ex = h (B.max.x - B.min.x), ey = (B.max.y - B.min.y) h, ez likewise (each sum a four-lane add of which lanes x y z are
used); a = n1 cy; **a = n0 cx + a (FMADD)**; **a = n2 cz + a (FMADD)**; d = n3 + a; p0 = n0 ex taken negated when it
compares below 0, p1 = n1 ey likewise, s = p0 + p1, p2 = ez n2 likewise, r = p2 + s; u = (-d) - r. When u < L the loop
goes on with the run of sub-meshes; otherwise it branches to `0x800a1120` (not read).

## 5. Locks, atomics and waits

- **No mutex in the root or the body.** Sharing is by atomic OR on bit masks (one bit a view: claimed, prepared, done),
  atomic add on per-view counters (the index handed out, the work done), acquire loads of flag bytes, and the waits of
  section 1 (YieldThread; SleepThread from the tick). The body has 79 atomic operations (adds, ORs, ANDs, compare-and-swap
  pairs and acquire loads), most in its handlers' counters and list pushes.
- **Order**: items go to whichever thread bumps a counter first. Anything appended in the order items are processed
  (a list pushed at +104, the counters' order) depends on thread timing in the translated code *(inference)*.
- **Through pointers**: the kind handlers (table at module data, three known ones inlined), a vtable slot 0 per object of
  a node's vector (phase F), slots +72 / +32 / +0 of other objects in the root, and sub-object methods in the body (vtable
  offsets +488 (36 sites), +496 (10), +16 (9), +40 (6), +56 (4), +24 (3), +1216 (2)).

## 6. The cut

| Order | Unit | Why | Exactness it needs | State |
|---|---|---|---|---|
| 1 | **the box test `0x80029240`** | fully read, a leaf, 0.25 ms here and called by the recording job too; a gate answers all six callers | its result decides what is drawn: the same 0 / 1 as the translation on every call. Bit-exact arithmetic on the values it uses (sums in the guest's order; no FMA: the guest has none here) | **written**, gated, checked: `HL_VIS`, `HL_VIS_CHECK` (section 7) |
| - | the sphere `0x800a8400` | | | native already (`HL_MATH`) |
| 2 | **the bounds / view leaf `0x808226e0`** | 0.46 ms, one caller, called directly, no indirect call | it writes floats the box test and the body read: bit for bit, 116 FMADDs reproduced as single roundings, 18 divides correctly rounded (Exact.h's rules) | **not read**: the next unit |
| 3 | **the body's sub-mesh loop** | the body's numeric core found so far: two tests a sub-mesh box over arrays, AVX2 work | the same verdicts per box (both tests bit-exact on what they compute: the distance test's two FMADDs single-rounded), the same runs merged | the two tests **written** (`box_visible`, `boxes_within`); the loop's run merging and its output not read: not wired |
| 4 | the body | 1.43 ms of its own code; an object walk over node kinds | its writes to nodes and lists exactly; the ARM reciprocal estimate (FRECPE) reproduced bit for bit where it feeds stored floats | not started: the kind handlers and the outputs to map first |
| 5 | the job (the root) | the scheduling: phases A-G, claims, the waits (0.47 ms of sampled CPU in the system) | timing only: the same work done; list order only where the translated order is deterministic | not started; the natural home is the native job system (`hl::jobs`) once units 3-4 run natively |

`hl::vis` is its own namespace, not `hl::gfx`: the job decides what is drawn before any recording, has its own switch,
and its tests are numeric kernels that share `hl::math`'s exactness rules (`hl/math/Exact.h`), not the recording
module's NVN seams.

## 7. What is built (branch `stream/v1-visibility`)

| Piece | Where | What it does |
|---|---|---|
| The tests | `engine/native/include/hl/vis/Cull.h`, `src/vis/Cull.cpp` | `box_visible` (4.1) and `box_within` / `boxes_within` (4.3), each with a plain path and an AVX2 path (`target("avx2,fma")` per function; the path chosen once from the CPU, `use_avx2` to force the plain one). AVX2: the box test takes two planes a step (one in each 128-bit half; plane i's verdict before plane i+1's, as the guest stops at the first plane that culls), the distance test eight boxes a step (corners gathered 32 bytes apart, the guest's two FMADDs as `vfmadd`) |
| Exactness | same | every value a test uses is checked as the guest's instruction uses it (`hl/math/Exact.h`'s Guard): NaN, infinite or subnormal operands and results that are not normal (or an exact zero) decline, and the translated function runs. The overlap prefilter only compares, so it accepts infinities. The plain path's FMADD rounds once through binary64 with Knuth's two-sum and a one-step correction on a binary32 midpoint, so it never declines where the FMA instruction does not. An AVX2 lane any rule would decline is settled by the plain path: the two paths agree by construction |
| The bridge | `include/hl/bridge/VisBridge.h` | `CullVolume` (box +0, planes +32 x 32, count +224, has-box +228), `CullPlane` (offset +16), `CullBox`, `SubmeshCullContext` (+840 plane, +1696 limit), each field `static_assert(offsetof)`; a plane count above six is not answered (the guest would read past the volume) |
| C surface | `include/hl/c/hl_vis.h`, `src/c/hl_vis.cpp` | `hl_vis_box_visible` (1 / 0, -1 declined, -2 plane count), `hl_vis_box_within`, `hl_vis_use_avx2`, `hl_vis_last_why` |
| OS layer | `engine/host/hl_vis.c` | **`HL_GATE(80029240, "d5406b5472f5d9f5")`**; `HL_VIS` (default **0**), `HL_VIS_CHECK=1` (native verdict, then the translated function for real under a per-thread bypass, w0 compared; the game gets the translated result), `HL_VIS_AVX2=0`, `HL_VIS_LOG=1` (counters every 10 s: calls, native, declined by reason and rule, culled / visible, callers by return address, fpsr-differs). With `HL_VIS_LOG=1` only, two counting gates: **`HL_GATE(800998a0, "4d0f7cc37da30d22")`** and **`HL_GATE(8009bb80, "c51a84d5360780ee")`** count the root's calls by work object and views, and the body's by worker index, pass byte and view context; they answer nothing |
| Tests | `engine/native/tests/vis_test.cpp` | vectors from the reading: no plane, a negative count, a box touching a plane, a degenerate box on and just off a plane, -0 normals, the w lane, the guest's sum order (a case left-to-right summing gets wrong), early exit (a NaN in a plane after the culling one is not used), six planes in pairs and odd counts; declines (NaN, infinities, subnormal operands, underflowing and overflowing products), the prefilter (touching, w alone, infinite volume, subnormal in the compare not reached); the distance test's arithmetic, its FMADD (a case two roundings get wrong) and a binary64 midpoint case; 300,000 random box tests and ~76,000 random distance tests plain against AVX2 (verdicts and decline reasons equal); the C surface over the guest layouts |

A native answer sets FPSR's IXC as `hl_math.c` does (the translation's fast path stays open); the check counts calls
whose FPSR differs. The gates go into `code_hot_7.c` (`0x80029240`, `0x800998a0`) and `code_hot_4.c` (`0x8009bb80`): a
build of this branch recompiles those two hot files.

**Not verified**: nothing of this has run in the game. The verdicts' equality with the translation is argued from the
reading and tested against vectors from it, not compared on live inputs; how often calls decline in the game is unknown.

## 8. Open questions, and the runs that settle them

| Question | What settles it |
|---|---|
| Does the native box test agree with the translation on every live call? | R1: `HL_VIS_CHECK=1` mismatches (the bar: 0), compared calls, fpsr-differs |
| How often does it decline, and why? | R1: declined by reason (fpcr, values by rule, planes) |
| Which callers matter? | R1: the callers line (return addresses: the body's two sites `0x800a096c` / `0x800a0a68`, the recording job's, the sub-mesh submission's) |
| How many views, pass items and nodes a frame; how many threads enter one item | R1 with `HL_VIS_LOG=1`: the shape lines (root calls by work object over the run against the frames; views seen; body calls by worker index and view context) |
| Is the native box test right in the picture? | R2: `HL_VIS=1` validation in the three scenes, shots looked at |
| The plain path in the game | R3: `HL_VIS=1 HL_VIS_AVX2=0`, one scene |
| The render lists: layout, readers, determinism | static: the kind handlers' tables and the recording job's reads (next static step); then a run with a write probe on the lists |
| What `0x808226e0` computes and writes | static reading (next unit) |
| The 0.47 ms in the system under the root: which SDK calls (Yield or Sleep) | a run with `HOS_JOBTRACE` over the item, or the sampler with the host frames kept |

**Runs asked of the orchestrator** (function only, no speed; any machine; a build of this branch):

- **R1, the check**: `HL_VIS_CHECK=1 HL_VIS_LOG=1` in castle-move, kokiri-idle, hyrule-walk (110 s each). Report from
  each `game_log.txt`: the start line `hl vis: box test checked, ... path`; the last `hl vis: box:` line (calls,
  declined by reason, culled / visible, compared, **mismatches**, fpsr-differs); `declined by rule`; `callers`; any
  `MISMATCH` lines with their volume and box bytes; the three `hl vis: shape:` lines; the run's frame count.
- **R2, validation** (only when R1 shows 0 mismatches): `build/s5/valid.sh <tag> <bin> HL_VIS=1 HL_VIS_LOG=1`: per
  scene ran / stalled, game-speed ratio, the `hl vis:` lines (native count), the memory table, the shots against
  `refshots-<scene>`.
- **R3**: as R2's castle-move with `HL_VIS_AVX2=0` (the start line must say "plain path").

## 9. Runs R1-R3, the body's node kinds, the sub-mesh loop's extent (2026-11-14, evening)

**R1-R3** (main PC, build of `64d7020b`; the orchestrator's runs): `HL_VIS_CHECK=1` compared 615,171 / 534,708 /
964,497 box calls (kokiri-idle / castle-move / hyrule-walk) with **0 mismatches, 0 declined, 0 fpsr-differs**; callers
`0x800a0968`, `0x800a0a64` (the sub-mesh loop: 85-90%), `0x800792d8`, `0x80079324` (the sub-mesh submission's cluster
path), `0x8008dc4c`, `0x80087e8c`. One work object, the body spread evenly over workers 0-5, pass byte 1 only, one view
context. `HL_VIS=1` (R2, `valid.sh`, three scenes) ran to the end, game speed 59.8-60.8, all calls native, shots right;
`HL_VIS_AVX2=0` (R3, castle-move) clean by log. By the owner's direction `HL_VIS` stays 0: a per-box gate is a crossing
a box, and is to be switched on only inside a native loop.

**The node kinds** (`HL_VIS_LOG=1`, build `91463f27`, main PC slot a, runs `v1k-castle-move` / `v1k-kokiri-idle`, last
report). The body classifies a node at its entry by five early paths, then by six bits of its masked pass mask and
state into a 64-entry handler table at `0x84c30038` (16 bytes apart; static: 64 template instances `0x8364f5d0` ..
`0x8366b950`); entries 19, 27 and 51 are compared with and inlined, the others called. Shares are of the body's time
stamp counter ticks (the gate runs the body itself, so the shares include the gate's own cost; no speed is read from
them):

| Kind | castle-move: calls, % of the body's time | kokiri-idle: calls, % | box tests under it (castle / kokiri) |
|---|---|---|---|
| 59 `0x836698b0` (called) | 197,391, **43.4%** | 268,919, **48.2%** | 3,843,155 / 5,702,030 |
| early: N+72 set | 206,246, **21.4%** | 273,829, 21.6% | 0 |
| early: N's vtable +672 not the expected function | 9,619, 10.0% | 12,530, 8.4% | 0 |
| early: N+18 bit 9 with an empty list | 96,100, 10.0% | 126,994, 9.2% | 732 / 18 |
| 19 `0x836571f0` (inlined) | 62,935, 5.1% | 84,565, 4.8% | 0 |
| 27 `0x8365b460` (inlined) | 107,482, 3.8% | 144,842, 3.6% | 0 |
| early: N+18 bit 0 | 1,310, 2.6% | 692, 0.7% | 5,458 / 35 |
| 3 `0x83650800` (called) | 32,084, 2.0% | 42,471, 1.7% | 0 |
| early: N+360 set | 9,679, 1.7% | 12,771, 1.7% | 101,162 / 135,247 |
| 51 `0x83665810` (inlined) | 1,992, 0.1% | 2,619, 0.1% | 2,361 / 0 |

So **one kind, 59, holds 43-48% of the body's time and nearly all its box tests**; the early N+72 path a fifth. The box
tests counted under kind 59 come from the body's own sub-mesh loop (the sites are in `0x8009bb80`), which therefore runs
after that kind's handler returns *(inference from the attribution; the path from the handler back to the loop was not
read)*. **The box counts, settled**: these runs count 4.0 M (castle-move) and 5.9 M (kokiri-idle) box tests in all, against
R1's 0.53 M and 0.62 M. No counter is wrong: in one run with both (`v1c-castle-move`, slot a, `HL_VIS_CHECK=1
HL_VIS_LOG=2`) the checked gate counted 4,923,486 calls and the per-kind counts add up to the same; and a run with
the body left alone (`v1d-castle-move`, `HL_VIS_LOG=1`, count only) counted 7,168,238 in 3,934 frames, so the timed
gate does not cause it either. **The difference is the slots**: R1 and R2 ran in slot b (175-330 box tests a frame),
these in slot a (1,800-1,950 a frame); each slot has its own copy of the saves, and the same scripted scene then looks at
different things *(inference: the save's place or time; R2's note that slot b's hyrule-walk save ends in a pond is
the same kind of difference)*. Figures a frame must name their slot. Crossings a frame, slot a castle-move: about 1,820
box-test crossings (95% from the sub-mesh loop's two sites) and about 380 body calls; answering the body at its entry
for a node replaces its box crossings by none.

**The sub-mesh loop's extent** (read): from `0x800a0940` to its back edge at `0x800a16f8` (lifted lines 6,930-9,320, of
which the two tests of section 4 are a small part). A sub-mesh that passes the frustum test and fails the distance test
goes to **an occlusion test**: its box projected (`0x800a7f00`, and about 400 lines of inlined projection: corners
against the context's matrices) and looked up in the culling context's depth pyramid (a tile loop with many exits).
Visible sub-meshes extend a run; a run ends in one of two ways: **a 6-byte record** (u16 first sub-mesh, u16 count, u16
a pass value) appended to a buffer whose pointer the body keeps on its stack, or, without that buffer, **an indexed draw
recorded at once** (`0x8002a5f0` BufferGetAddress, `0x8008f840` DrawElementsInstanced: the body records NVN draws itself
on that route). A loop that answers this whole needs the occlusion test and the draw route native too, and a hook
inside `0x8009bb80` (the loop is inlined: entry gates cannot reach it; `nx2/hl_gates.py` would need a site hook at
`0x800a0940` with the loop's exits as targets, as it has step hooks).

**The render-list entry** (read, at `0x800a1780`..): 24 bytes, +0 u64 a sort key (a byte of the node at +32 and a value
shifted left 8, the whole shifted left 12), +8 u32, +12 u16 zero, +14 u16 flags (a sub-mesh byte's low four bits and a
bit of the node's +30), +16 the node; written to an array on the body's stack-held pointer at index i, and its pointer
appended to a list (an array at +72 of a per-pass object, its u16 count at +80) **with a plain increment, not an atomic**:
each such list is written by one thread at a time *(inference: one list a worker, the worker index the body is given)*.
Then the node's +24 gets bit 4. The lists' readers: still not traced.

## 10. Hand-over (for the next session of this stream)

Read first: this document's sections 1, 4, 6, 9; then `engine/host/hl_vis.c` (all the switches and counters) and
`engine/native/include/hl/vis/Cull.h`.

| What exists | Where |
|---|---|
| Native tests (box against volume; the distance test; plain and AVX2) | `engine/native/{include,src}/hl/vis/Cull.*`, tests `engine/native/tests/vis_test.cpp` |
| Bridge (volume, box, context layouts) and C surface | `include/hl/bridge/VisBridge.h`, `include/hl/c/hl_vis.h`, `src/c/hl_vis.cpp` |
| Gates | `HL_GATE(80029240)` (the box test: native with `HL_VIS=1`, checked with `HL_VIS_CHECK=1`, counted with `HL_VIS_LOG=1`); `HL_GATE(800998a0)` and `HL_GATE(8009bb80)` (on only with `HL_VIS_LOG`: counts; the body's gate runs the translated body itself, timed by node kind) |
| Log lines | `hl vis: box test ...` (start), `hl vis: box: calls ...`, `declined by rule`, `callers`, `hl vis: shape: ...` (root and body), `hl vis: kinds (...)` (node kinds, boxes under each) |
| Scratch tools | `E:\OOT\scratch-from-c\v1`: `showfull.py <hex> <out>` (a lifted function unabridged), `cond.py <dump> <from> <to>` (a stretch condensed), `tree.py <f_root> [depth] [min]` (the sampled call tree), `q.py`, `rd.py`, `index.pkl`; `fn/*.c` dumps; `ntest.ps1`, `suite.ps1` (the native tests, the whole suite) |
| Runs so far | `build/s5/v1r1-*`, `v1r2-*`, `v1r3` (orchestrator), `v1k-castle-move`, `v1k-kokiri-idle` (kinds), `v1c-castle-move` (both box counters) |

How to run the counters: build with `mkg.ps1 -Root <worktree>/engine -Name v1-... -Slot <slot>` (the three gates put
into `code_hot_7.c` and `code_hot_4.c`), then `build/s5run.sh --slot <slot> <run> <scene> HL_VIS_LOG=1` (add
`HL_VIS_CHECK=1` for the box check and its own count).

`HL_VIS_LOG=1` counts node kinds and leaves the body alone; `HL_VIS_LOG=2` runs and times the body by kind (the shares
of section 9 were taken so).

**The owner's cut (2026-11-14, late), which replaces any hook inside the body**: answer `0x8009bb80` at its entry (its
gate, today a counter, becomes the answering gate under `HL_VIS`): first the three early paths (N+72 set; vtable +672
not the expected function; N+18 bit 9 with an empty list: 39-41% of the body's time), then kind 59 with the sub-mesh
loop that follows its handler (the handler `0x836698b0` may stay a call back to the translation; the loop, its box and
distance tests in batches, the occlusion part and both endings native around it); every other kind declines at the
entry and the translated body runs unchanged. Required before the large part is written: the path decided at the entry
**without any write** (a path whose condition follows a side effect is answered whole or declined before it); the three
early paths' real size and writes (the N+72 path takes ~31k ticks a node: not a bare return); a whole-node check under
`HL_VIS_CHECK` (every write of the translated body for that node: list entries and counts, the 6-byte records, NVN
draws recorded on the spot, node and view fields; compared per node where the worker matters); crossings before and
after, a frame, with the slot named. Note the body's entry already writes (N+22 bit 0 cleared, M+24 zeroed, N+20's
counter cycled) before the kind is known: the gate decides on the values read before those writes and makes them
itself when it answers.

Next steps after that, in the orchestrator's order: (1) done (above); (2) the waits: count YieldThread / SleepThread per
worker while inside the job, and guest mutex locks under it (needs a per-thread "inside the job" flag set by the root
gate running the root itself, as the body gate does, and counters at the OS layer's yield, sleep and lock entries);
(3) read kind 59's handler `0x836698b0` with the sub-mesh loop as one unit (occlusion included) and give the cut and the
site hook's form before writing; then the N+72 path; (4) trace the readers of the 24-byte entries (`0x80084de0` first).

## 11. The body's real shape: preludes and one dispatch (third session, read from the lifted body)

**Finding that changes the cut: no "early path" ends the body.** The body is a fixed sequence of steps, each taken or not
by the node's state, and every one falls into the next; the function returns nothing and its only exit is after the
dispatch. The first session's "early paths" are preludes: a node counted under one of them goes on to the later preludes
and then to the dispatch (the handler by index), so a prelude cannot be answered at the entry without also answering the
dispatch and the handler of that node. That is why the N+72 nodes cost about 31k ticks: the time is mostly the dispatch
that follows. The kinds table of section 9 therefore says "first prelude matched", not "what the node does".

The sequence, with what each step reads and writes (N the node, M = N+56, C the culling context, x2 the pass array):

| Step | Taken when | What it does (read) |
|---|---|---|
| Prologue | always | clears N+22 bit 0 |
| P1 flag18 | N+18 bit 0 | calls a virtual method (slot +16) of the object embedded at N+144; when it answers true, calls the first method of that object's owner with a record on the stack (node, pass list empty); then on to P2 |
| Prologue 2 | always, after P1 | zeroes M+24 |
| P2 m33 | M+33 bit 0 | calls `0x8051f560`(M, N), clears M+33 bit 0, sets bit 0 of one byte in each of M+32 records (120 bytes apart, array at M+0); then on |
| Prologue 3 | N+16 and the pass mask have bit 7 | N+20's two low bits cycle: (low + 1) modulo the count in its bits 2-3, the count kept |
| P3 vtable672 | the method at the node's vtable +672 is not the expected function | indirect call of it with (N, C, mask = N+8 and C+15148, the pass array, the worker index); then P5 or P6 by N+18 bit 9. **Every such node also has N+360 set** (counts below): it does P4 first |
| P4 n360 | N+360 non-zero | loops over two arrays of objects through the record at N+360 (+40 / +56, counts at +32 / +48), multiplying a float of C by a float of the record and calling virtual methods (slots +24, +56) of each; rewrites N+20's high bits |
| P5 list | N+18 bit 9 and the list at N+96 empty (N+96 equals N+104) | the node's vtable +744 must be the expected function (else it is called, and the step stops); clears N+18 bit 9; with N+36 (u16) zero, nothing else; otherwise loops that many entries of the array at N+48: the bounding sphere kernel `0x800a8400`, vector adds, entries pushed on the list at N+96 |
| P6 n72 | N+72 non-zero | record P: when P+112 bit 5 is set (95% of nodes): P+36 gets the u16 at P+38 and N+18 bit 8 is cleared; otherwise a long loop that resets P's float fields to extremes and walks the array at P+16 (count u16 at P+34), calling virtual methods |
| P7 n80 | N+80 non-zero | zeroes the u16 at +18 of the object it points to |
| Dispatch | always | the pass list (stack records of 168 bytes initialised, the passes whose mask matches), then the handler by the table index (kinds 59, 19, 27, 51 inlined or called, the others by pointer), the sub-mesh loop after kind 59, the endings |

(P1 and P2 are checked before the mask and the N+20 cycle; the order above is the translated order.)

**The three prologue writes and the decision.** None of the reads that decide the route is a field the prologue writes: the
decision reads N+18, M+33, the vtable, N+360, N+96 / N+104, N+72, N+80, N+8, N+16, M+44 and the pass array, and the
prologue writes N+22, M+24 and N+20. So the route can be computed read-only before them, as the owner required, and the
dispatch index too. The route of a node is exact for a node with no prelude ("plain"); for the others the entry reading
names the preludes the body starts with, and a prelude's own effects (its calls) can add later ones.

**The gate** (`HL_VIS=1`; `HL_GATE(8009bb80)`): reads the route, counts it, and declines every node; with `HL_VIS_CHECK=1` it
compares the three prologue fields before its reads and after: the gate's own part wrote nothing. `HL_VIS_BOX=1` is now the
per-box test's switch (it was `HL_VIS`).

**Counts** (main PC, slot a, build `v1e-gate`, `HL_VIS=1 HL_VIS_CHECK=1`; the box check ran alongside, 0 mismatches; any
figure names its slot; nodes are the gate's calls over the whole run):

| Scene | nodes | plain | plain by handler index | with a prelude: P5 only / P6 only / P3+P4 / P4 only | prologue mismatches |
|---|---:|---:|---|---|---:|
| castle-move | 285,473 | 155,771 (54.6%) | 59: 75,663; 27: 42,046; 19: 24,526; 3: 12,710; 51: 826 | 38,027 / 81,410 / 3,751 / 3,816 | 0 of 285,473 |
| kokiri-idle | 469,631 | 262,627 (55.9%) | 59: 130,469; 27: 69,820; 19: 40,563; 3: 20,461; 51: 1,314 | 60,929 / 132,672 / 6,030 / 6,142 | 0 of 469,635 |
| hyrule-walk | 963,036 | 534,315 (55.5%) | 59: 257,424; 27: 145,710; 19: 85,671; 3: 42,901; 51: 2,609 | 129,697 / 270,426 / 13,105 / 13,032 | 0 of 963,039 |

(N+72 nodes with bit 5 of their record clear, the long form: 7,058 of 81,410 in castle-move, 1,374 of 132,672 in kokiri-idle,
7,062 of 270,426 in hyrule-walk. The three runs ended normally, no crash. The steps P1, P4, P5 and P6's long form were read
only as far as the table says; the loop bodies were not followed.)

**Hand-over 3** (end of the third session): the gate and its counters are committed and run clean (above); no node is
answered. Next, in this order: (1) the plain-59 node in full: read the dispatch from the pass list to the handler call and
the sub-mesh loop's two endings (section 9 has the loop; the dispatch tail after the handler is not read), write the pass
list natively, call the handler `0x836698b0` back as a guest function through `hl_translated`, then the loop; (2) the
whole-node check: take the translated body's writes (node fields, the list entries, the 6-byte records, the counters) by
running it on the same node first when the check is on, and comparing with what the native answer computed on a node
whose state was saved; (3) plain 27, 19, 3; (4) the preludes P5 (N+36 zero) and P6 (short form) in front of a plain
dispatch.

**What this means for the owner's cut.** Answering "the three early paths" alone is not possible: each is a prelude of a
body that goes on. What can be answered at the entry is a whole node: its preludes, then its dispatch. Plain nodes are 55%
of the calls, and nearly half of those (kind 59) are the box-test heavy ones; the next whole-node unit is therefore **a
plain node of kind 59 in full** (prologue writes, the pass list, the handler `0x836698b0` called back, the sub-mesh loop,
its endings), then plain 27 / 19 / 3 (inlined or called handlers, no box tests); a node with a prelude is answered only
when its prelude is also written (P5 with N+36 zero and P6's short form are the cheap ones: a few stores and a test, and
together 42% of the calls). The check for such answers is whole-node, as the brief says: run the translated body on a
copy of what it writes, or run it for real and compare what the native answer computed; not written yet.

## 12. The dispatch's tail, the whole-node check, and why no node is answered yet (fourth session)

**The dispatch and its tail, read** (lifted body, from the end of the preludes to the return). The pass list is 33 records of
56 bytes in the body's stack frame (11 chunks of 168 bytes, 2,496 bytes of frame in all), initialised to empty (a zero
pointer first, a byte of 4 at +27, a float 1.0 at +40). The dispatch picks the handler from the table of section 9 by the
index; the handlers of kinds 19, 27 and 51 are compared with by address and their code is **inlined** in the body (after
which each calls virtual methods of the object embedded at N+144 and continues into a long common loop); any other
handler is **called** with: x0 the node, x1 the pass array, x2 the pass byte, x3 the pass list's address (frame + 392),
x4 the culling context, x5 the node's pass mask (N+8 and the context's +15148), x7 the worker index, and a stack argument
(the frame's +384, a record of four bytes the body filled: bits of the mask and of the record's +44, and the pass array's
byte at +2). Its return value is stored at N+12. Then the **tail**, which all kinds share:

| Step | What it does |
|---|---|
| T1 | N+12 = the handler's return. If M+36 bit 5 (the record's +36, "M" being the record at N+56): a path of its own through the context's +12528 object (a sub-system's list; 39% of plain-59 nodes in castle-move) |
| T2 | if the u16 at M+42 is not 0: a long path through the object at N+128 and the context's pass objects (virtual calls, a floor / water test; rare: 27 of 22,609 plain-59 nodes in castle-move) |
| T3 | if N+12 is not 0: **the pass list is walked** (below); else |
| T4 | the exit: N+18 loses bit 7 and the function returns |

**The pass list's walk** (T3, the part that holds the box tests). Each pass-list record names a *pass object* P (its first
word) and carries a key (a u64 at +16 and a u32 at +24) and flags (bytes +25 to +27). For each, the body looks at **a 120-byte
cache entry** of the node's record: entry number = the u16 at P+0, at `*(M+0) + 120 * number`. The entry holds six run lists
(each a pointer at +8, +24, +40, +56, +72, +88 and a u16 count 8 bytes later: +16, +32, ... +96), the key it was built for
(+104 u64, +112 u32) and a flag byte (+116, bit 0 = stale). **Cache hit** (flag clear, record byte +27 & 0x18 clear, key
equal): for each of the six lists with a non-zero count, the body claims that many slots at the end of P's matching list
with **an atomic fetch-add** on P's counter (the counters at P+516, +772, +1028, +1284, +1540, +1796; the pointer
arrays at P+504, +760, ...) and copies the run pointers into the claimed slots. **Cache miss**: the six counts are zeroed,
the entry is rebuilt by the sub-mesh loop of section 9 (the box and distance tests, then the occlusion test, then the
6-byte runs or the on-the-spot draws), the key is stored, the stale bit cleared, and the same merge as a hit follows. So
**the order of entries in P's lists is not deterministic** (workers claim slots in the order they arrive: a whole-node
check can compare the entries as a set, not in order), and the visible runs are cached across frames: the box tests of a
frame (95% from the two loop sites) are the cache misses.

**Why plain kind 59 cannot be answered whole this session.** The check below says that **every plain-59 node's handler
returns non-zero** (the tail bucket "M+36 bit 5 clear, M+42 zero, N+12 zero" holds 0 nodes of 22,609 in castle-move): all of
them go into T3, whose miss path is the sub-mesh loop with the occlusion test (a projection of 400 lines and a tile loop
with many exits), the 6-byte run buffer and the draw recording. The decision to take T3 is known only *after* the handler ran,
so the gate cannot decline then (the handler's writes have been made); the answer would need the whole of T3, with its
cache-hit merge and atomics, and T1's path for the 39% of nodes with M+36 bit 5. The inlined kinds 19 and 27 are no easier
(their inlined code calls virtual methods, then enters a long loop that ends in the same tail). **Nothing is answered**:
the gate stays at "every node declined" and the translated body runs from its entry.

**The whole-node check** (`HL_VIS=1 HL_VIS_CHECK=1`). The gate runs the translated body for real on every node (the game
gets the translated results only), after the native side (`hl::vis::prologue`, `hl/vis/Node.h`) has said what the
body's prologue writes, computed from the node's state first. It then compares each predicted write with the memory after the
body, and snapshots 384 bytes from N and 256 from M before and after to count, by class (the plain handler index, or
"prelude"), which bytes the translated body changes: the writes a native answer of that class has to make
(`hl vis: body check:` lines). `HL_VIS_SELFTEST=1` flips one predicted value of every node: the check must count every node as
wrong, and does (545,766 injected, all counted: the check itself works).

What it found (main PC, slot c, build `v1f-check`, `HL_VIS=1 HL_VIS_CHECK=1 HL_VIS_LOG=1`; every figure names the slot, whose saves
differ from slot a's; the box check ran alongside; the last periodic report of each run):

| Scene | nodes (plain) | plain 59 | prologue fields: mismatches | prediction wrong / compared, plain nodes: N+22, M+24, N+20 | plain-59 tails 001 / 101 / 111 / 000 |
|---|---:|---:|---:|---|---|
| castle-move | 479,096 (312,837) | 20,518 | 0 of 479,108 | 0 / 312,846; 70,612 / 312,846; 16,833 / 312,846 | 12,584 / 7,908 / 26 / 0 |
| kokiri-idle | 505,750 (311,082) | 20,640 | 0 of 505,752 | 0 / 311,084; 76,283 / 311,084; 15,339 / 311,084 | 12,660 / 7,955 / 25 / 0 |
| hyrule-walk | 222,645 (145,440), a report taken at 37 fps | 9,016 | 0 of 222,646 | 0 / 145,442; 30,492 / 145,442; 8,871 / 145,442 | 5,503 / 3,488 / 25 / 0 |

(tail digits: M+36 bit 5, M+42 non-zero, N+12 non-zero after the body; "000" is the trivial tail.) The box check beside it
counted 0 mismatches. The self-test run (castle-move, 545,766 nodes, every one with one wrong value injected) counted 545,766
injected wrong values among its mismatches: the check sees what it should.

- the prologue's three writes are **not final** for many nodes: N+22 (bit 0 cleared) is never changed afterwards (0 wrong in
  every plain-node prediction of the three scenes), but the record's +24 (zeroed by the prologue) is written again by the
  handler or the tail in 20-23% of plain nodes, and N+20 (the cycling counter) is rewritten in 5-6% (its high bits; the
  nodes with a prelude 5% and 5%). So the prologue alone cannot be compared with the final state as a whole-node check:
  the answer for a class must predict the final values, handler included. That is why only N+22 is a meaningful
  partial prediction, and why the check's other two lines are information (what a later native answer must write), not
  defects.
- bytes of the node a translated body changes: always N+22, N+24 and N+20 (every plain node; N+24 is the render-list flag the
  tail sets), sometimes N+12, N+18 (19 and prelude nodes), N+21, N+25; for nodes with a prelude also N+104..119 (a record
  the prelude writes) and N+368..377. The record: +24, +33, +72, +104, +136, +152, +160..255 in a few percent of nodes
  (the cache bookkeeping of the pass list and the handler's results).
**Loading stalls in slot c, not tied to this work.** In slot c some castle-move and kokiri-idle runs stayed on the loading
screen to the end (a black picture with the spinner, 97-128 fps, a few thousand body calls at most). They happened with
`HL_VIS=1 HL_VIS_CHECK=1` (4 of 9 runs), with `HL_VIS=1` and no check (1 of 1) and with **no `HL_VIS` at all** (`HL_VIS_LOG=1`
only: 1 of 2), so the check is not their cause; the runs that loaded gave the figures above. A run that has stalled shows
at most a few thousand body calls: read a run's node count before trusting its figures.

**What the check does not yet do, and what a native answer needs next.** The check compares the writes the native side predicts
at their addresses and lists the node and record bytes the translated body changes; it cannot yet compare what the
body writes through other pointers (the pass objects' lists and counters, the cache entries, the 6-byte runs, the draws).
When a class is answered, those writes are compared as sets (the lists' order depends on the workers' timing, above).
The order for the next sessions: (1) the cache-hit merge of T3 and the pass list's empty exit (the nodes whose pass list is
empty after the handler: the kinds 19, 27, 3, 51 with N+12 and the tail's other conditions read, after reading what the
inlined handlers and the handler `0x83650800` do); (2) the miss path with the sub-mesh loop and the occlusion test, for the
plain-59 nodes; (3) T1's path (M+36 bit 5).

**Hand-over 4** (end of the fourth session): committed on `stream/v1-visibility`: the whole-node check and its counters
(this section), `hl::vis::prologue` and `handler_index` natively with game-free tests, the C surface
`hl_vis_node_prologue`. No node is answered; `HL_VIS` stays 0 by default and with it on every node is declined (the check,
with `HL_VIS_CHECK=1`, runs the translated body itself and returns its results). The crossings and the body's time a frame are
unchanged from before by construction (the gate crosses once a node and runs the translated body as before: about 380 body
calls a frame in slot a's castle-move, section 9). Next: read what the inlined handlers of kinds 19 and 27 and the handler
of kind 3 do after their virtual calls (they end in the shared tail), write the tail's cache-hit merge and the empty-list
exit, and answer a node class only when its handler is native or a pure call back whose result the tail can read before
it declines (a node cannot be declined after its handler ran: its writes have been made). The loading stalls of slot c
are an environment fact (above).

## 13. Fifth session (VIS1, 21 Nov 2026): the stream rebased on main, the box test measured

The seven commits of `stream/v1-visibility` were cherry-picked onto main `150a02c9` (branch `perf/vis1`; only the two README
tables conflicted). The build (`vis1-a`) links and starts; with `HL_VIS_BOX=1 HL_VIS_CHECK=1` on market-spin (main PC, slot b)
the box check counted 9,223,569 compared calls, **0 mismatches**; 99% of the calls come from the sub-mesh loop's two sites
(about 2,250 crossings a frame). No node is answered yet (section 12 stands: plain kind 59 always reaches the tail's pass
list walk, whose miss path is the sub-mesh loop with the occlusion test and the draw recording; none of it is native).

Speed, main PC (RTX 5070), explicit options (dlss 0, upscaling 0, resolution 1, hdr 0, vsync 0, no cap), `HL_VIS_BOX` 0 / 1,
fps of one run each: market-spin (save market-mid, slot b) 80.2, 80.9, 82.4 / 77.9, 82.7, 85.1; hyrule-walk (slot a)
100.9, 94.5 / 93.5, 96.1. No gain beyond noise (run to run spread 3-7%): the native box test replaces a short translated
function by a native call of about the same cost. `HL_VIS_BOX` stays 0. Answering whole nodes needs the miss path native
first (occlusion projection, run buffer, draw recording) with a site hook at `0x800a0940`; that is the next unit of work.
The PC 3050 could not be measured: it has no lifted work folder (no build there; the exe was copied from the main PC) and
its headless runs present no frames the harness counts (7 frames in 111 s).

## 14. Is the job on the frame's critical path? (VIS3, 22 Nov 2026) Gate verdict: no, stop

Step 3 of `refactor-plan.md` assumed the ~4.4 ms of CPU is worth making native. It is only worth it if it gates the next
present. Measured on `refactor/integ1` (`8cc3b72a8`, `HL_RB_LAG=2`, `HL_GFX_VAR=1` on) on the main PC (RTX 5070, Ryzen 7 7800X3D),
Market `market-spin` from `build/s5/savelib/market-mid`, speed lease, explicit options (dlss 0, upscaling 0, resolution 1,
hdr 0, vsync 0, no cap). The branch has no lifter change and no new code for this: the tools are the existing ones,
`HOS_JOBTRACE` (window 80-86 s) with `tools/bench/critpath.py` (the path walked back from each present, over the
hand-offs) and `chainb.py`, and `HOS_SAMPLE_ALL` + `HOS_SAMPLE_NS` (70-106 s) to put the sampler's stacks on the path's work.
WPR needs an administrator, which the main PC session is not, and `HL_THREAD_CPU` / `RX_VK_FEED_LOG` are not in this branch
(they live on `diag/replay1` and `refactor/order3`); the job trace gives the same answer with the hand-offs included.

**The frame** (5 runs without the sampler: fps 89.8, 89.4, 88.7, 91.3, 91.0; a sixth at 84.8 is left out as an outlier):
10.3-10.6 ms, mean 10.4 ms. One serial loop:

| Step (mean of 3 runs) | ms |
|---|---:|
| the main thread (`sead::MainThread`), present end to its last held submit | 1.69 |
| held flush: last hold to the Presentation Thread's first submit | 0.78 |
| the Presentation Thread (PT): its submits, the replay itself (run 1: dry pass 1.25, own segment recorded 2.56, mirrors 0.42, segment wait 0.41) | 6.95 |
| PT: last submit end to present end | 1.02 |

**The critical path, ms a frame by thread** (`critpath.py`, 3 runs A, 515-530 frames each, the five runs agree within 0.2 ms):

| Thread | ms | Share |
|---|---:|---:|
| PT, the Presentation Thread (replay inline, then the present) | 8.31 | 80% |
| main thread | 0.52 | 5% |
| module workers MW1 / MW3 / MW4 / MW5 / MW2 | 0.33 / 0.24 / 0.24 / 0.20 / 0.05 (1.06) | 10% |
| waits for a virtual core, no hand-off | 0.19 | 2% |
| executors EX0-EX5, hand-offs, polls | ~0.2 | 2% |

**Who hands work to the replay, and what it waits for.** The main thread: its held submits go to the PT through a queue
(`lr 834a3084`, once a frame, 9 us). The replay runs in the PT, so the replay starts only after the main thread's last hold
and the flush: 1.69 + 0.78 = 2.5 ms of each frame is the game side (the main thread, its job-group wait for the module
workers and executors, the module jobs), 7.9 ms the PT. The path through that 2.5 ms is main 0.52 + module workers 1.06 +
core waits 0.19 + hand-offs. The replay is not waiting on the visibility job in particular: the same 2.5 ms holds the game's
whole chain.

**The visibility job's share of the path** (two sampled runs, 487-492 frames, 1,245-1,279 path samples each, a sample is
one 4.5 ms round of a thread; the sampler stretches the frame to 12.2 ms, so read shares):

| What | Run 1 | Run 2 |
|---|---:|---:|
| path samples under the root `0x800998a0` (any visibility function in the 16 frames) | 21 (1.6%) | 11 (0.9%) |
| the same, ms a frame, thread by thread (its thread's path ms x its share) | 0.17 | 0.09 |
| the recording jobs `0x8006cd60` + `0x80084de0`, for comparison | 142 (11.1%) | 140 (11.2%) |
| the job's CPU while running (leaf in game code, not in a wait), all threads | 3.95 ms | 3.63 ms |
| the job's CPU with the waits inside it (YieldThread, SleepThread) | 9.7 ms | 9.6 ms |

- The ~4.4 ms of CPU is real (3.6-4.0 ms running plus ~0.4 ms in stacks whose root was cut), spread over the 5 module workers and the
  main thread. Only **0.1-0.2 ms of it is on the critical path**: it runs in parallel and ends before the main thread's last
  hold gates anything. Whatever the job's cost, making it free would shorten the frame by at most that, 1-2%.
- Under the module runner `0x80083960` the path's game-thread samples are `0x8006cd60` 121 (47%), `0x800998a0` 21 (8%),
  `0x80084de0` 19 (7%) in run 1 (one frame of the module runner: the recording job `0x8006cd60` is about 1 ms of the 2 ms
  the game threads have on the path, five times the visibility job). 90% of the game threads' path samples are cut at 16
  frames, but a visibility frame is only missed when the root is cut off; the counts of the root and of the body or the box test
  (listed alone) agree, so it is not hiding.
- The 3050's WPR trace (`E:\OOT\scratch-trace1`, 21 Nov, 24.3 ms frames, before the readback ring) gives the same answer
  by a different method: with the path's run intervals from `cp.py` and the sampled stacks, **0.37 ms of the 24.3 ms** is under
  `f_800998a0` (body 0.13 ms), 1.5%; the presenting thread waits 10.5 ms a frame for the order thread, which is the gate there.

**Gate: the job plus its loop is 0.1-0.4 ms on the critical path, under 1 ms on both machines. Step 3 as written is not
built.** What gates the next present is the PT's replay (80% on the 5070, 37% order thread plus 17% presenting thread on the
3050), not the game side. The visibility CPU still costs cores (about 4 ms a frame of 70), which the 3050's SMT sharing could turn
into path time (404 ran with a busy sibling 42% of the time); that second-order cost is not measured and is not a reason by itself.
What the path does contain on the game side is the recording job `0x8006cd60` (about 1 ms) and the main thread's own 0.5 ms.

Runs: `E:\OOT\scratch-vis3` (`A-n` / `B-n` job trace only, `S-n` job trace + sampler; `vis3an.py` the join), main PC, 22 Nov.

## Not established

- What the body writes as render lists, their layout and readers; whether gameplay reads anything this job writes.
- The kind handlers behind the body's dispatch table; the paths for N+18 bit 0 and for threads whose TLS slot is 0.
- Phases D, E and G of the root beyond the calls listed; `0x80083960` as a caller.
- What `0x808226e0` computes (matrices and volumes is an inference); who writes the culling volumes.
- What the sub-mesh loop's runs produce and what the branch at `0x800a1120` decides.
- The per-frame counts of views, pass items and nodes; the split of the 0.47 ms between YieldThread and SleepThread.

## Method

The lifted functions were read with the query scripts of the handbook (index of the lifted code, copied to
`E:\OOT\scratch-from-c\v1`), and `showfull.py` there (a function's lifted text unabridged). The sampled times are the
per-sample records of `build/hotfn/r1..r3.recs.json` re-aggregated by `tree.py` there (the chain below a root, inclusive
per path and per function, own time by leaf kind, ms from each run's samples-to-ms factor, mean of three runs).
