<!-- Copyright (C) 2026 Sacrappy -->
# LOCK1: the lock-on pointer triangles (issue #89, 24 Nov 2026)

Branch `fix/lockon-89` from origin/main (0e5db2102). Main PC (RTX 5070). Save `kokiri-dummy` (child Link in front of the Kokiri Forest
training dummy). Scene `kokiri-idle`, title skipped, `HL_INPUT_SCRIPT=0:B,0:ZL/14000` (inputs count from "play: began").

## LOCK4 state (25 Nov: CAUSE FOUND, fix written, NOT yet proven in the game: no build left in LOCK4's budget)

**The cause: the write-back's diff pass (gpu/vk/shaders/wb_diff.comp) wrote a whole subgroup span (32 vectors, 512 bytes) from the
mirror to guest memory whenever ANY vector of the span differed.** The ring's pool holds 256-byte elements; the compute program
15e70c016d50a89c updates the fields of the live elements (0 and 2 here) every frame, so the 512-byte span around them differs every
frame, and the unchanged vector next to it, element 1's (or 3's) position at +16, went back too with the mirror's older contents (the
game's 0x6f fill) over the CPU's store. The game's stores, the job order and the renderer's mirror were all right; LOCK3's "stores
of the fill" were the guest memory read back after the loss (its watch cannot see a GPU write through imported memory).

- **Probe** (not committed: E:/OOT/scratch-lock4/hl_lock4.c, entry gates on f_812618c0, f_8128d140 and f_812f0fc0 that never answer, plus
  E:/OOT/scratch-lock4/lock4-gates-hack.patch for an empty hash; build lock4b, gone to save disk): every call of the setter for element
  < 4, field +16, stride 256 is logged with its four floats, what the memory held, the node's and the system's blobs and the call chain.
- **Every store the CPU made was valid, in every run, with every input valid** (no fill in the matrices of any node call; the
  pointer is spawned one element at a time by the same node x0 in successive frames, from jobs on different workers, chain
  f_8128bc5c <- f_8125f520 <- f_81270a04 <- f_81270710 <- f_8007f660): build/s5/c3/game_log.txt (E-EE) and build/s5/c5/game_log.txt
  (E-E-). No job-order, fence or scheduling fault exists; candidates (a) and (b) of the brief are refuted, (c) too (the host never writes 0x6f).
- **Then the memory reverts at the next write-back that comes before the next mirror sync.** `bash E:/OOT/scratch-lock4/tl.sh c5
  10386bfc00` (ms clock; SET = the game's store, PROBE = the draw's read of guest memory, wb / sync = the renderer's ring-page
  write-back and mirror sync): e1 SET 85657436, PROBE sees it 85657441, wb 85657444, PROBE 85657487 sees the fill; e3 SET 85657531,
  PROBE 85657533, wb 85657534, PROBE 85657721 the fill; e2 SET 85657492 comes after the wb and the next sync (85657507) takes it into
  the mirror: it survives. In c3 (`tl.sh c3 10386d3300`): e1 SET 85403223, wb 85403227, fill again at 85403262, e2 and e3 survive.
  A store made between a sync and the next write-back is lost when its 512-byte span holds a vector the GPU changed: which of the
  pointers is lost depends on the store's timing, hence E-E-, E-EE, EEE- and EEEE (with a watch the threads are slower and the order
  changes, 10 of 11 no-watch runs lose elements).
- **Fix**: the vector branch writes only the vectors that differ (`if (any(notEqual(v, s.v[i]))) { g.v[i] = v; s.v[i] = v; }`), the
  vote and its capability check in wbd_pipe_ready are gone; wb_diff_comp_spv.h regenerated with glslangValidator 1.4.363. Test:
  tests/test_wb_diff_exact.py (shader text, the compiled header has no vote op, a model of both rules). The cost to measure (not done):
  contiguous GPU writes coalesce as before, scattered ones go as 16-byte writes over PCIe.
