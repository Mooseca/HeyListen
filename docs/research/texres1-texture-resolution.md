# TEXRES1: texture resolution keyed by the storage a handle names (23 Nov 2026)

Branch `perf/texres1` from `refactor/integ4` (7f9a8e8bf). Main PC, RTX 5070 / Ryzen 7 7800X3D. Switch `RX_VK_TEXRES` (default **off**), check mode
`RX_VK_TEXRES_CHECK=1`. Code: `engine/gpu/vk/texres.h` (new), `vk_draw.cpp`, `vk_replay.cpp`, tests `tests/test_texres.py` + `tests/texres_test.cpp`.
Numbers are in sections 4 and 6; the verdict is in section 7.

## 1. The idea and what MEMO1 left open

MEMO1 (version 4) showed that the texture handle words and registration serials change every frame while the storage they name does not: keyed by
storage, 79% (castle-move) and 69% (Market) of `draw()` time repeats within 60 frames, half of it two frames back (double-buffered targets).
BIND1 had put the texture category at 3.66 ms summed (Market), 1.56 ms of it slot misses, plus ~1.1 ms of ParLock waits from `texture_touch`.
The task: a handle that names storage already resolved should cost a lookup, not a resolution.

## 2. How a handle was resolved (before)

`build_descriptors` (vk_draw.cpp) keeps, per program and texture slot, 4 `TexSlot`s chosen by the handle's hash. A hit needs the same handle word, the
same slot version (`texture_slot_version`, bumped by every registration) and the same sampler version and destroy generation: and then costs a touch
once per texture epoch. A miss goes to `texture_view_of`: `handle_hits` (a per-thread map by slot id and version); on its miss, under the ParLock:
`texture_of` (copy of the registration under `reg_mu`), `texture_get` (the Key from the description, the textures map, `texture_touch`), `texture_view`
(a key and `tex->views`), `image_level`. Then `sampler_for` (a per-thread table by sampler id).

The slot's registration is re-written every frame for the same storage (new handle, new serial, new pool/offset): the version moves, `handle_hits`
and the slots miss and the full path runs.

## 3. Design

**Fingerprint (texres.h).** A 64-bit hash of what decides the resolution: the storage's GPU address, the whole `nvn_texdesc` (target, format, flags,
samples, size, levels, stride, swizzle), the derived layout (`L`), the packaged layout bytes, and the view (16 bytes or "no view"). Left out: the
object's magic, pool pointer, offset and initialization **serial** (what changes every frame). Never 0. A resolution is a pure function of this
content and of the texture set (the destroy generation), which is what `handle_hits` already relies on.

**Registry mirror without touching `vk_bank.cpp`** (a shader-stamp file: a change would make every player re-prepare shaders). The registering
thread writes `slot_fp[id]` (8 MB of zero pages, 1<<20 slots): `registering(id)` stores 0 *before* the registry changes, `registered(id,...)` stores
the fingerprint *after* (vk_replay.cpp: `JOB_REGISTER_TEXTURE` and `register_texture_locked`). A recorder reads it with an acquire load, no mutex.
0 means not registered or being registered: the reader takes the old path and keeps nothing. A reader that read fingerprint F, resolved, and finds
the slot still at F and the destroy generation unchanged may keep the answer under F; because of the 0-before order a registration that began
after its first read is seen at its second.

**Three layers, all per thread, none taking a lock on a hit:**
1. `texres_view` (the storage table): `Cache<VkImageView, Texture>` keyed by (fingerprint, view type): an entry is good while the destroy generation
   is the one it was resolved under (the TICK-052 gone-ring rescue as `texture_view_of`); a hit does the once-per-epoch `texture_touch_quick` (full
   touch under ParLock only if that fails), as the handle hit does. A miss resolves the old way and keeps only a complete answer (view and texture,
   not held back by the upload budget).
2. The program's `TexSlot`s keyed by fingerprint instead of handle + slot version (`RX_VK_TEXRES_SLOT=0` leaves them by handle): the sampler stays
   the handle's own id (checked by its version as before). The way is chosen by the fingerprint. An answer of nothing is never kept by storage.
3. `desc_fp_note` / `desc_slots_kept` (the descriptor reuse, RX_VK_DESC_SLOTGEN): by the slot's fingerprint (44 bits) instead of its version, so a
   registration of the same storage under a new serial no longer defeats reuse of a draw's descriptors.
4. `targets()` (the NOP_SET_RT resolution under the ParLock, held 0.21 ms a command buffer in BIND1): `RX_VK_TEXRES_TARGETS` (on with the switch) keys
   it by the fingerprints of the targets' texture objects and views; a hit touches the textures (age) and takes no lock.

**Invalidation.** Storage re-registered with another description: the fingerprint differs. Image destroyed or recreated (including the no-attach
upgrade, evictions, remakes): `destroy_later` bumps the destroy generation, every entry made earlier misses. Pool memory moved: the fingerprint holds the
GPU address and description, not the pool; the `Texture` is looked up by that address as before, and what moves a texture's *contents* is the upload
tracking inside `texture_touch`, run once per epoch. Sampler retirement: untouched, the slot still checks `samp_retired`, `samp_frame` and the
sampler's version. `RX_VK_TEXRES` off: the registrations skip the fingerprint, nothing else changes.

