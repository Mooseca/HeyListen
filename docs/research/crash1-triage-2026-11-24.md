# CRASH1: triage of the v0.4.3 crash reports, 22-24 Nov 2026

Analysis only (no game run, no build). Sources: the issues #125, #126, #129, #131, #132 (read-only), the logs and
report the reporters attached, the automatic reports in #55 (81 comments, 181 reports: v0.4.1 27, v0.4.2 105,
v0.4.3 49), the lifted C of the build on the main PC (function names and offsets only here, no game code), and the
sources on origin/main (0e5db2102, 223 commits after v0.4.3).

Reading the crash records: `f_X+0xN` in a host frame is a byte offset in the compiled function (not a guest offset); the
guest frames (`lr 0x... f_X+0x..`) are guest offsets. A host address of 0x1000_0000_0000 + g is guest g, so a fault at
host 0xfffffffffff is guest -1 and one at 0x100000000090 is a null pointer plus 0x90. The local .map belongs to another
build (other function layout), so host offsets could not be turned into lines; the register dumps and guest frames were
used instead.

## Verdicts

| Issue | Crash | Verdict | Confidence |
|---|---|---|---|
| #125 | FATAL call to 0x80000008 at the title, 3 of 3 starts, also with HL_GFX=0 | A virtual call on an object that is not what the game expects, in a build that carries an exeFS code mod; not the HL_GFX natives | likely (class of cause), the exact cause unknown |
| #126 | read at guest -1 in f_803b44e0 (a heap's free), Fire Temple, 5378 s | A free of a block whose heap header is bad (double free, free of a stale block or a heap overrun): game memory corruption. Not one of our gates (the only gate on it is the recorder's, off by default) | likely, trigger unknown |
| #126 (2 more) / #129 | DMC adult, no record (or a crash at loading); #129 closes at Continue after death, 13927 s | The same family as #126 where a record exists; for #129 unknown (no log yet) | unknown |
| #131 | no crash record, leaving Market_Adult while loading, 3.5 h, AMD RX 9060 XT | Ended from outside: no memory shortage visible in the tail; AMD driver or the OS most likely | unknown |
| #132 | write at guest -1 in f_83bb8420 (+0x7b), SceneLowPriority, 1154 s | A string/buffer object with a null buffer pointer and zero length handed to a string function that writes its terminator at end-1 | cause of the fault found, the origin of the empty object unknown |

## What #55 says (v0.4.3, 49 reports)

- **The heap/destroy family is 20 of 49 (41 %)** (v0.4.2: 9 of 105, 9 %): crashes at f_80a30a00 (11: +0x1ef x8, +0x376,
  +0x37e, +0x69), f_80a31030 (4: +0x550 x2, +0x710 x2), f_803b44e0+0x607 (5), f_834bdb90+0x89 (1) (+0x100ba of
  f_80587c80 not counted). Same host callers every time (the host offsets 0xfe958ea, 0x475442e, 0x474861b are the
  chain f_80a31030, f_80a31220, f_82c20a40) and always on a ModuleSystemWorker thread. The faults are loads or stores at
  a small offset from a null object (guest 0x8, 0x10, 0x38, 0x90) or at -1, i.e. a destroyed or never made object.
  Maps: DeathMountainCrater_Adult 8 (+2 in v0.4.2), SpiritTemple 7, Dodongo's Cavern 3, Fire Temple 1 (+7 in
  v0.4.2), PhantomGanonStage 1, FinalBattleField 1. Fire and desert maps; adult in 12 of 20. GPUs: NVIDIA only
  (RTX 2060 to 5070 Ti, 8 to 62 GB), so not an AMD, driver or low RAM matter.
- **f_83bb8420+0x7b: 3 reports**, all DeathMountainCrater_Adult (RTX 3050 OEM, 8 GB), plus #132 (Gerudo thief stage,
  16 GB) not yet counted there. Same host address, so the same build (lifted code 7a90fd06b3).
