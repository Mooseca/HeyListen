<!-- Copyright (C) 2026 Sacrappy -->
# ORDER3: the culling-results read stuck inside the writer job (26 Nov 2026)

Follow-up of `order-readback-decouple.md` (RX_VK_RB_EARLY, on main since bdf3c771b). The read of the 0x3980 culling / camera block
(R4) waits for the copy behind its last writer. When it waits long, the order thread is inside that writer job, and
the job's last R4 copy is recorded late. This note says where the job's time goes, whether the eight culling programs could be recorded
first, and what that would take. Logging only on this branch, plus one behaviour change (the laptop's wait, below).

## Diagnostics (perf/order-writer-stall)

- `RX_VK_ORDER_SLOW_JOB_MS=<ms>` (20; 0 off): an order-thread submit job over that time, and one writer job in 600, is logged with:
  - its replay phases on the order thread (dry pass, own segment, wait for segments...) and its waits by site;
  - the replay's time categories over the job (texture lookups, uploads, descriptors, pipelines, programs...);
  - the draws, dispatches and pipelines made;
  - when the R4 block's last copy was recorded;
  - what the order thread recorded before the first culling program (bindings, programs, written storage ranges), and how many of the
    culling programs' storage bindings overlap a range written before them in the job;
  - the same for their textures and storage images, against the textures the job wrote before them (the dry pass's targets and
    images up to the first culling dispatch).
  Cost when no job is slow: two clock reads per replay phase change and per wait site on the order thread, a lookup per storage binding
  on the order thread (a mutex and a short vector), a hash lookup per texture binding of the culling programs; the log line only past
  the threshold.

## What the warp tour and Hyrule Field showed (main PC; build/s5/o3-w1, o3-w2, o3b-w1, o3b-w2, o3b-H)

- **The eight programs come after most of the frame's draws.** Before the first of them the order thread records 325-14,201 bindings of
  37-6,612 programs. In steady Hyrule: 337-2,437 bindings of 129-1,054 programs; the job takes 3.2-5.7 ms and the last copy is recorded
  1.4-3.4 ms in (the PC 3050's ~2 ms recording wait on half of Hyrule's reads, -3.7 % against the old read there).
- **At a zone load the writer job takes 20-500 ms, before the eight.** In one tour, 54-59 jobs were over 20 ms, 25-30 of them the
  writer job. Their time goes to the replay's own work on the frame's first use of things:
  - a 297 ms job: texture lookups 238, uploads 173, descriptors 335 (summed over threads);
  - an 81 ms job: pipelines 85, programs 99;
  - other jobs: up to 68 ms of dry pass even with warm caches, and one late-fix wait of 32-123 ms.
  STUT3 owns the uploads and the parallel replay's lock.
- **Storage dependencies of the eight:** 0 of their 135-164 storage bindings overlap a range written before them in the same job in
  steady Hyrule. On the tour 0, once 1: 0x113b62d000+0x5b40, written by f78bce74159566cc and bound by fcd994b5b6761630, a ninth program
  that writes a 0x3980 range in some jobs. Its R4 writes are copied like the others' (every exact binding is). But a job where it runs
  makes nine writes against the eight learned, so the eighth copy is taken as final, and a read between the eighth and the ninth
  copy gets the block without the ninth write. Rare (it was seen in the warp tour only); a learned count per job kind would remove it.
- **Texture dependencies of the eight** (build order3c; job lines where the writer job's dry pass reached the first culling dispatch;
  build/s5/o3c-H Hyrule walk, 68 jobs; o3c-w1 + o3c-w2 warp tours, 190 jobs; counter `r4tex.py`):

  | program | jobs (Hyrule / tour) | textures bound | storage images | sampling a texture written earlier in the job (Hyrule / tour) |
  |---|---|---|---|---|
  | 3018813b775edcb6 | 61 / 134 | 1 each | 0 | 0 / 0 |
  | 93be496778e568b5 | 63 / 48 | 2 each | 0 | 0 / 0 |
  | abccf81b45c5eb50 | 63 / 151 | 2 each | 0 | **53 / 4**: a 512x512 RGBA16F texture (format 97), and on the tour an 800x1000x8 array (format 70) |
  | b612216258832b9c | 63 / 96 | 2 each | 0 | 0 / 0 |
  | fcd994b5b6761630 (ninth) | 4 / 54 | 1 each | 0 | 0 / 0 |
  | 44511d69b52282ad, 6344c53d07706e30, 7984161db3e053b5, fd958faab99f20a2 | | none | none | |

  **Verdict: the eight cannot simply be recorded first.** abccf81b45c5eb50 samples, in 53 of 63 steady Hyrule frames, a 512x512
  RGBA16F texture that an earlier draw or dispatch of the same job renders. Moving the eight ahead would need that texture's producer
  (and whatever it reads) moved with them, or abccf81b45c5eb50 left in place with the block final only after it, which is late again.

## Shape (a): recording the eight first

What it would take:
1. During the writer job's dry pass, at the first culling dispatch, keep the replay state there (the dry pass already keeps state
   copies at its segment points).
2. Record the eight dispatches and their copies from that state into a command buffer of their own, submitted ahead of the job's
   segments.
3. Leave them out of the segment that would record them again: they append to large lists, so running them twice is wrong.
4. Put the barriers right for whatever the later draws read of their output.
The dry pass itself must first reach them: it walks the whole command buffer before recording, up to 68 ms at a load even warm. So
either the culling dispatches are found ahead of the dry pass (a quick scan of the command stream for the learned programs), or the
early recording waits for the dry pass's point.

Gain: in steady Hyrule the copy would be there ~1.5-3 ms earlier on half of the reads, about the 3050's missing 3.7 %. At loads,
everything the job records before the eight stops being in the read's way (20-500 ms jobs).

Feasibility after the texture check: not as such (abccf81b45c5eb50 above). Risk: high. It changes the GPU's order inside a frame and the replay's stream state handling. A texture the eight sample that an earlier
draw renders (a depth or a pyramid) would make it wrong, which is what the texture check is for. Multi-day; after the release, the
owner's decision.

## Program translation at zone loads (nobody's yet)

The "programs" category (97-99 ms in 50-81 ms writer jobs of the warp tour) is the shader recompiler translating programs the replay
meets for the first time in play. The start's preparation compiles what the caches already list. The caches are filled from earlier
sessions on that PC and the bundled pipeline-state list, so a zone's programs that were never seen on the PC, or that the list does not
hold, are translated at their first draw, on the replay's critical path. Not measured further: which programs, and whether the
bundled list could hold them, is open.

## The laptop's wait (behaviour change)

The first wait of a read for its copy is now `RX_VK_RB_EARLY_WAIT_MS` (30) or three of the game's last frame times, whichever is longer
(`rb_early::first_wait_ms`). It changes anything only under 100 fps. At 13-15 fps the laptop fell back to the old path in about 7 % of
its reads at a fixed 30 ms; the 200 ms long wait after it is unchanged.