- **General**: any CPU store into a 512-byte span of a mirrored pool next to a vector the GPU changes can be lost the same way
  (LOCK2's RX_VK_WB_SHADOW_SYNC keeps the shadow right, and stays: it fixes a different loss).
- **To prove (needs a build)**: census EEEE in 3 runs without any watch and 4 triangles in the pictures (save kokiri-dummy, input
  "0:B,4:ZL/14000", RX_VK_SHOTS), a tour, the suite. Test the fix against RX_VK_NO_WRITEBACK=1, which should also give EEEE.
- Disk: E: was at 100% (105 GB of builds in build/s5/bin) while this ran; a shader write failed with ENOSPC.

## LOCK3 state (25 Nov, NOT fixed; the write log narrows it to the game's CPU side)

Builds lock3b and lock3c (local probes, not committed: E:/OOT/scratch-lock3/lock3-probes.patch): HOS_WATCH with an event log (time, thread,
host place, three callers, the dword and the next three at the address, written after each store), a 5 ms poll so the data breakpoints are
armed within a frame of the ring's first draw (HOS_WATCH_POLL_MS), the ring probe on every draw for the first 300 draws with a millisecond
clock, and "lock3 sync/wb ring page" lines with the same clock. Logs: build/s5/<tag>/game_log.txt; scripts E:/OOT/scratch-lock3/*.sh.

- **The game's CPU stores each pointer once, from a job on a worker thread, and only at lock-on.** EEEE run, writes only (build/s5/l3e1):
  e1+16 stored at ms 74041337 by ModuleSystemWorker4 (f_812f0fc0+0x639 <- f_8128d140+0x462 <- f_812618c0+0x1816), e1+128 one ms later
  (f_812f0f60+0x475 <- f_812618c0+0x1bf4), e2+16 at +12 ms by Worker5, e3+16 at +166 ms by Worker1: one store per element, three
  different workers, presents 6770 to 6772. Nothing stores them again in the next 14 s.
- **In an E-E- run the stores of elements 1 and 3 either never come or carry the fill.** build/s5/l3c3 (E-EE): no store to e1 in 22 s
  after arming. build/s5/l3c5 (E-E-): the only store, e3+16 at ms 66304228 by Worker2 at the same place, writes 0x6f6f6f6f as the first
  float (the vec4's first component is the fill; the CPU's job computed it from an input that held the fill). 13 s later, at the end of
  the lock-on, the game's own memset (f_8572f300+0x33c <- f_812efb80+0x192) writes 0x6f over e1 and e2 (the pool is freed).
  So it is not a store that the renderer loses (LOCK2's lead is refuted again here): in guest memory the CPU's stores are the fill, or absent.
- **It is timing, not a switch.** No-watch runs: E-E- in 10 of 11 (build/s5/ab2def1, ab3def1, nw1, nw2, ab1off1, ab2off3, ab3off1, fp1f301,
  fp2f301, fp2f601; EEE- once, fp1f601). With the watch armed (slower threads): EEEE in l3c2 (27 samples) and l3e1 (349), E-EE in l3c3.
  HL_JOBS=0 HL_JOBGROUP=0 HL_DISPATCH=0 HL_DISPATCH_ALL=0 HL_MODSTAGES=0 HL_STAGES=0 HL_GFX=0 HL_MATH=0 HL_STREAM=0 (every native piece
  of the hybrid engine off) still gives E-E- (ab1off1, ab2off3, ab3off1), and HOS_FPS_MAX=30 or 60 gives no consistent change.
  HOS_CORES=1 and 2 did not reach the ring in 2 minutes (no answer).
- **Per frame, without the watch (build/s5/nw1, ms clock in the log):** e1 appears at present 6857 and is the fill again at 6859; e2 appears
  at 6860 and stays; e3 never. At two frames (6858 and 6869) the draw binds ANOTHER 16 KB pool (0x10384df400 instead of 0x10386d5800)
  that holds all four elements with plausible data (+248 = 0x1e, a 30-frame effect: the lock-on's own burst, a second user of the same program);
  those two samples are the only EEEE of the run. The ring probe's census mixes both pools: read it per address.
- **What is left:** (1) why the pointer jobs of elements 1 and 3 see the fill (they read a matrix in an object another job fills: a missing
  order between jobs that the console's scheduling hides?), or do not run; f_812618c0 (the effect node's update, one call per pointer),
  its vtable callee f_8128d140 (3x4 matrix product, then the setter) and the job that fills the node's inputs are the places to read;
  the watch recipe above (poll 5 ms, writes only, HOS_WATCH_ALL_THREADS=1 HOS_WATCH_STACK=1 HOS_WATCH_EVENTS=1) logs who stores what.
  (2) The rw phase of HOS_WATCH recurses in the event handler (it reads the watched address): read through ReadProcessMemory if it is used.
  (3) A per-element job trace (HOS_JOBTRACE) around the lock-on would show whether the e1 and e3 jobs run before the job that fills their inputs.

## LOCK2 summary (24 Nov, PAUSED by the coordinator for the usage budget: fix written, NOT proven in the game)

- **Proven (logs):** the game's CPU writes elements 1..3 itself: `f_812f0fc0+0x639` stores element 3's +16 (E:\OOT\scratch-lock2\
  watch5.out, run build/s5/lock2-r12, every thread armed, write phase only); in r9 (E:\OOT\scratch-lock2\watch4.out, guest
  threads, read/write phase) it reached e1, e2 and e3, yet e1 held 0x6f6f6f6f at the end ("watch: ... holds ... at the end"
  lines in build/s5/lock2-r9/game_log.txt): a store that is **lost** afterwards. Which elements survive changes run to run
  (`bash E:/OOT/scratch-lock2/ring.sh <tag>`: r5 E---, r9 E--E/E-EE, r11 EE-E, r12 E---/E--E, r14 E-E-).
- **Not the cause (tried):** no buffer-to-buffer copy touches the pool (RX_VK_WATCH_RANGE, r11); RX_VK_WB_LAZY=0
  RX_VK_WB_POOL_EAGER=0 RX_VK_WB_SMALL_EAGER_KB=0 still loses them (r14). RX_VK_WB_DIFF=0 (r13, r15) and RX_VK_NO_WRITEBACK=1
  (r16) gave no answer (the runs did not reach play within the 120 s limit). The crash3f build was not tried.
- **Hypothesis (not yet proven in the game):** the write-back's diff refills a page the CPU wrote from guest memory after the
  GPU's work, so a CPU store made after the mirror's sync differs from the mirror and the mirror's older 0x6f goes back over
  it (details in the State below). The fix (vk_memory.cpp shadow_sync_copies / wb_shadow_sync_on, RX_VK_WB_SHADOW_SYNC on by
  default, =0 off) and its test (tests/test_wb_shadow_sync.py, passes) are committed as work in progress.
- **Next step, exactly:** take a slot, put build/s5/bin/lock2y in it (the fix + local logs "vk: lock2 sync ring page" / "vk:
  lock2 wb ring page" + LOCK1's ring probe; built from the tree before the last test fix, which only moved one line), and run
  `bash E:/OOT/scratch-lock2/go.sh <tag> lock2y "0:B,4:ZL/14000" RX_VK_SHOTS=E:/OOT/scratch-lock2/<shots> RX_VK_SHOT_EVERY=20`
  2 to 3 times until a run reaches play (caches), then once more as the "after" and once with RX_VK_WB_SHADOW_SYNC=0 as the
  "before"; `bash ring.sh <tag>` must show EEEE with the fix, and E:\OOT\scratch-lock1\count.py counts the blobs in the shots.
  The lock2 log lines tell whether the ring's page is on the diff path (shadow yes, known 0 = refilled) before the fix.
  If the fix does not give EEEE: the write-back loop's whole copies (no shadow) or the late-page path are the next suspects.
- **Reuse:** builds build/s5/bin/lock2x (logs + watch, no fix) and lock2y (fix + logs); maps of their dlls in
  E:\OOT\scratch-lock2\hookshot_vk.lock2{x,y}.map; the local probes (not committed) in E:\OOT\scratch-lock2\probe-src\
  (vk_draw.cpp: ring probe, LOCK2_WATCH=<file> arms HOS_WATCH on the pool it sees; vk_memory.cpp: the lock2 logs) and
  E:\OOT\scratch-lock2\lock2-all-1.patch; save build/s5/savelib/kokiri-dummy; scripts go.sh, run.sh, ring.sh, resolve2.py in
  E:\OOT\scratch-lock2. The pool's address is not fixed (0x10386c6b00, 0x10386bd200, 0x10386d5700, 0x10386c5000 seen).
- **General or ring-only:** if the hypothesis holds it is general: any CPU store into a page of a mirrored, shadowed pool that a
  GPU program also writes can be lost the same way (other GPU particle emitters, CPU-reset counters beside GPU data). Not
  checked on another case yet. Tests: run_all 509 passed, 4 failed (the 3 known + test_vertex_bind, which my line broke and
  which passes after the fix in the commit).

## LOCK2 state (24 Nov, step by step)

- Took over the worktree; merged main (0e23349ea). Scratch: E:\OOT\scratch-lock2.
- Step 1 (who stores to the pool): HOS_WATCH (host/mkw_glue.c, hardware data breakpoints on guest threads) given a short
  caller stack (HOS_WATCH_STACK=1) and a phase length (HOS_WATCH_SECONDS); build lock2x with LOCK1's local probes applied
  (not committed). Plan: ZL at 6 s from play, watch e0..e3 +16 of the pool 0x10386c6b00 from ~4.5 s.
- Run lock2-r1 (build/s5/lock2-r1/game_log.txt): the pool was at 0x10386bd200 this time (the address is NOT fixed from
  run to run), so the watch saw only the game's 0x6f fill (f_8572f300, a memset, from f_812efb80) at the old address. The
  ring probe there: e0 live before the lock-on, and at lock-on e2 became live as well (e1, e3 stayed 0x6f6f6f6f): which
  elements are lost changes from run to run. Next: the probe arms the watch itself on the pool it sees (LOCK2_WATCH=<file>).
- Runs r5, r9 (probe-armed watch, guest threads only): the pool is at 0x10386c6b00 (r5), 0x10386d5700 (r8, r9). In r9 (two
  lock-ons, 4 s and 10 s) e2 and e3 +16 went from 0x6f6f6f6f to floats (3f03f75a, 3ed92a7f) during the watch, but NO guest
  thread stored there (the write phase saw nothing; the read/write phase only f_812f0fc0, a reader of all four called from
  f_8128d140, and nvn_gpu_read's memcpy). So the words that do arrive in elements 1..3 are put there by a thread that is
  not a guest thread (the renderer: a write-back from its mirror) or through another mapping. r5: the pool freed after the
  lock-on (f_8572f300 memset from f_812efb80 at the end of the watch).
- Next: HOS_WATCH_ALL_THREADS=1 (every thread), HOS_WATCH_PHASES=w.
- **The writer** (r12, every thread, write phase only): `f_812f0fc0+0x639` stores element 3's +16 (called from f_8128d140 through
  a64_icall_site, from f_812618c0). f_812f0fc0(x0 = the pool's descriptor {base +0, stride +16, dirty lo/hi +32}, x1+8 = the
  field's offset, w2 = the element, s0..s3 = the value) is "set a vec4 field of element i if it changed": it compares the four
  floats with memory, stores them (stp, stp) when any differs and widens the descriptor's dirty element range. So the game's
  CPU code does write elements 1..3 itself, one by one (r9: its stores reached e1, e2 and e3 in the read/write phase, yet e1
  held 0x6f6f6f6f again at the end: **a lost store**).
- The probe's census of e0..e3 (E = data, - = fill) shows which ones survive changes run to run: r5 E---, r9 E--E/E-EE, r11
  EE-E, r12 E---/E--E, r14 E-E-. No B2B copy touches the pool (RX_VK_WATCH_RANGE, r11).
- Switches: RX_VK_WB_LAZY=0 RX_VK_WB_POOL_EAGER=0 RX_VK_WB_SMALL_EAGER_KB=0 (r14): still lost (E-E-). RX_VK_WB_DIFF=0 (r13, r15)
  and RX_VK_NO_WRITEBACK=1 (r16): the runs did not reach play in time (no answer).
- Lead (to prove next): the write-back's diff (vk_memory.cpp, the write-back loop: "the pages of the runs the shadow does not
  know: from guest memory, whole, first") refills a page the CPU wrote (shadows_forget_written) from guest memory as it is
  when the GPU runs the copy, after the compute: the CPU's newer words (e1's, stored after the mirror's sync) are then in the
  shadow, the mirror still has 0x6f there, the words differ and the pass writes the mirror's 0x6f over the CPU's store. The
  WBL1 comment in the same loop names this very race for its flush pages.
- Fix written (not yet proven in the game): vk_memory.cpp shadow_sync_copies + wb_shadow_sync_on (RX_VK_WB_SHADOW_SYNC, on by
  default, =0 off): a mirror sync makes its copies into the shadow too and a mirrored pool's pages stay known, so the shadow is
  the mirror as the GPU found it and only the GPU's words differ. Test: tests/test_wb_shadow_sync.py (passes). Build lock2y
  = the fix + local logs ("vk: lock2 sync ring page", "vk: lock2 wb ring page") + LOCK1's probes. Next: A/B in the game,
  RX_VK_WB_SHADOW_SYNC=0 vs default, ring census + blob count.

## LOCK1 state (24 Nov, end of the session: NOT fixed, cause narrowed)

- **Reproduced.** While ZL is held the ring around the dummy shows 1 or 2 pointer triangles (two at most, opposite each other) instead of the
  full ring. A counter over the shots (pink blobs near the target) gives 1 in about 55% and 2 in about 15% of the locked frames, never 3 or 4,
  in 6 runs.
- **The triangles are one draw**: program `13afdae0385d7afe` (vertex 1837 IR lines), `prim 4, count 210, inst 4, bi 0`, in the scene pass
  before the post-processing. `RX_VK_SKIP_PROG=53509044401d78d2,13afdae0385d7afe` removes every triangle, so it is the whole ring. Before the
  lock-on the same program draws `inst 1` (Navi's target arrow).
- **No draw is left out** ("0 skipped", "0.0 draws left out (not ready)"), no instance count, divisor or base-instance fault: the vertex streams
  are all `divisor 0` and the instance index only selects a table entry.
- **Where the per-instance data comes from** (vertex IR): `InstanceId` -> `sb2[inst*16]` (the table `0,1,2,3`, right) -> element `i` of a
  64-element, 256-byte-stride pool (`sb1`, 16 KB, at the same guest address every frame) -> position/orientation at element+16.., fields at
  +128..+168 and +236/+244. A compute program (`15e70c016d50a89c`, 64 invocations a group, one group, thread `i` = element `i`) updates the
  pool in place (it writes +128..+168 and +244 only; it reads +236).
- **Elements 1..3 of that pool are never initialised in the replay**: a probe on the draw (every 10th draw over 20 s of lock-on) reads the
  four elements from guest memory: element 0 is a valid matrix (the same every frame, Link standing still), elements 1, 2 and 3 are
  `0x6f6f6f6f` (the game's fill) in all 47 samples. The GPU copy of the pool is the same before the compute, after it and at the draw
  (hashes equal, `RX_VK_DUMP_SSBO` before/after), so the compute leaves them alone as well (it only touches an element that is live). The
  uniform buffer the draw and the compute read (c11, 464 bytes) holds the matrices for the instances correctly (4 matrices with the ring's
  rotation), so the CPU did compute the ring.
- So the renderer draws what its memory holds: one live element. **Open question for the next step: who writes elements 1..3 on the console?**
  The candidates, not yet separated: (a) the game's CPU code (a spawn loop for the four pointers: a lifter/native-engine bug would give
  exactly "element 0 only"), (b) a GPU copy/spawn command the replay drops or truncates (no buffer-to-buffer copy touching the pool was seen
  in the frame's dump), (c) the mirror sync overwriting GPU-written elements with the CPU's page (`RX_VK_MSYNC_DIFF=2` does not change the
  picture, so not just that).
- Switches tried on the picture (no change, still 1-2 triangles): `RX_VK_PARALLEL=0`, `RX_VK_GAME_ORDER=0`, `RX_VK_MSYNC_DIFF=2`.
  Skipping the compute `15e70c016d50a89c` removes the second triangle (1 left in all frames), so the compute does contribute.
- Next step: watch writes to the pool's page from the guest side (the `A64_WRITE_TRACK` build or the write-history in
  `gpu_write_history.h`) from lock-on start, to see whether the game ever stores to elements 1..3; if it does, the loss is in the
  write path; if it does not, find the emitter function and its loop count (a lifter fault would also show on the CPU side).

## How to reproduce

`build/s5run.sh --save build/s5/savelib/kokiri-dummy <tag> kokiri-idle HL_INPUT_SCRIPT=0:B,0:ZL/14000 RX_VK_SHOTS=<dir on E:> RX_VK_SHOT_EVERY=20`
with the bench run in title-skip mode (`run_bench.py --title skip`) and the slot's `slot_02/progress.sav` touched so it is the newest
save (the title skip loads the newest one; `cp -r` does not keep the times, so slot b picked `slot_00`). A run needs about 60 s to reach
play on this PC when it is quiet and 90 s when it is not; a new exe needs two or three runs first (shader and pipeline caches).