- **Title and intro: 10 of 49** in v0.4.3 with many different sites (f_8572f300 x4, f_80a9e750, f_83b51a00,
  f_80a9f3c0, igvk64 x2, KERNELBASE); in v0.4.2 the two biggest clusters (34 + 15) are title crashes too. The #125
  FATAL text (call to an address with no function) appears nowhere else in #55 (no FATAL line is kept there at all),
  so #125 is a one-off or a rare path; the 0x80000008 value is in no other report.
- The lifted-code keys: 7a90fd06b3 in 51 reports, d10f97a7db 4, d78ffe35b5 2 (the WaterTemple family f_804fc320
  x6 is one of those: builds with a code mod or another game version), and #125's 3df8cd792e is not among them: its
  build differs from the standard one.

## #125: title, call to 0x80000008

**Log.** The run reaches the title and is quiet for about 3 minutes (4420 lines). Then the first native graphics lines
(HL_GFX_PREP, _PREP_STATE, _REC, _STATE, "the native recording pass (NVN procedures tapped: 0)") appear in the last 8
lines before the FATAL: that is the first time the title's 3D scene is drawn, and the lines are written at the first use
of each native, so they are the neighbours of the crash in time, not its cause. The run with HL_GFX=0 (125b) crashed at
the identical place (same lr, same backtrace) on sead::MainThread instead of ModuleSystemWorker1 (the first crash was
ModuleSystemWorker1), so the crash does not depend on the thread or on HL_GFX. The log ends with no memory notes:
RTX 4050 laptop, 16 GB, 9809 MB for the game, 6894 MB heap; nothing out of memory, no map load, no stalls (10 fps in
the shader-precompile phase at the start, 60 fps when the crash comes).

**The guest code.** f_8025dae0 (559 lines of lifted code) is a function a guest caller (f_809f2f10, through a table of
object pointers) reaches directly when the object's vtable entry is f_8025dae0. At its end it walks 8 object slots in
its argument (+0x28 to +0x60), and for the last non-empty slot takes a lock word at +216 (an atomic OR of bit 31), and
if the old value shows other users it calls a virtual function of the slot's object (vtable +24) with the old lock value
as argument. The call that failed is that one (lr 0x8025deac).

The registers (the dump is in the report) show: the slot's object (x21 and x0) is at 0x100754e350, an address inside
ModuleSystemWorker1's own stack, and the lock word was 8 before the OR; the argument of the virtual function (x1) is 8.
The target, 0x80000008, is exactly the lock word after the OR (0x80000000 | 8). So the vtable pointer read from the
object was not a vtable: it pointed 24 bytes before the object's own lock word, i.e. the object was never an object with
a vtable but a memory block at that stack address (a stack object of another type, or a dead one whose bytes have been
reused). The function's own argument (x0 of f_8025dae0, also at a stack address, 0x100754e280, below the caller's frame)
points the same way: the caller reached this function with a pointer to dead or foreign stack memory in its object table.
So "image base + 8" is not a function pointer that was relocated badly: it is the number the lock code writes, read back
as a pointer.

**Whose code.** Plain lifted game code (f_8025dae0 and its five callers up to f_802a28d0 are in no gate, no hl::
module and no oot_patches edit: grep of engine/ finds none of them; the gfx units named in the notes are 0x80077d60 and
its neighbours). The natives that were on in the run (HL_GFX_PREP, _PREP_STATE, _REC, _STATE) write NVN command
records for the render state and do not touch the guest object tables of the module system.

**What is different about this player.** The log has `hl: exeFS mods patch the game's code (17187 entries in
hookshot_code_patches.txt)`, the mod "Fast Travel (Visited Patch)", and the lifted-code key 3df8cd792e instead of the
standard 7a90fd06b3: this game was built with Code mods. No other reporter of the five issues has that, and the player
says it worked in v0.4.2 (so with a v0.4.2 build of the same mod, presumably). With a code mod the engine leaves every
native gate and step hook out of the patched functions, and the lifted text differs, so the same game runs with
different code paths and a different stack layout than in the 51 standard reports; a mod patch (17187 changed ranges is
a lot for a fast-travel patch) that misplaces bytes, or one written for another game version, could leave a stale or
wrong object in that table. Not proven: I had neither the mod nor hookshot_code_patches.txt.

