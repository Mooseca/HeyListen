# BIND1: where the replay's CPU goes, and what a bindless texture path would save (22 Nov 2026)

Branch `perf/bind1` from `refactor/integ4` (582aba6a6). Main PC, RTX 5070 / Ryzen 7 7800X3D, speed leases (priority 2), `market-spin` from
`market-mid` and `castle-move` from `hyrule-castle`, `HL_*` defaults of the build, fps counted by the harness from "play: began" + 10 s.
Build: the existing `build/s5/bin/integ4` (built 16:24, after the branch tip's commit at 16:12: same source, nothing of mine in it). No code
was changed on this branch: the repository's own timers (`RX_VK_PROF_FINE`, `RX_VK_PARLOCK_STATS`, `RX_VK_NO_DRY_MARKS`) cover every category
asked for, so no counters were added and no build was needed.

**Verdict: no pilot.** A bindless texture path can take at most ~1.0 ms of the market frame (10.6 ms) even if every texture and every image
push cost vanished, and an honest estimate is **0.2-0.3 ms (2-3% fps)**, against the 1.5 ms bar. The design is written down below in case
the bar moves; the numbers that decide it are in the first four sections.

## 1. Method

`RX_VK_PROF_FINE=1` (logging only, every 120 presents): `a frame (fine)` sums the sections of `draw()` over every recording thread (each
section a pair of QPC reads, ~15 ns each); `replay thread, wall`, `replay_handle_early's steps`, the per-op tables of the dry pass and of the
segment workers, and the driver-call counters give the replay thread's own wall time. Windows with fewer than 2,000 draws a frame (loading,
menus) are left out (`E:\OOT\scratch-bind1\avg.py`). `RX_VK_PARALLEL=0` (serial replay) gives the same sections with no other thread, which
is the pure per-draw CPU cost. `RX_VK_PARLOCK_STATS=1` adds the lock waits by place.

| run | scene | fps | p50 | p99 |
|---|---|---:|---:|---:|
| plain | market-spin | 87.4 | 10.6 ms | 24.6 ms |
| PROF_FINE (2 runs) | market-spin | 85.6 / 85.2 | 10.9 | 23.9 / 24.4 |
| PROF_FINE + PARLOCK_STATS | market-spin | 86.9 | 10.8 | 21.8 |
| PROF_FINE + NO_DRY_MARKS | market-spin | 86.5 | 10.8 | 22.4 |
| PROF_FINE, serial (`RX_VK_PARALLEL=0`) | market-spin | 65.9 | 14.1 | 31.9 |
| plain | castle-move | 113.2 | 8.6 | 12.7 |
| PROF_FINE | castle-move | 112.0 | 8.7 | 12.6 |

(Market-mid is the hardest scene: 2,360 draws a frame; the "125-130 fps in play" of the brief is the same structure on lighter frames.
The profile costs ~2% fps. One run each: these are breakdowns, not an A/B.)

## 2. The breakdown (market-mid, 45 steady windows, 2,360 draws a frame)

### 2a. What the replay thread's 7.7 ms is (wall, the thread that holds the replay lock)

| step | ms a frame | note |
|---|---:|---|
| submissions, all | 7.68 | 13 a frame; the three big command buffers 6.05 (2.76 big a frame) |
| dry pass (serial, before the first segment can go) | 2.35 | of its ops (1.91 ms): clear-ds marks 0.65 (42 a frame, 15 us each), draw idx 0.24, report counters 0.23, bind ubo 0.12, bind tex 0.12, dispatch 0.11 |
| the replay thread's own (last) segment | 2.89 | |
| waits for the workers' segments + submits | 0.60 | |
| 17 small command buffers recorded whole on this thread | 0.94 | |
| memory work before submissions | 0.46 | |
| segment setup (begun / init / before submitted) | 0.26 | |

The game's own draw code (1.7 ms) runs before this on the submitting thread, so the chain is ~9.4 ms of the 10.6 ms frame.

### 2b. What the 2,360 `draw()` calls are (summed over the five recording threads; 13.7 ms a frame = 5.8 us a draw, parallel)

