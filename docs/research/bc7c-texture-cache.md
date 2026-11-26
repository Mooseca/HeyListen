# BC7C: ASTC to BC7 coverage audit and a disk cache of the BC blocks

**VERDICT (2026-11-23): NO-GO. Do not merge; RX_VK_BC_DISK stays off.** Zone-entry hitches are not the BC transcode (about 1 ms GPU a frame), so a warm disk cache gains nothing
(warm zone entries equal off; 3 ms a read on the render thread) and all three disk arms ran at about 78 fps against 112 for off (cause not hunted). The audit shows what stays RGBA8 is negligible:
only a few over-2048 textures (Kokiri 10 tex / 356 MB held, 3% of the sampled bytes; Market and Field 0 sampled) and tiny ones (0 MB). Details below. The picture check (warm against off) was not run.


Branch `perf/bc7c` (from origin/main 5d9b08331). Goal: fewer texture stutters at zone entry, less texture bandwidth on the RTX 3050.

## What is written (not yet built or measured)

- `RX_VK_BC_AUDIT=<presents>` (vk_texture.cpp, texture_frame): every n presents the log has `vk: BC audit frame N: <class> ... textures ... MB held; sampled in the last 8 presents: ...`
  for decoded-ASTC textures: BC7, BC1, BC3, and RGBA8 by reason (small, 3D, msaa, over 2048, skipped levels, other). Zone-entry ASTC ms come from
  `RX_VK_PASS_TIMING=1` ("astc transcode", "astc from the BC cache (copies)"); cache hits across zones from the `vk: BC cache` line.
- `RX_VK_BC_DISK=1` (off by default), `_DIR` (default: the game folder, like the pipeline cache; set it elsewhere for tests), `_MB` (4096), `_AHEAD` (64 records):
  `gpu/vk/vk_bc_disk.h`. Two pack files `hookshot_bc_a/b.pack`; records `{magic,size,key,hash}+blocks` in creation order; header holds the encoder
  version (hash of the three ASTC/BC shaders + a manual revision) so a changed encoder empties the files; the older pack is deleted when the newer holds half the cap.
  Written off the render thread (a detached thread) once the GPU has written the blocks (entry pinned until written); read: on a RAM-cache miss the render thread
  reads the record into a host buffer (hash checked), then the disk thread reads the next `_AHEAD` records into the RAM cache. Index scan on that thread at start.
  The blocks are made on every transcode while it is on (also in RX_VK_BC_CACHE_LAZY mode), the RAM cache keeps its own rules.
- Tests: test_astc_batch.py updated for the two changed lines; switches docs regenerated (list_switches.py). Other failing tests in tests/ are the same as on main (229 of them: no compiler here).
- `build/s5/bc7c/pc3050_bc7c.sh` (main checkout, untracked): the PC 3050 script (off / cold / warm arms, castle-move and kokiri-idle, needs a build of this branch pushed there).

## Known gaps / ideas
- A hit in the older pack is not copied forward (a working set above half the cap thrashes).
- The folder default is the game folder (as the pipeline cache); a release must not ship the files (they are runtime-made).