**Why v0.4.3 and not v0.4.2.** Between the two tags oot_patches.py gained the voice-option, scene-format and four
above-60-fps edits, none near these functions; hl_gates and exefs_mods did not change. The change that makes the
difference for this build is likely the lift itself (every build is lifted again for a new version, and with a changed
lifted text the patched layout moves), not a native.

## #126 and #129: the Fire Temple and the Crater

**#126's crash (report and logs in the zip; folder `E:\OOT\scratch-issues\126zip`).** Fire Temple, 5378 s,
ModuleSystemWorker1, read at guest 0xffffefffffffffff (host -1). The guest chain: f_803b44e0 (frame 0, lr +0x94),
f_80a31030, f_80a31220, f_82c20a40, f_83b78d80, then the job loop (host frames: hl_gate_8007fe60, bridge JobGroup,
run_job). f_803b44e0 is a heap class's virtual `free(heap, block)`: the recorder (engine/host/hl_trace.c) lists it
among the heaps' free functions. It takes the heap's lock when the heap's flag word says it is thread safe, reads the
block's header at block-8, finds the chunk, compares the header's 16-bit tag with the heap's, unlinks the chunk from a
list (two neighbour pointers) and goes on to coalescing. The faulting load is late in the function (host +0x607) and
reads a neighbour pointer that is -1: a chunk header that is not the one the heap made. The registers: block
0x117e722058, heap 0x1178800960 (both in the normal heap range), x22 = 0x90 and x25 = -144 left in the caller's registers (a
144-byte object is likely, not established). So: a free of a block that was already freed (its header is a free-list entry or overwritten), or
of a block that does not belong to this heap, or after a neighbour's overrun.

The caller f_80a31030 and its sibling f_80a30a00 (a recursive destroy that also frees through f_8021dea0, the game's
free by address, and takes and releases a lock, f_851047f0 and f_851048a0) are the destroy path for a collection of
objects called from the module system's job (f_83b78d80). The other 15 reports of the family die in the same functions
a little earlier, on a null or -1 object, i.e. at the object being destroyed or at its owner: the same bug seen at
different points (an object destroyed twice, or destroyed while another job is still using it), not different bugs.

