<!-- Copyright (C) 2026 Sacrappy -->
# ORDER2: the order thread's readbacks without the previous frame's whole replay (25 Nov 2026 -)

Goal (the owner's order of 25 Nov, 21:00): keep the order thread's gain (`RX_VK_ORDER_THREAD`, +6 to +12 fps on the RTX 3050) and give the
game's CPU the right GPU results, so a frame's CPU work does not depend on how far the replay has got. Today's choice is between the flashes
(old read), -15 % on the 3050's Market (flash2f's wait, `RX_VK_ORDER_RB_JOIN=5`) or the order thread off.

## What the measurements say (main PC, build order2a = flash2f + `RX_VK_ORDER_R4_MAP`, run build/s5/o2-M2, Hyrule Field, 60 frames)

1. **R4 is not visibility bits.** The 0x3980 block starts with 0.1, 25000, 1.7778, pi/4: a camera / view block, followed by ~1850 more
   non-zero words (lights and fog, by the flashes' look). Eight compute programs write it, all in ONE job a frame (queue
   0x101004133020, the last submission before the present): b612216258832b9c, 44511d69b52282ad, 93be496778e568b5, 6344c53d07706e30,
   abccf81b45c5eb50, 7984161db3e053b5, 3018813b775edcb6, fd958faab99f20a2, in that order. The same job writes the R5 lists (0x9b040,
   0x8b040, 0x44b040) and R6 (0x1b580).
2. **The dependency is the frame's last submission, read early in the next frame.** That job is handed to the order thread at the end of
   game frame c-1 and runs at once (handed-over to run: 0.0-1.0 ms: the order thread has no backlog there). Its replay takes 3.9 ms
   (median); the R4 bindings are recorded 0.6-2.8 ms into it (the last one at 2.1 ms median, 2.8 at most). The game's culling job reads
   the buffer about 4 ms after the hand-over: 69 of 240 reads waited (the first read of the fresh buffer each frame), 1.56 ms median,
   3.2 at most. The other reads of a frame (the older buffer, R5, R6, written 12 ms before) wait for nothing.
3. **Why the wait is long**: the value reaches guest memory with the submission's write-backs, which run at the submission's END
   (`group_tail_send` -> `memory_end_submission_of`), after the job's whole recording and all of its GPU work, although the eight
   programs are done 1-2 ms of recording earlier. On the 3050 the same wait is 4.4-5.5 ms, once a frame (coordinator, matrix116).
4. **A fixed lag is not the answer**: ring R4 at lag 3 = 14.3 one-frame luma steps a minute in the field (o2-L3, 167 s; the plants), lag 2
   = ~1.8 a minute, all dark and small (o2-L2 + o2-L2b, 132 s in the field), old read 3.1 (o2-B, 96 s), flash2f's wait 0 (o2-D, 140 s).
   Lag 2 hands out entries tagged two game frames back (ring ages 2243/3/5): a camera two frames old.
   (The scripted walk opens the pause menu in many runs: counts are on field frames only, `count2.py`.)

## Design: stage the readback where its last writer runs, not at the submission's end (direction 1, inside the job)

The producers are not behind a backlog; they are at the head of a long job whose results are published only at its end. So:

- **Early stage.** When a program that writes a learned readback range (R4 first) has been recorded, the replay records right behind
  its dispatch a copy of that range from the mirror into a slot of the readback ring (the STEP1 ring: engine-owned host memory, no
  write-back of the range to guest memory). The slot is tagged with the game frame and with the GPU completion of the command buffer
  it is in (its segment's own submission and fence/timeline value), and it is complete once the range's last writer of the job has
  been recorded (learned: the number of written bindings of that range in a writer job, eight here, stable) and that segment is on the
  GPU. Segments already go to the GPU as they are recorded (`early_submit_job`), so the staged copy is on the GPU ~2 ms into the job.
- **The read** of the range waits for that frame's slot only (bounded; a range with no writer in the jobs handed over before the read
  is answered at once from the newest slot), then copies it into guest memory, as the ring's `rbring_apply` does. The write-back at
  the submission's end leaves the range alone (the ring's rule), so nothing lands over the CPU's view later.
- **Exactness**: the value is the GPU's result of the same job the inline replay published, and the newest writer the game handed over
  before the read: the same value inline gave (the ring's `HL_RB_LAG_CHECK=1` mode compares it with the old path's, per read).
- **Expected cost**: the read waits until ~2.1-2.8 ms of recording + the copy's segment on the GPU, against ~4 ms + the whole
  submission's GPU work today. On the main PC the read comes ~4 ms after the hand-over, so most reads should not wait at all; on the
  3050 the wait shrinks by the job's tail (recording and GPU). Whether that is within 2-3 % of the old read is to be measured.
- **Generalisation**: the rule is per learned range, not per size: any readback class whose writer sits inside a submission (R1-R6 all
  go through `rbring_note_read` / the written bindings) can be staged at its writer. R5 and R6 are read a frame later (12 ms after
  their writer) and wait for nothing today; they keep the old path until an audit shows them stale.

## Directions weighed and not taken first

- **Overtake the order thread's backlog** (run the producer job ahead of others): there is no backlog to overtake at that point
  (handed-over to run 0.0-1.0 ms); the time is inside the job and at its end.
- **Compute R4 on the CPU** (direction 2, the owner's "renders that do not depend on the previous frame"): the block is camera / view
  data, so it is probably derived from constant buffers the CPU wrote (the camera) and from GPU state of earlier frames. Eight programs
  write it, and each also writes large GPU pools (0x980000, 0x1d840 bytes...), so a native version means translating eight shaders and
  proving bit-equality (a `_CHECK` mode against the GPU's block). It is the clean end state and the next step if the early stage does
  not bring the 3050 within 2-3 %: first a dump of the block and of the programs' inputs to see which words depend on GPU-only state.
- **A conservative merge** (visible if visible in any of the last k results): not applicable, the block holds floats, not flags.

## Not known yet

- Whether the segment holding the last R4 dispatch is submitted before the job ends in every frame (segment sizes, the dry pass's
  holds); the build's counters will say.
- Whether the CPU writes into the R4 block between its reads (the ring's tainted-range rule covers a direct write).
- The 3050's numbers.