## Results 2026-11-23 (main PC, build of fe76fd5c3: compiled first time with 0 errors; warp tour of foot1_tour.sh, 665 s, Market save)
Audit (RX_VK_BC_AUDIT, decoded-ASTC textures; "held" = alive, "sampled" = used in the last 8 presents), peak per zone:
- Market: BC7 1705 tex / 1665 MB held (398 MB sampled), BC1 1119 / 403 (75), RGBA8 small 52 tex / 0 MB, RGBA8 over 2048: 1 tex / 23 MB held, 0 sampled.
- Kokiri: BC7 2052 / 1845 (325), BC1 1197 / 421 (127), RGBA8 over 2048: 10 tex / 356 MB held (about 14% of the held bytes), 14 MB sampled (about 3% of the 466 MB sampled per 8 presents), RGBA8 small 68 / 0.
- Field: BC7 1164 / 1223 (451), BC1 764 / 296 (155), RGBA8 over 2048: 3 / 44 MB, 0 sampled, small 31 / 0.
- No 3D, msaa or skipped-level RGBA8 textures in these zones: what stays RGBA8 is the over-2048 ones (Kokiri, a few) and tiny ones. Not worth a BC path.
Disk cache, first cold run (cache folder empty, 2.9 GB written over the tour): fps from play+10 s 78.0 against 112.6 off; first Market entry 54 frames over 33 ms, 24.7 s of them, worst 8.8 s
(stallwatch: the presentation thread idle, page faults +22k): the writer held the index mutex during its disk write (render-thread lookups waited) and wrote at normal IO priority
while the game read its files. Fixed after that run: file write with the index mutex released; writer thread in background mode (low IO and CPU priority). Later zone entries in the cold run
are as the off run (a few ms, within noise). Disk reads in the same session (1643 reads, 3675 ms on the render thread: 2.2 ms a read, RAM-cache evictions) were counted.
Off arm: fps 112.6 from play+10 s, zone entries 8 to 56 frames over 33 ms (0.7 to 6 s of them in the 1500 frames after the zone), Kokiri worst 1138 ms.

Second pair after the fix (build ae33e3045), cold2 then warm on the same folder (2.8 GB, 3319 records written):
- cold2: first Market entry worst frame 1036 ms (8795 ms before the fix), 28 frames over 33 ms (3.2 s); other zones as off. Start-up (first present to the Market map line) 33.2 s, off 33.3 s, warm 33.3 s; the index scan (disk thread) 512 ms with 2.8 GB on disk, not on the render thread.
- warm: 3909 records read (3331 MB), 12.0 s of render-thread time in all (3.1 ms a read), 29850 read ahead, 0 bad; zone entries NOT better than off or cold: sums over 33 ms per zone 1.1 to 7.1 s against 0.7 to 6 s, worst frames 150 to 864 ms against 165 to 1138. Kokiri 4.3 s / 845 ms (off 6.1 s / 1138 ms, cold2 3.9 s / 812 ms: noise).
- Verdict: the zone-entry hitches are not the BC transcode (the GPU transcode of a zone costs about 1 ms of GPU per frame in the pass timing), so reading the blocks from disk gains nothing on the render thread and costs 3 ms a read.
- Problem: all three disk arms run at 77.5 to 78.2 fps from play+10 s against 111.7 for off (median present 9 to 11 ms against 3.5 ms; the GPU ms per frame are the same, 6.9 ms). Cause not found yet (not the writer: cold before the fix is the same).
  Suspects: the RAM cache storing every texture (the lazy mode is bypassed while the disk is on), host-visible entry buffers, the extra GPU to host copies. RX_VK_BC_DISK stays off by default; it is not worth shipping as it is.

## State at stop (2026-11-23 reboot)
- Done: code above, tests adjusted, committed on perf/bc7c. NOT compiled yet (no build ever ran: the build lease was granted just as the reboot stop came, killed at once and released).
- Next command: `T=$(bash build/s5/machine.sh request mainpc bc7c build 45 1)`, then `bash /e/OOT/scratch-bc7c/build.sh` (reads /e/OOT/scratch-bc7c/build_ticket: write the new ticket there first; runs mkg.ps1 -Root E:/OOT/HeyListen-wt/bc7c/engine -Name bc7c -Block -Lift -Pgo ... -Owner bc7c; output build/s5/bin/bc7c). Fix compile errors in vk_texture.cpp / vk_bc_disk.h first.
- Then: speed lease, copy the build as foot1_tour.sh does (slot c), runs with HL_HITCH_LOG=rel:8 RX_VK_BC_AUDIT=300 RX_VK_PASS_TIMING=1, arms: RX_VK_BC_DISK=0 / =1 cold / =1 warm with RX_VK_BC_DISK_DIR=E:\OOT\scratch-bc7c\cache; audit in Market, Kokiri, Field; screenshots against off.
- Leases in use: none now. Scratch: E:\OOT\scratch-bc7c (build.sh, build_ticket, tmp).
