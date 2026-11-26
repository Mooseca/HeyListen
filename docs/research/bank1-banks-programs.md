# BANK1: the driver banks and the program lookup (23 Nov 2026)

Copyright (C) 2026 Sacrappy

Branch `perf/bank1` from `refactor/integ4` (7f9a8e8bf). Main PC, RTX 5070. Status: **interim** (see section 6: what is measured, what waits
for machine time).

## 1. What the first profile says (castle-move, `RX_VK_PROF_FINE=1`, build `bank1` with every new switch off, 34 steady windows, 1,896 draws a frame)

Summed over the recording threads, ms a frame (`E:\OOT\scratch-bank1\avg.py`, runs `build/s5/env-bank1-prof1-*`):

| part | ms |
|---|---:|
| banks (uniform_range, index 0 and 2) | 2.32 |
| of it the fill of a **task or mesh** stage | **2.10** |
| of it the fill of a compute stage | 0.04 |
| of it the fill of a graphics stage | 0.01 |
| of it the stream copy and kept bytes | 0.07 |
| program lookup (program_for) | 1.68 |
| of it **the answers' handles read** (`answer_handles_memo`) | **1.21** |
| of it the last picks' pair, the pick's key, the validity, program_pick | 0.08, 0.06, 0.16, 0.13 |

Findings that change the plan:

1. **The banks of graphics stages are not the cost.** 0.33 fills a draw, but 0.16 of them are graphics c0 and cost 0.01 ms in all; c2 is never
   filled at all (0 fills: no program reads c2 on the GPU). The refill the brief asks about is already skipped by `tex_gen`/`ssbo_gen` (0.53
   of 0.86 bank calls are kept by generation). HL_UBO_WRITER=1 (the native writer) changed nothing measurable (banks 2.32 -> 2.46, noise).
2. **90% of the bank time is the task and mesh stages' c0**: 0.07 fills a draw = 133 fills a frame at ~16 us each. Almost all of it is the
   pointer table (`pointer_table`, vk_bank.cpp): for each small storage buffer a `memory_read_as_submitted`, a `host->gpu_guest` per word, then
   `gpu_pool_start/end` per found pointer (a one-span thread cache, a miss takes ParLock and pools_mu). The draws that cost most are a few
   mesh programs (a03bdab9: 1.5 draws a frame at 900 us, 507e946d: 29 at 49 us).
3. `HL_BANK_LEAN=1` (c2 of every stage by `tex_gen`, c0 of task and mesh stages by `ssbo_gen` + the submission's stamp): **0 hits**. Those
   draws bind their storage buffers anew at every draw, so the generation moves each time. Banks 2.32 -> 2.09 is noise. Dead end as a
   saving; kept (off) with its check mode.
4. **Program lookup**: 31% of the picks have other texture handles than the pick's last ones; all of them read every answer's handle
   (`descriptor_handle` -> `stage_cbuf_word`; for OoT most handles are words of the draw's uniform block: `ub_read`). That read is 1.21 ms of the
   1.68. The pair (`ProgFast`) answers 0.41 of the draws and costs 0.08 ms. `program_pick` (the lock) runs 0.001 times a draw.
5. `HL_MESH_PICK=1`: the mesh programs' lookup was 0.05 ms a frame; the switch makes it lock-free (hits 0.037 a draw) and `draw() whole`
   went 12.94 -> 11.43 in that one run (ParLock no longer held for it), but the program lookup itself did not move. Needs the A/B.
6. `HL_PICK_TLS=1` (the shared picks' counters per thread): program lookup 1.68 -> 1.63, banks 2.32 -> 2.13, `draw() whole` 12.94 -> 11.73:
   inside one run's spread; needs the A/B.

## 2. Switches (all default off)

| switch | what | check |
|---|---|---|
| `HL_BANK_LEAN` | generations above | `HL_BANK_LEAN_CHECK=1` fills and compares every kept bank |
| `HL_MESH_PICK` | task/mesh program kept per thread by serial + colour types and the answers' slot/version vector, found with no lock | `HL_MESH_PICK_CHECK=1` |
| `HL_PICK_TLS` | the program picks' counters per thread | none (counters only) |
| `HL_PTR_MEMO` | per-buffer pointer words kept per thread by (address, size, submission stamp) | `HL_PTR_MEMO_CHECK=1` makes both tables, uses the one without the memo |
| `HL_POOL_SPANS` | the thread keeps 8 pool spans instead of 1 | none (the same spans, looked up in 8) |

vk_shader.cpp and vk_bank.cpp are shader-stamp files: this branch changes the stamp once (a first run re-prepares shaders).
`RX_VK_PROF_FINE` gained: the bank fills by stage kind, the stream copy, program_for's parts, the pointer table's build / reads / pool lookups,
pool-span misses, `ub_read` for handles.

## 3. Tests
`tests/test_bank_gen.py` (updated for the new expressions, not weakened), `test_mesh_pick.py`, `test_ptr_memo.py` (wiring plus a model of the
memo against the table made without it), `test_switches_documented.py` (docs regenerated with `engine/scripts/list_switches.py`).

## 4. Dead ends
- Skipping c2 refills: nothing to skip (c2 is not filled).
- HL_UBO_WRITER for these banks: the fills it speeds are 0.01 ms.
- Bank generations for task/mesh (HL_BANK_LEAN): the storage buffers change at every draw.

## 5. Not measured yet
Everything below waits for machine time (the owner is playing; leases re-queued at priority 2): the PROF_FINE profile of the second build (pointer
table parts, `ub_read`), the fps A/B (castle-move, market-spin, kokiri-idle, 3 rounds, `ab_env.sh`), the check runs (0 mismatches), the pictures
(`RX_VK_SHOTS`).