| category | parallel ms (us/draw) | serial ms (us/draw) |
|---|---:|---:|
| handle resolution + texture lookup ("textures") | **3.66 (1.55)** | 1.36 (0.57) |
| of it slot misses: view and sampler lookups, ParLock | 1.56 (0.66) | 0.55 |
| descriptor writes and push ("bind descriptors") | 0.95 (0.40) | 0.69 |
| of it the `vkCmdPushDescriptorSetKHR` call | 0.62 (0.26) | 0.45 |
| user uniform buffers | 1.11 (0.47) | 0.84 |
| driver banks c0/c2 + c1 | 0.44 (0.19) | 0.18 |
| storage buffers | 0.70 (0.30) | 0.54 |
| program lookup (vk_shader.cpp pick, shader-stamp file) | 1.81 (0.77) | 0.83 |
| pipeline lookup | 0.41 (0.17) | 0.23 |
| bind pipeline | 0.72 (0.31) | 0.52 |
| vertex + index buffer binds | 0.90 (0.38) | 0.54 |
| push constants (checkpoint marker 0.29) | 0.37 (0.16) | 0.26 |
| dynamic state | 0.29 | 0.25 |
| hazards + pass | 0.34 | 0.25 |
| the `vkCmdDrawIndexed` call | 0.20 (0.09) | 0.10 |
| between the descriptor build and the pipeline bind, pre-lookup, checks | ~1.1 | ~0.7 |
| **draw() whole** | **13.72 (5.8)** | **7.62 (3.2)** |

Notes:
- Per draw: 5.2 texture slots (4.2 kept, 1.0 resolved again, 0.87 of those "another handle in the slot"), 5.8 descriptors pushed a draw,
  0.86 descriptor builds, 0.36 pipeline binds, 0.34 push-constant calls.
- Driver time is small: queue submits 12.7 a frame = 0.36 ms, slot waits 0.06 ms (all threads), `vkCmdPushDescriptorSetKHR` 0.62, which agrees
  with VKC1's census (3.2 ms of ~12 in `vkCmd*`, 0.57 of it pushes).
- **The parallel replay makes a draw 1.8x dearer than the serial one** (5.8 against 3.2 us), and the texture section 2.7x (1.55 against 0.57 us).
  Parallel is still 3.5 ms faster per frame (the wall: 7.7 against 12.6 ms), but the recorders spend ~7 ms of their 16 ms on contention and
  cold caches. The five recorders' op sum is 16.0 ms against a segment wall of 3.6 ms: the effective parallelism is ~4.4.