**Triggers.** #126's log: the run walked DMTrail, Goron City, DMC, Fire Temple; the crash comes about 6000 lines after
the last map line (Fire Temple), while the module jobs run; ImInSpace's two DMC crashes: right after the Sheik scene
and walking toward the Fire Temple passage, and loading the Crater after the Bolero warp (the game was at 2-3 fps
before, which the log of the clean run in the zip also shows once: 9.6 fps at one point, the only one under 20). The
other zip log (hookshot.log, the clean run) went DMC <-> Fire Temple 8 times and was closed by the player, so neither
the map pair nor the Bolero warp crashes every time. #129 (3.9 h, Continue after dying in the Crater) is the same
load of the same map, with no record and no log yet. Common to #126, #129 and the rest of the family: a map load or
unload with several module jobs destroying objects of the old map, in fire/desert dungeons and the Crater, hours into
a session (1154 s to 13927 s), on every GPU vendor of the family (NVIDIA only in #55), with 8 to 62 GB RAM.

**What we do around it.** The jobs run through our job group natives (HL_JOBGROUP, HL_MODSTAGES: "mode 1, 6 workers"
in the log): the guest module jobs run on pool workers where the Switch ran them on fixed cores, so a destroy that is
safe by the game's own timing may run beside the user of the object. This is a hypothesis; v0.4.2 had the same natives
and the same family at 9 of 105, so the natives alone do not explain the jump to 41 %: more players are in the late
game maps since 0.4.3 (the family needs Crater, Spirit, Fire), which fits 8 of 20 in the Crater, and the v0.4.3 reports
come in a few days. Also in play, and old: the heap retry of hl_heap_retry.c moves an OptimizeChangeBank allocation to a
parent heap when the model's heap is full (304 and 384 blocks in the two zip logs, so it happens in the clean run too);
the free path walks the heap tree for the owner, so it is correct by its notes, but a block that goes back to the wrong
heap would give exactly this header. The clean run having more moves than the crashing one argues against it as the
cause.

**Since v0.4.3.** main did not touch hl_jobs.c, hl_heap_retry.c or the destroy functions' gates. It changed what
could matter: HL_REGION_KEEP (a freed address region stays resident, a region allocated over it is zeroed in place),
cold-page holds (HL_MEM_COLD_LOWMEM), the OptimizeChangeBank hold (HOS_OCB_HOLD_MS, which cuts map reloads in
the market only) and the lifter's new default options (native float, local registers), which change every function's
code. None is a fix of this bug.

## #131: ended without a record, Market_Adult, AMD

The record says: no crash handler observed, ended from outside or lost power. Process started 16:28, ended 19:58 (3.5 h),
log 62 MB. The tail shows a normal run with no memory notes at all: 34.9 fps, a load in progress (uploads of 150-190 ms a
frame, "51 new ASTC textures held back"), 1000 textures (2121 MB) live, the same 240 MB pool imported 1280 times
(0.0 ms each, harmless counts), and two small host pools not imported: `VkResult -1000072003`
(VK_ERROR_INVALID_EXTERNAL_HANDLE) on pool 0x7f4a826c00 and the earlier one; these are import refusals the engine
survives (it logs them and goes on). RAM 32 GB, i5-14600KF. There is no "out of memory" line, no device-lost line, and
the log ends mid-activity, not with "window closed, exiting". For #55 the AMD records are a few driver crashes
(amdvlk64 x6 in v0.4.2). A hard stop without a record points to the driver or the OS (TDR with the process killed,
a fast-fail) more than to a lack of memory, but the log cannot say. Unknown until the Windows event log or the whole report is in.

## #132: Gerudo thief stage

f_83bb8420 takes an object (x1) with a pointer at +56 and a 32-bit length at +64 (a string or buffer view), writes a zero
byte at pointer + length - 1 (the terminator at the end of the buffer), then compares the string with a constant one
byte by byte and, on equality, makes a call through the first object's table (+216 slot, vtable +8); it is a
string function reached through icall from f_8329e940, in the resource lookup chain of f_80e7c590 and f_80c62200,
where the name searched is "Drop/DropTable/DropTable_Obj_Fairy" (the fairy drop table: the bytes at x24 are that path;
not our drop module: hl_drop.c is the cold-memory drop of decoded files, off by default, and unrelated).
The write at guest -1 means pointer 0 and length 0: a string object that is all zero, made by memory that was cleared
(an object freed and zeroed, a block never filled, or a page given back and read as zero). The object at x24 itself is
intact (its path is there), so the bad one is its sibling argument. Our memory features that can give a zero page back
to the guest are the "zero pages of pools without CPU access" (the log shows 387 MB given back) and the cold-page and
region-keep paths; they are designed to touch no memory the CPU reads, and the log has nothing to show a fault. 3 of 4
reports of this function are in the Crater and #132 is a new map, so the function is not map specific; the cause of the
empty object is unknown. The thread SceneLowPriority loads resources in the background, and the log's last lines show
the vcores watcher: a worker was held 7.9 s waiting for a core by SceneLowPriority (other threads waited 2 s). At 22
fps and an interval of 1 at the end, the PC was running behind: a slow background load makes a half-built object
likelier to be seen, but it is a guess.

## Next steps, ranked

1. **Catch #126's family with the recorder.** HL_TRACE=2 (hookshot_env.txt: `HL_TRACE=2`) records every heap
   allocation and free with the caller chain and, at the crash, says whether the faulting address or a register is in a
   live or a freed block, who allocated and freed it, and the last 200 events of the thread: that distinguishes a double
   free from a dead object from an overrun at once. Reproduce on a save with the adult Link at the Crater and loop:
   Crater -> Fire Temple door -> Bolero of Fire to the Crater -> Goron City -> Crater, 20 rounds, and Crater ->
   Spirit Temple loop; use the 8 GB/RTX 3050 setting if a PC with that exists (the f_83bb8420 reports are 8 GB, the
   others any). If it never reproduces locally, ask ImInSpace to run with HL_TRACE=2.
2. **#125: build without the Code mods option** (or ask the player to) and see if the title passes; ask for
   hookshot_code_patches.txt, the mod's .pchtxt/.ips and the game version it was made for. Locally: build with a small
   mod that patches a few bytes and run the title for 4 minutes; then a patch of the same size class (several thousand
   ranges). If the title passes with a clean build, the cause is the patch/lift pairing, and the builder should refuse or
   warn on a mod whose ranges exceed a small number or fall in the module system's objects.
3. **Run the family under the job twins off**: HL_JOBGROUP=0 HL_MODSTAGES=0 on the loop of 1 (the guest jobs on their
   own stage); if the crash stops, the pool workers expose a race of the original; if it stays, the cause is in the game.
4. **#129, #131: logs first.** For #129 the whole hookshot_log.txt from before the next start; for #131 the Windows event
   log around 19:58 (Application, event 1000/1001; System, display driver events: "stopped responding", amdkmdag
   LiveKernelEvent 141/117) and the whole report; both: how much page file and free RAM; set `HL_MEM_ACCOUNT=60` for a log
   line of commit and working set every minute, which would show a leak before a long run ends.
5. **#132**: ask for the whole report and the log (the x24 and the other registers), whether it happens again at that
   place (the title of the issue says: returning from the dreams room), and whether it
   reproduces with `HOS_NOACCESS_RAM=0` (the zero pages given back off).
6. Add to the report writer: the guest registers in the issue text and the lifted-code key; in #55 add FATAL lines and
   the lifted code so a mod-patched build is visible at once.

## Draft replies (first person)

**#125**
> The game calls a function through a pointer that holds 0x80000008, and that happens on its own code, not in the
> graphics path (HL_GFX=0 gave the same crash). Your log shows a game built with a code mod ("Fast Travel (Visited
> Patch)"), which no other report has, so I would like to see whether it matters. Could you attach `hookshot_code_patches.txt`
> from the game folder and the mod's file, and try the game once with the mod removed and the build made without the Code
> mods option? If it starts then, I know where to look.

**#126**
> The report and logs helped: the Fire Temple crash is the game freeing a block whose memory header is wrong (a block freed
> twice, or one that was already gone), while it unloads a map. It is the same function chain as 20 other reports from
> the Crater, the Spirit Temple and Dodongo's Cavern. I am trying to catch it with the memory recorder; if I send you a
> test, would you run it and play the same route? Your clean log shows the same map pair 8 times without a crash, so it
> needs a particular order of loads.

**#129**
> Thanks for the report. The Crater is the map with the most crashes of this kind after the Fire Temple, and your Continue
> after dying is another map load there. The crash window gave no place, so I cannot say more without `hookshot_log.txt`:
> please copy it from the game's `logs` folder before you start the game again, and tell me whether Continue closes
> the game each time or once.

**#131**
> The game ended with no crash record, which means it was stopped from outside the game (the driver, or Windows), and the log
> before it shows no memory problem. Could you look in the Windows Event Viewer (Windows Logs, Application and System)
> around 19:58 on 23 Nov for an error about HeyListen or about the display driver ("stopped responding"), and attach the
> whole report and `hookshot_log.txt`? Does it happen again when you leave the Market?

**#132**
> The game wrote a zero byte at the address just before the start of memory, in a function that works on a name
> (the log shows the fairy drop table's path), so a name object was empty when it was used. It is the same function that
> crashed three other players in the Crater, now on another map. I cannot tell yet what makes the object empty; could you
> attach the whole report and `hookshot_log.txt`, and tell me if it happens again at that place (coming back from the dream
> room)?