**Check mode** (`RX_VK_TEXRES_CHECK=1`, implies on): every storage hit, slot hit and targets hit is also resolved the old way and the two compared
(views and textures); the old answer is the one used. A comparison is dropped when the slot was registered or a texture destroyed meanwhile. The
mismatches are counted, the first twelve logged, a line every 10 s. `RX_VK_TEXRES_STATS=1` adds hit counters.

## 4. Why it can not be +30%: what the profile says

Profiles are separate runs from the fps runs (`RX_VK_PROF_FINE=1`, `RX_VK_PARLOCK_STATS=1`; they cost ~2% fps), windows with more than 1,800 draws a frame
(castle: 1,000), sums over the recording threads, ms a frame, A = switch off, B = `RX_VK_TEXRES=1` (everything on). Parser `E:\OOT\scratch-bind1\avg.py`.

| | market A | market B | market A (2nd) | market B (2nd) | castle A | castle B |
|---|---:|---:|---:|---:|---:|---:|
| build | texres3 | texres3 | texres3 | texres3 | texres2 | texres2 |
| draws a frame | 2,358 | 2,362 | 2,363 | 2,356 | 1,660 | 1,652 |
| textures, summed ms | 3.92 | 3.70 | 3.99 | 3.79 | 1.81 | 1.98 |
| of it slot misses | 1.64 | 1.39 | 1.64 | 1.50 | 0.31 | 0.37 |
| draw() whole, summed ms | 14.45 | 13.70 | 13.71 | 13.48 | 10.14 | 10.52 |
| slots resolved again a draw | 1.05 | 0.81 | 1.04 | 0.78 | 0.71 | 0.64 |
| replay thread: dry pass, ms | 2.73 | 2.52 | 2.27 | 2.22 | 0.91 | 0.94 |
| replay thread: its own segment, ms | 3.95 | 3.78 | 3.77 | 3.78 | 2.87 | 3.04 |
| replay thread: submissions, ms | 8.32 | 7.87 | 7.46 | 7.39 | 6.56 | 6.87 |

(The first Market pair is the PROF_FINE-only pair, the second the PARLOCK_STATS pair; the Market columns' "dry pass" and "own segment" rows are the replay-wall line's dry pass and segments' recording-and-wait, the castle
column's the early-steps line's dry loop and own segment (two definitions of nearly the same thing). The castle pair is texres2: its slots still read both the version and the
fingerprint, which texres3 fixed. The castle PARLOCK pair (t4c-plA/B) hit different phases of the scene, 2,067 against 1,615 draws a frame, and is not
comparable; it is kept in the logs only.)

- **Hit rate is high, the saving is small.** In check mode (Market) 94% of the slot misses are answered from the storage table (440,241 storage misses
  against 7,761,866 slot misses; 44.0 M slot hits), 99% in the castle (28,025 of 4.0 M). Slots resolved again a draw fall from 1.05 to 0.81 (they were
  by handle, now by storage; what remains are storages new to the program's 4 ways: a program that draws 100+ different textures thrashes 4 ways, and the
  storage table answers those).
- **Texture ms drops by 0.2-0.25 ms of 3.9 in the Market, draw() by 0.2-0.75 ms summed** (castle: nothing, within the windows' spread). Over the
  parallelism of ~4.4 that is **0.05-0.17 ms of the critical path, 0.5-1.5% of the 10.6 ms frame**. The fps A/B agrees (section 6).
- **Why the slot-miss ms does not vanish.** A slot miss still costs ~0.7 us (1.39 ms / 1,900 misses) *with* the storage hit. The rest is not
  resolution: the *first touch of every texture in a submission* (`texture_touch`: the dirty-page check against guest memory, uploads, age) runs under
  the ParLock. PARLOCK_STATS (Market, per command buffer): "touch by slot" 198 takes (203 with B), "touch by view" 182 (172), "touch: not checked this
  submission" 379 (375). These are inherent to a texture's first use in a submission, whichever handle names it; the table cannot skip them, and neither
  can the descriptor reuse. The waiting at those sites: slot touch 0.113 ms (B 0.171), view touch 0.094 (B 0.060): moved, not removed.
- **Dry pass and the replay thread's own segment**: unchanged within the spread (Market dry pass 2.73 -> 2.52 and 2.27 -> 2.22, own segment 3.95 -> 3.78
  and 3.77 -> 3.78). The dry pass does not resolve sampled textures at all (it marks written targets, `dry_mark_written`, and storage images of compute
  dispatches); the one storage-keyed part there, `targets()` under the ParLock per NOP_SET_RT (clear ds 0.64 -> 0.60 ms), now answers from a
  fingerprint table and gained ~0.04 ms: its cost is mostly `texture_written`'s ParLock take, not the resolution.