- ParLock (`RX_VK_PARLOCK_STATS`, per big command buffer, summed over threads): waiting 0.65 ms, holding 0.59 ms (x2.76 big a frame:
  1.8 ms waiting, 1.6 ms held). By place: the texture "touch" under ParLock at vk_draw.cpp:3960 (the slot hit path, once per texture per
  texture epoch when `texture_touch_quick` fails, 194 takes, 28 waited) 0.25 ms, and the same at :2943 (`texture_view_of`'s hit) 0.17 ms: **0.41 ms
  per command buffer, 1.1 ms a frame of the 3.66 ms of "textures" is waiting for ParLock**; `targets()` (:4757) holds it 0.21 ms (92 takes);
  the program pick (:8124) waits 0.08.

### 2c. Castle-move (33 steady windows, 1,850 draws a frame; frame 8.6 ms)

Replay thread: submissions 7.28 (own segment 2.98, dry loop 0.68, "what came before submitted" 0.68, whole-here 1.36 for 18 small command
buffers, waits 0.49). Summed draw(): 13.4 ms: textures 2.22, banks **2.88** (castle's heavy bank refills), vertex+index 1.86, program lookup
1.73, UBO 0.82, storage 1.18, push call 0.32. 5.2 texture slots a draw; the mesh draws (45 a frame, 3.2 ms in the workers) and `signal event` 0.5 ms
are castle-specific. Same shape: textures are 17% of draw(), push 2.4%.

### 2d. A natural experiment: `RX_VK_NO_DRY_MARKS=1`

The dry pass's marks (`dry_mark_written`: the clear-ds ops, 0.65 ms) skipped: dry pass 2.35 -> 1.41 ms (-0.94), segments 3.58 -> 4.39
(+0.81: the workers do the texture first-use work instead), textures 3.66 -> 4.29, frame the same (86.5 fps, one run). Moving work between
the dry pass and the workers is zero-sum; the per-draw cost is what has to fall.

## 3. What a bindless design saves

What bindless would remove from the table above, line by line:

| removed | summed ms a frame (market, parallel) |
|---|---:|
| the image share of the push call (images are ~55% of the 5.8 descriptors pushed a draw) | 0.3-0.4 |
| the compare of the pushed words for the image writes (`words_same_store`, part of the 0.33 outside the call) | 0.1-0.2 |
| building `out.imgs` / `VkWriteDescriptorSet` per texture element (the part of the 2.1 ms non-miss texture time that is bookkeeping, not the version checks) | 0.4-0.8 |
| **total** | **0.8-1.4** |

What stays: the handle is still read on the CPU (a bank word per draw; the slot hit logic has to answer "which array index is this handle
now?"), the touch (`texture_touch`, the ParLock waits: 1.1 ms of textures: a texture still has to be marked used, uploaded, aged), the sampler
registry, the dummy views, and the new per-draw cost of writing an index block into the push constants. A hit in a global handle->index table
is about as dear as today's per-program slot hit, so the added cost is ~0.1 ms. **Net: 0.7-1.3 ms summed**.

Converting to the critical path: the recorders share the work (op sum 16 ms, segment wall 3.6 ms, i.e. /4.4), and the dry pass (2.35 ms, not
a texture thing: it has no descriptor build) is unaffected. So **0.15-0.3 ms of the 10.6 ms frame: 1.5-3% fps.**

Upper bounds, to show how far from 1.5 ms it is:
- Delete every texture second (3.66) and every image push (0.62) outright: 4.3 ms summed / 4.4 = **1.0 ms (9%)**, and that is not reachable.
- Serial replay (no parallelism to divide by): the same deletion saves 1.36 + 0.45 = 1.8 ms of a 12.6 ms wall. Even there bindless gives 14%,
  and the shipped replay is parallel.
- Texture-section contention alone (ParLock waits at :3960/:2943, 1.1 ms summed, 0.25 ms on the critical path) is a bigger item than the
  descriptor writes and has nothing to do with bindless: a texture's touch can be made lock-free or done once per epoch elsewhere.

The brief's threshold ("at least ~1.5 ms of replay CPU on the 5070") is therefore not met by a factor of 5-10. **Step 3 (pilot) is not built.**

## 4. The other big replay costs, ranked by what they could give the critical path (market, ms of the 10.6 ms frame)

None is a single +30% (that needs ~3 ms off the chain). Roughly, from the numbers above:

1. **Parallel efficiency** (5.8 vs 3.2 us a draw): the recorders' 16 ms would be ~9 ms at the serial per-draw cost, segment wall 3.6 -> ~2:
   up to ~1.5 ms if all of it were recovered. Known parts: ParLock waits 1.8 ms/frame summed (0.4 ms critical), the texture touch under
   ParLock 1.1 ms of it; the rest is probably cache-line traffic (texture epoch/last-use stores, shared hash maps) and SMT/frequency: not measured.
2. **The dry pass, 2.35 ms serial** before the first segment can leave: 0.65 of it marks (clear-ds 15 us each: `targets()` under ParLock held
   0.21 ms/cb + `texture_written`); moving it did nothing (2d). ORDER2/JOIN1 analysed the overlap of the dry pass with the previous segments and
   left it as a design (needs jobs on the heap and the Serial-mode replay safe beside recording workers).
3. **The replay thread's own segment + waits, 3.5 ms**: more recorders and smaller tails were tried (REPLAY2/ORDER3: no change).
4. **Program lookup 1.8 ms summed (13%)**: is in `vk_shader.cpp` (shader-stamp file, not touched on this stream); 2x dearer in parallel than serial
   (ParLock(d.mesh) at :8124). DRAW1's PROGFRONT answers 0.33 of the draws and is off by default.
5. **Constant-buffer paths**, UBO + banks + storage 2.3 ms (castle: banks alone 2.9).
6. The game's own 1.7 ms draw code before the replay, serial with it (a frame is ~9.4 ms of chain): overlapping the replay of frame N with
   the game's work for N+1 is the structural lever (JOIN1 `RX_VK_DEFER_JOIN`, a diagnosis only).

## 5. Design of the bindless texture path (not built)

Goal: no per-draw descriptor writes for sampled textures; a per-draw block of indices instead.

**Descriptor model.** One global descriptor set (set 1), `VK_DESCRIPTOR_SET_LAYOUT_CREATE_UPDATE_AFTER_BIND_POOL_BIT`, one binding per
view type (2D, 2D array, cube, 3D, cube array, 1D), each `VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER` with
`PARTIALLY_BOUND | UPDATE_AFTER_BIND | VARIABLE_DESCRIPTOR_COUNT`. Today's set 0 stays the push set for buffers and for everything not
converted (storage images, texel buffers, compute, mesh). A push-descriptor layout cannot carry UPDATE_AFTER_BIND, hence two sets: every
pipeline layout becomes {set 0 push (buffers + fallback textures), set 1 global}. Set 1 is bound once per command buffer (compatible layouts
keep it across pipeline changes) and a recording begins with one `vkCmdBindDescriptorSets`.

**What an array entry is.** The (view, sampler) *pair*, not the texture: the engine's slots already resolve to a (view, tex, sampler) triple
(`TexSlot`), and a combined image sampler keeps the translator's `OpImage`/`OpSampledImage` shape unchanged. A pair gets a stable id in a
registry keyed by (VkImageView, VkSampler); the entry is written once (`vkUpdateDescriptorSets` on the global set, host-side, update-after-bind)
when the pair is first used. Entries are immutable while GPU work may read them, which is what makes a rebind of a guest texture slot
mid-command-buffer safe (the later draw gets another pair id; a design that indexed by the NVN pool slot itself would show the later texture
to the earlier draws, since the GPU reads descriptors at execution, not at recording).

**Lifetime.** A pair dies when its view is destroyed (texture destroyed, `destroy_gen`/`texture_kept_since` ring) or its sampler is retired
(`sampler_book`, the maxSamplerAllocationCount rotation). Its id goes to a free list tagged with the recordings timeline value of the last
submit that may use it (`vk_timeline_reached`, as the sampler retirement does); on reuse the entry is overwritten (UPDATE_AFTER_BIND allows
it while no *pending* command buffer uses it: the tag guarantees that). Dummies (per view type) get ids 0..5; a failed resolution binds the
dummy id, as today. Capacity: 16k entries per binding at first (market-mid has ~2,600 textures and 39 samplers live), grown by creating a
bigger set between frames, bounded by the device limits.

**Limits and vendors.** Needs `descriptorBindingSampledImageUpdateAfterBind`, `descriptorBindingPartiallyBound`,
`runtimeDescriptorArray`, `shaderSampledImageArrayNonUniformIndexing` (the translator already depends on the last for handle tables), and
`maxPerStageDescriptorUpdateAfterBindSampledImages` / `...Samplers` / `maxDescriptorSetUpdateAfterBind*` >= 6 x capacity (the Vulkan 1.2
descriptor-indexing minimum is 500,000; NVIDIA and RADV report >= 1M; Intel's older Windows drivers report less and may only take 2D + array
at 16k; AMD's Windows driver is the one to test first). The device-feature chain already enables whatever f12 reports. If anything is
missing, or the program has more than the push block's texture count, the draw takes today's path (the translator emits the old variables for
that program: `Profile::bindless_textures` false). Mesh-shader fallback, compute and FSR/frame-gen pipelines keep their own layouts.
The push-constant block is 96 bytes (`kPushSize`: rescaling layout 48, render area 16, guest pages 8, mesh first 8, fallback 16); the
128-byte minimum guarantee (AMD, Intel) leaves room for 8 u32 indices, so a draw with more than 8 texture elements falls back (market's
programs have up to ~10 slots: the share is not measured; a per-recording index buffer with its device address pushed is the alternative).

**Translator** (`engine/gpu/vk/eden/shader_recompiler/backend/spirv`, `spirv_emit_context.cpp::DefineTextures`, `emit_spirv_image.cpp::Texture`):
a texture descriptor stops being its own `OpVariable` at its own binding and becomes an element of the shared array of its view type
(`AddGlobalVariable` once per type, binding fixed 0..5, set 1); `Texture()` always takes the `count > 1` path with the index
`push.tex_index[descriptor_index] (+ element)`, decorated NonUniform when the index is not provably dynamically uniform (a fragment program's
index is uniform per draw, so NonUniform is needed only for handle tables: the table path already decorates). Depth-compare samplers and
integer images use the same array of their type (the sampler inside the pair carries the compare mode; today's `is_depth` split in the
descriptor stays as a key into the pair registry). `texture_scaling_index` and the rescaling words stay keyed by descriptor index. New
capabilities: `RuntimeDescriptorArray`, `SampledImageArrayDynamicIndexing`; `PartiallyBound` is a layout flag only. Shader stamp: this changes
every program's SPIR-V and layout, so the `kStateStamp` / shader-cache stamp moves and every player re-prepares shaders once (the precompile of
~13,000 pipelines, as for any translator change); the pipeline cache is keyed by SPIR-V and is dropped with it. This is the part the stream
rules forbid touching without a brief.

**Replay** (`vk_draw.cpp::build_descriptors`, `ensure_layout`, `bind_descriptors`): in the texture loop, `TexSlot` gains `pair_id`; a hit writes
`index_block[k] = sl->pair_id` instead of `out.imgs.push_back`, and the `VkWriteDescriptorSet` for that binding is not made (the push set
shrinks to the buffers, `ensure_layout` counts only non-converted bindings, `total <= max_push_descriptors` gets easier). A miss resolves as
today, then registers the pair. The index block is appended to the push-constant data (`data[]` at line ~4394, one `vkCmdPushConstants`), and
the THIN_PUSHC dedupe sees it as changing bytes. `texture_touch` and `draw_sampled()` stay.

**Texture arrays and 3D.** View types are separate arrays, so an array texture and a cube are different bindings with the right `OpTypeImage`;
a handle table (count > 1, per-pixel index) becomes `tex_index[d] + element` over consecutive pair ids: the table's pairs must be allocated
contiguously (a run per table) or the table path falls back (it is the clustered-light shadow maps, one program family).

## 6. Effort and risks (for the record; not recommended on these numbers)

| piece | days |
|---|---:|
| translator: shared arrays, index block, depth/integer/array/cube/3D/gather/query forms (every `Texture`/`TextureImage` user), tests | 3-4 |
| layouts: set 1, pipeline-layout change in `ensure_layout` and the other layout makers (mesh fallback, copy kernels), bind per recording | 2 |
| pair registry, lifetime tied to destroy ring + sampler retirement + timeline, growth | 3 |
| replay: slot -> pair id, index block, fallback rules, the push-block dedupe | 2 |
| checks: `RX_VK_BINDLESS_CHECK` comparing both paths' resolved views per draw; pictures in 6 scenes (shots + framelog) | 3 |
| AMD / Intel / PC 3050 runs (no AMD or Intel box on the lease system today) | 2+ |
| **pilot to default-off**: ~12 days; to default-on across vendors: 4-5 weeks | |

Risks: (1) stale entries (a view destroyed while an entry still names it: device lost, or a wrong picture): the whole registry hangs on the
timeline tagging; (2) the same set 1 for every pipeline means `vkCmdBindDescriptorSets` interacts with push descriptors and with the
FSR/frame-gen layouts (compatible-layout rules); (3) NVIDIA's non-uniform index codegen can cost GPU time in texture-heavy fragment shaders (not
measured; the GPU is not the bottleneck at 87 fps but is on the 3050); (4) the translator change touches every program: a bug is global; (5)
players re-prepare shaders once; (6) the gain is inside the run-to-run spread of the scene (87.4 / 85.6 / 86.9 / 86.5 fps for the same build).

## 7. Dead ends and things that did not apply

- No new counters: `RX_VK_PROF_FINE`'s sections, `RX_VK_PARLOCK_STATS` and the per-op tables already split every category in the brief
  (handle resolution + lookup = "textures", descriptor writes + pushes = "bind descriptors", pipeline lookup + bind, vertex/index binds, banks +
  UBO + storage = constant buffers, hazards/dynamic state/push constants = state, the draw call, the dry pass, the replay wall's steps).
- Sync and bookkeeping on the replay thread (memory work 0.46, queue submits 0.36 ms over 12.7 calls, slot waits 0.06) are small.
- `RX_VK_NO_DRY_MARKS=1` moves 0.9 ms from the dry pass into the workers and changes nothing (2d).
- Not run: castle-move with PARLOCK_STATS; an A/B (nothing to A/B: no code); the PC 3050 (own session).
- The VKC1 branch's `RX_VK_THIN_TEXSEC` (a stage's texture section kept across draws) is not in integ4; it attacks the same 3.66 ms from the
  other side (skip the work rather than make it cheaper to push) and needs no translator change. Its slot-version fix was never measured; if
  texture time is to be cut, that and a lock-free `texture_touch` are the cheaper routes (est. 0.2-0.5 ms critical path each).

## 8. Raw data

Runs: `E:\OOT\HeyListen\build\s5\bind1-{m-plain,m-fine,m-fine2,m-parlock,m-nomarks,m-serial,c-plain,c-fine}` (game_log.txt, present_trace.csv),
scripts `E:\OOT\scratch-bind1\series1.sh`, `series2.sh`, `avg.py`. Leases: speed, priority 2, released.
