# What the frame's heavy replay is made of (stream R4, 2026-11-15, PC 3050, castle-move)

Tools (logging only, `RX_VK_PROF_FINE=1`, every 120 presents): `a frame (fine)` (draw sections summed over the recording threads, now with the
program lookup, the pipeline lookup and the texture slots resolved again), `a frame (fine, replay thread, wall)` (submissions, the dry pass,
the segments, the command buffers recorded whole), `replay_handle_early's steps` and `ops of the dry pass / segment workers / whole`.
`RX_VK_PRESYNC_STATS=1` now also times the dirty-page scan and the chunk diff.

## Where the replay thread's wall time goes (ms a frame, 2.2-3 big command buffers, ~2,300 draws)
Submissions with 300 draws or more: 14.3. Of the early path's steps: the mirror pre-sync before the dry pass 4.2, the dry loop 2.6, the replay
thread's own (last) segment 4.7, waits and submits 0.6; 18 small command buffers recorded whole here 2.4.
Summed over threads, per draw: textures 2.0 us (of it 0.9 resolved again: 1.0 us each), program lookup 1.2, user uniform buffers 0.55,
storage buffers 0.56, descriptor push 0.66, pipeline bind 0.55, vertex+index binds 0.45. Raw `vkCmd*` calls are a small part; most of the
rest is already cached per thread (texture slots, handle hits, banks, vertex sets, descriptor reuse), so there is no large repeated work
left to remove between draws. The program lookup is in vk_shader.cpp (shader stamp): not touched.

## The pre-sync: the chunk diff hashed every page again
On this PC (slow link) the mirror syncs' chunk diff is on, and the capture's copy is meant to make its hashes (TICK-060). The claimed copy
(`RX_VK_CAPTURE_CLAIM`, on by default since sprint 5) dropped them: 6 slots of ~1,340 a submit were hashed by the copy, the pre-sync hashed
the rest again, 3.7 ms of its 5.4 ms. `claim_run` now passes the hash arrays on (`RX_VK_CLAIM_HASH`, default on, =0 as before): 1,451 slots
hashed by the copy, 13 hashed again, the pre-sync 2.5 ms, the heavy submissions 14.3 -> 10.4 ms a frame.
Speed (interleaved, 3 against 3): castle-move 31.9 -> 36.1 fps, kokiri-idle 34.0 -> 37.3 fps.

## Tried, no gain over the spread (removed)
A segment's place on a fixed worker (TICK-052's affinity, on the early path), 16 handles a texture slot (resolved again 0.92 -> 0.64 a draw, time
the same), later early segments shorter (the first longest): 36.2 against 36.1 fps.