- **Where the critical path is** (Market, same profile): the replay thread's 7.4 ms = its own segment ~3.0 + dry pass 1.8-2.3 + waits 0.65 + 17 small
  recordings 0.64 + memory work 0.5; the heaviest draws (10 us and more: 245-262 draws, 3.4-3.7 ms of 13.5) are costly in banks (c0/c2 refills), program
  lookup (1.3-1.8 ms) and the UBO/storage binds, not in textures. Textures are 28% of draw(); the part the storage key attacks, the miss path, 11%.
- **Descriptor reuse by fingerprint** (layer 3) needs `desc_slotgen_on()`; it only matters where a draw's handles are unchanged but a registration of the
  same storage came (rare: a changed handle word moves `bind_gen` first). No measurable effect; kept because it is the same rule.

## 5. Dead ends and things not done

- A texture handle is a *word* in the banks, read every draw: nothing in this design skips reading it. The descriptor words are built from the views and
  samplers, which the slot hit already gives at ~0.1 us a texture; building them from a per-draw key (whole-draw reuse) is MEMO1's section 6, and its
  coverage and 12-day estimate stand.
- The registrations' mutex (`reg_mu`, `texture_of`) is off the hit path, but it was never the dear part (view creation and the touch under the ParLock were).
- `vk_bank.cpp` could hold the fingerprint more simply (inside `register_texture_copy`, under `reg_mu`, beside the version); not touched: it is in the
  shader stamp. The mirror lives in `texres.h` and is written from vk_replay.cpp. Two simultaneous writers of one slot (the replay thread and the game
  thread's register-at-once path) are not ordered by the 0-then-value rule.
- A lock-free `texture_touch` (the 200+ ParLock takes a command buffer above) is the remaining texture lever, perhaps 0.1-0.3 ms of critical path (BIND1's
  estimate); not attempted: it touches the upload tracking (`texture_dirty`, `upload`).
- Mid-way: the first build's version-and-fingerprint reads doubled the slot hit's table traffic (castle textures 1.81 -> 1.98 ms in texres2); texres3
  reads only the fingerprint when a slot is keyed by storage.
- Not measured: the PC 3050 (GPU-bound; the coordinator declined the run), AMD / Intel, other zones, zone changes, a long play session. The 0-before-value
  order and the destroy generation are covered by the unit test (random registrations, destructions and resolutions, 0 mismatches) and by check mode in
  the game for two scenes.

## 6. Numbers

**fps** (3 interleaved rounds A B A B A B, one speed lease, priority 2, fps from "play: began" + 10 s, `HOS_PERF_REPORT=1`; texres2 for castle, texres3 for
the others; arm A is the same binary with the switch off):

| scene | A (off) runs | B (RX_VK_TEXRES=1) runs | A mean | B mean | B/A |
|---|---|---|---:|---:|---:|
| castle-move | 121.5 124.2 125.5 | 124.4 123.7 124.5 | 123.7 | 124.2 | +0.4% |
| market-spin | 82.1 85.2 87.0 | 86.4 87.1 85.0 | 84.8 | 86.2 | +1.6% |
| kokiri-idle | 118.3 119.6 119.0 | 118.5 118.9 119.7 | 119.0 | 119.1 | +0.1% |

The spread inside one arm is 4-5 fps in the Market (a1, 82.1, had 21 frames over 50 ms): all three are inside noise. The Market +1.6% is about what the
profile predicts (0.5-1.5%), but is not distinguishable from it.

**Check mode** (`RX_VK_TEXRES_CHECK=1`, every slot, storage and targets hit resolved the old way and compared): castle-move 49.7 M comparisons, **0
mismatches**; market-spin 52.2 M comparisons, **0 mismatches** (a 110 s run each; kokiri-idle not run).

**Pictures** (`RX_VK_SHOTS`, castle-move and market-spin, A and B, `E:\OOT\scratch-texres1\shots\{castle,market}-{A,B}`): the arms differ by the scenes'
own motion (a frame number is not the same picture in two runs), so no pixel comparison; the B pictures were looked at: Market frame 12000 shows correct
textures everywhere (the circus tent, cobbles, characters), none missing, flickering or placeholder.

## 7. Verdict

- **Gain: +0.4% (castle), +1.6% (Market), +0.1% (Kokiri) fps, all inside noise; texture time -0.2 ms of 3.9 (Market), 0 (castle).** This lever cannot
  give +30%. The slot-miss path it attacks is 11% of `draw()`, and a storage hit still costs ~0.7 us because the dear part of the texture category, the
  first touch of each texture in a submission under the ParLock, does not depend on the handle.
- Correctness: 0 mismatches in ~100 M comparisons over two scenes; the unit test with a moving registry.
- **Proposed default: off.** It is leaner in theory (no reg_mu, fewer ParLock takes on the resolution path) and costs 8 MB of zero pages; the measured fps
  gain cannot be told from zero. To adopt it under the "within noise and leaner" rule, run the check mode on more scenes and zones (and AMD) first.
- Next levers from this data: the touch (200 ParLock takes and 379 first-touch checks a command buffer), the banks' refills (castle 1.7-2.9 ms) and the
  program lookup (1.3-1.8 ms); none is a +30% alone.
