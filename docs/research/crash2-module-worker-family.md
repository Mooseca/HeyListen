# CRASH2: the ModuleSystemWorker destroy-path family of v0.4.3

Question: why 20 of 49 v0.4.3 crash reports (41 %; v0.4.2: 9 of 105) die in f_80a30a00, f_80a31030, f_803b44e0 or
f_834bdb90 on a ModuleSystemWorker thread (chain f_80a31030 <- f_80a31220 <- f_82c20a40 <- f_83b78d80). Background:
docs/research/crash1-triage-2026-11-24.md (branch docs/crash1). Only function names and offsets here, no game code.

## State (kept current)

- 2026-11-24 08:20: worktree E:\OOT\HeyListen-wt\crash2, branch fix/crash2 from origin/main 0e5db2102. History done
  (below). Build lease requested (queue behind four builds). Loop script ready (E:\OOT\scratch-crash2\loop.sh, outside
  the repo): age toggle (cheat 999), then warps 1010 DMC, 1023 Fire Temple, 1026 Spirit, 1020 Dodongo, 1011 Goron City
  and so on every GAP s.
- Run 1 (bin main8 = main of 2026-11-23, slot b, 19 min, HL_TRACE=2 HL_JOBGROUP_CHECK=1 HL_STAGES_CHECK=1):
  build/s5/c2a-on/game_log.txt: 29 map loads (age toggle by cheat 999, then warps 1010 DMC, 1023 Fire, 1026 Spirit,
  1020 Dodongo, 1011 Goron City, 1009 DMT), no crash. Invariants clean: takes/passed/runs not run 0, bad finishes 0,
  bad counts 0, double completes 0, double runs 0, heap order 0, group ends checked 518098 with 0 faults, take count
  below 0: 0; stages: registrations compared 275625, differ 0; observation: lane drift 173. INVALID for the Crater
  (and Fire Temple) as a crash test: Link is adult without the Goron Tunic, so the heat kills him (owner saw it); these
  loads happen but are not the reports' path. Spirit Temple and Dodongo's Cavern loads are valid.
- Run 2 arm "c2a-off" (HL_JOBGROUP=0 HL_MODSTAGES=0): INVALID, the boot never reached play ("skip title: gave up
  after 120 s"): a helper of mine pressed A into the live-input file before play began. Redone as c2b-*.
- Run 3, arm c2b-off (HL_TRACE=2 HL_JOBGROUP=0 HL_MODSTAGES=0, the guest's own job group and stages, bin main8, slot a):
  REPRODUCED after 17 map loads (about 7 min of warps), on the map DodongoCavern (adult; a valid map). Log copy:
  E:\OOT\scratch-crash2\c2b-off-game_log.txt, recorder text E:\OOT\scratch-crash2\hl_trace_crash.txt. Fault: read at
  0x100000000000 in f_80a30a00+0x30a on ModuleSystemWorker4, chain f_80a31030+0x22e, f_80a31220+0xe09, f_82c20a40+0x963,
  f_8007fe60 (the translated group, so the natives were NOT involved: the frames show the guest's group, not hl::). So the
  family exists with HL_JOBGROUP=0 HL_MODSTAGES=0; the natives are not its cause (one sample, but the first arm tried).
  (The natives-on arm c2b-on was stopped by the coordinator's order at 13 maps, no crash yet: no conclusion from it.)
- What the recorder says (hl_trace_crash.txt): the objects the destroy path walks lie in the guest heap 0x11787ea8d8
  (size 0xf800000, inside the NVN pool the back end mirrors: "mirror made ... [0x1178000000, 0x117f000000)"). Those same
  pages, [0x117e70d000,+0x40) and [0x117e70e000,+0x40), were written back by the back end (GPU writes copied into guest memory,
  "write-back by the back end", every 250 to 760 ms up to 1.4 s before the crash, submission 218410) while guest objects
  allocated by SceneLowPriority 22 s earlier lived there (x24 = block 0x117e70dff8 size 0x28 straddles 0x117e70e000;
  the neighbours 0x117e70dce8 size 0x70). The same addresses held 0x90 and 0x40 blocks freed by ModuleSystemWorker2 22.7 s
  before. So a GPU write-back lands on the game's live heap objects (their chunk headers / fields): the destroy path then
  reads a bad pointer. No double free is visible in the recorder: the blocks the crashing thread frees just before are
  distinct, not freed before.
- Hypothesis (to prove): the back end writes GPU words back to guest addresses the game has already given to its heap
  (a GPU buffer freed or re-used while a recorded binding still lists it as written, or a write-back of the lazy kind
  with a stale mirror). v0.4.3 changed this path (bccc744c2: pools under 4096 KB always written back and a CPU write makes the
  pool eager, RX_VK_WB_SMALL_EAGER_KB, RX_VK_WB_POOL_EAGER; f0f7ae922: the GPU's writes visible to the host at each
  submission's end; 62b2cb694 / 539d20ad8 retired and idle imports), which fits the rise from 9 % to 41 % and "NVIDIA only".
  Test that would prove it: the same warp loop (loop.sh, cheats 999 then 1010/1023/1026/1020/1011) with
  RX_VK_WB_POOL_EAGER=0 RX_VK_WB_SMALL_EAGER_KB=0 (the v0.4.2 behaviour) against the default, HL_TRACE=2, many more
  loads (the first crash came after 17); and in the recorder a check at each write-back that the range holds no live
  game heap block (hl_trace has the live-blocks table: log "write-back into live block" with the block's allocator).
- Not done: a build of the worktree (mkg.ps1 failed when its build ticket was re-queued), the natives-on arm to a crash,
  the lifted-code reading beyond the call chain, the fix. The Crater runs (adult without the Goron Tunic burns) do not
  count; no Crater-valid run was made. Leases: all released, game window closed.
