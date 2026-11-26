<!-- Copyright (C) 2026 Sacrappy -->

# FOOT1 (23 Nov 2026): the resident footprint and the commit growth, mem/session-growth's levers on main

Work in progress: stopped for the main PC's reboot (section "State at stop"). Brief: bring mem/session-growth's levers onto
main 2ed3bab9c and measure them over a long zone-changing run, with and without memory pressure (memhog fixed mode, about
1.5-2 GB free).

## 1. The port (branch perf/foot1, worktree E:\OOT\HeyListen-wt\foot1, from main 2ed3bab9c)

| commit | lever | switch (default) | adapted |
|---|---|---|---|
| c8ac5c4e2 | a cold unit given up is held a while, not for good (from 0200a90bc) | `HL_MEM_COLD_GIVE_UP_S=<s>` (0: for good, as before) | header comment kept beside main's HL_FAULT_WATCH/LOWMEM lines |
| 27ba096c7 | imports freed after a retirement or an eviction tell the host (from b04ca74a6); never-imported pool mirrors given back when idle | `RX_VK_UNPIN_RETIRED=1` (0: as before); `RX_VK_POOL_MIRROR_IDLE=1` (only with `RX_VK_POOL_MIRROR=1`) | main's DeadImport had moved up (Longshot 839a8cc4); `retired` flag added; the unpin put behind a switch (it was unconditional on the branch) |
| 8b7d3f11b | the textures' image blocks given back (from 247e46430) | `RX_VK_BLOCK_RECLAIM=1` (0: as before), `_FREE_MB` 512, `_UNUSED` 1800, `_MB` 256 | placed after main's dead-target sweep; the block count is forgotten in `destroy_image_now` (main's RX_VK_REAP destroys images on the reaper's thread) |
| 98d7da5f1 | `RX_VK_POOL_MIRROR_IDLE` opt-in | | on the branch it was the default with the pool mirror; MEM2's unmerged HL_COMMIT_LEAN would turn the pool mirror on by itself |
| c922ff25c | docs: memory-boundary.md section 22 (the branch's section 21), switch lists regenerated | | |

Not ported: 1026956a2 (a pool mirror's texel views keyed by device address). Main's 1914073ac already releases a mirror's texel
views when the mirror goes. `RX_VK_POOL_MIRROR` stays off: it loses the torch flames.

Tests: `run_all` passes 497, fails 2 (the known nup failures nx2/test_nup_paths and nx2/test_nup_read_name), skips 53.
`engine/native/tests/mem_test.cpp` (the give-up test) built by hand with clang++ and passes. `list_switches.py --check` is up to date.
Build: `bin/foot1` (mkg.ps1 -Block -Lift -Pgo, 329 s, exe sha256 23ef23b707fa60d0...).

## 2. The tour (verified)

Market save, kokiri-idle scene. `HOS_INPUT_LIVE` gets `!cheat 10xx` warps after "play: began", one every 40 s:
+15 1001 HyruleField, 55 1002 Kakariko, 95 1009 DeathMountainTrail, 135 1011 GoronCity, 175 1020 Dodongo, 215 1003 Market, 255 1000
Kokiri, 295 1005 LostWoods, 335 1001 HyruleField, 375 1012 ZoraRiver, 415 1013 ZoraDomain, 455 1007 LakeHylia (a HyruleField map), 495
1011 GoronCity, 535 1020 Dodongo, 575 1003 Market. HL_RUN_SECONDS=665: 610 s of play, 16 maps, every warp taken (both picture runs).
Ids come from `host/hos_main.c` `oot_destinations`: 1000 + the index.

Each run has the switches `HL_HITCH_LOG=rel:8 HL_STALL_WATCH=rel:8 HL_STALL_WATCH_MAX=400 HL_MEM_ACCOUNT=30 RX_VK_LEDGER=30 HOS_HOST_SPLIT=40,30
HL_FAULT_WATCH=10` and the external sampler `E:\OOT\scratch-foot1\sampler.py`, which writes a line every 30 s into `build/s5/<tag>.mem.csv`
(private commit, working set, available RAM).
Analysis: `python -I -B E:\OOT\scratch-foot1\analyze.py build/s5/<tag>`. It gives fps from play+10 s and the stutters during play
(via `stutter_report.py`, page-fault class, 50/100/250 ms). It also gives the census means after 150 s: window RAM, the driver's
32-128 MB commit, the commit charge. And the lever lines.

## 3. First data: the picture runs (slot lease, functional only, the machine shared with a build; numbers NOT for A/B)

| run | private commit max | commit, census mean after 150 s | driver 32-128 MB commit | window commit end | arenas commit | live imports end | heap units marked imported | avail RAM min / median |
|---|---|---|---|---|---|---|---|---|
| f1p-A (no switch) | 30.8 GB | 29.2 GB | 8.2 GB | 11.7 GB | 5.8 GB | 199 | 59,025 | 52 / 1342 MB |
| f1p-ALL (blk + unpin + give-up 120 s) | 30.4 GB | 28.8 GB | 7.8 GB | 11.7 GB | 5.8 GB | 199 | 56,903 | 463 / 1894 MB |

- The tour reproduces the owner's growth. Commit goes from 13.8 GB at 40 s to 24 GB at 100 s, then 29-30 GB from 290 s on. The
  working set stays at 6-9 GB.
- Where the 30 GB is at the end (census + ledger): the guest window has 11.7 GB committed, of which 4-7 GB is resident. The
  driver's 32-128 MB regions beside VRAM hold 7-9 GB, commit only. The driver arenas (512 MB and up) hold 5.8 GB, commit only.
  The heaps hold 0.7 GB and the tagged buffers 0.4-1.3 GB.
- `RX_VK_BLOCK_RECLAIM` emptied 25 blocks (462 textures, 289 MB; 38 made again, 6 within 3600 presents). Even so, the textures'
  pool still held 3840 MB of blocks with 2.7 GB free: 29 of 30 blocks are held by a texture used lately (1,800 textures). The
  block-level rule does not reach the fragmentation; `RX_VK_IMAGE_GENERATIONS=1` (on main, off) is the candidate queued in L2.
- `RX_VK_UNPIN_RETIRED`: 2,122 fewer 64 KB units held as imported at the end (59,025 to 56,903, about 130 MB). The cold pass may
  take those units again. It is small.
- `HL_MEM_COLD_GIVE_UP_S`: 0 units were given up in 10 minutes in either run. The lever only acts over long sessions (play8:
  19,508 units after 45 min) and cannot be measured with this tour.
- Pictures: no visible difference between A and ALL in Goron City, at Dodongo's entrance, or at the third Market entry. In both
  runs the entrance torches are unlit; that room is like that, and it is not the lit-torch spot of memory-boundary 21. The
  near-black shots are the loading screens, in both runs. Shots: `E:\OOT\scratch-foot1\shots\{A,ALL}`. The ALL run has no shots
  before frame 19350, because the folder did not exist: the game does not create it.

## State at stop (2026-11-23 reboot)

**Done.** The port: 5 commits on perf/foot1 (tip after this note: the docs commit). Tests run, the foot1 build made. The tour
verified. Two picture runs (f1p-A, f1p-ALL) analysed above. The PC 3050 run list sent: the coordinator routed it as 3050 Task
42/44/46, and its results come back to `E:\OOT\scratch-foot1\pc3050\`.

**Half done / not started.**
- No speed-lease run has started yet: L1 and L2 were still queued at the stop; their tickets were released and the scripts killed.
- The torch runs from `savelib/goron-city` and `savelib/dodongos-cavern` (A against ALL, 110 s, shots) were refused by runguard with
  rc 12: RAM under 4 GB free.
- Not measured: the pressure runs (memhog), the per-lever A/B, `RX_VK_IMAGE_GENERATIONS=1`.

**Scripts** (none running at the stop):
- `E:\OOT\HeyListen\build\s5\foot1_tour.sh`: speed lease, slot c, tour arms. Its arguments are the lease tag, `foot1`, the hog
  target in MB (0: none), then `"tag|env"`.
- `E:\OOT\HeyListen\build\s5\foot1_pic.sh`: the same on a slot lease.
- `E:\OOT\scratch-foot1\{tour_live.sh, sampler.py, memhog.py (STALL1's copy), analyze.py, torch.sh, pc3050-runlist.txt}`.
- Leases used: build `20261123-112012-foot1-build-d80d` (released), slot `...-foot1-P1-slot-2d45` (released), slot `foot1-torch`
  (released), speed `...-foot1-L1-speed-e88e` and `...-foot1-L2-speed-b697` (released at the stop, never granted).
- Slot c and slot a hold no foot1 binary: the backups are in `build/s5/foot1-bak*`. Slot a was taken by another agent's run after
  my torch lease, with that agent's own exe.

**Next commands after the reboot** (the build `build/s5/bin/foot1` stays valid; no rebuild needed):
```
cd /e/OOT/HeyListen
nohup bash build/s5/foot1_tour.sh L1 foot1 0 "f1-warm|-" "f1-A1|-" "f1-ALL1|RX_VK_BLOCK_RECLAIM=1 RX_VK_UNPIN_RETIRED=1 HL_MEM_COLD_GIVE_UP_S=120" > /e/OOT/scratch-foot1/L1.log 2>&1 &
nohup bash build/s5/foot1_tour.sh L2 foot1 0 "f1-blk1|RX_VK_BLOCK_RECLAIM=1" "f1-unpin1|RX_VK_UNPIN_RETIRED=1" "f1-gen1|RX_VK_IMAGE_GENERATIONS=1" > /e/OOT/scratch-foot1/L2.log 2>&1 &
```
Then the pressure leases: `foot1_tour.sh L3 foot1 1750 "f1-hA1|-" "f1-hALL1|<ALL>" "f1-hA2|-"` and `L4 ... "f1-hALL2|<ALL>" "f1-hgen1|RX_VK_IMAGE_GENERATIONS=1"`.
Then `bash E:/OOT/scratch-foot1/torch.sh` once RAM allows. Read each run with `analyze.py`, fill in this file (MB per lever,
page-fault stutters under pressure, proposed defaults), commit, and report.
