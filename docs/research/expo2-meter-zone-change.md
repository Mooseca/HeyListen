<!-- Copyright (C) 2026 Sacrappy -->
# EXPO2: the exposure meter after a zone change on main (24 Nov 2026)

Owner: EXPO2, branch `fix/expo2` (worktree `E:\OOT\HeyListen-wt\expo2`, from origin/main `0e5db2102`, which carries EXPO1's
`1aacae5ea`). Scratch: `E:\OOT\scratch-expo2`. Builds: `build/s5/bin/expo2a` (= origin/main, 461 s, built under lease `expo2`).

## Answer (final summary)

**No: on current main the exposure meter does not freeze after a zone change.** Three default warp tours on origin/main `0e5db2102`
(`build/s5/bin/expo2a`) give 0-4 reads given the last result again in a 2000-read window (sums 5, 10 and 12 held reads over 7, 12 and
11 windows), with 0 flashes; the ring serves the new zone's sums two frames old (0 waits for the GPU) one or two reads after each
change. The trigger EXPO1 found is still there and fires at every zone change: 35 real drops of the ring's ranges (the two meter
blocks, the 0xc0 companion and an R3 block) in the three tours. What is new since PIPE2 is EXPO1's fix: PIPE2's build `pipe2e` does
not contain `1aacae5ea`, so its section 6 measured the pre-fix freeze.

The counterfactual on the same build closes it: with `HL_RB_LAG_KEEP=0` (the old staging) and each meter block's binding sent to guest
memory directly every 1500 frames, the freeze returns in full (M = 1744 then 1995-2000 in every window, 24 "read zero 600 times in a
row" rows); with the fix the same injections are followed by 42 take-overs and M stays 0-12. **No code change was needed for this
brief.**

## State (last edit 24 Nov 03:44, done)

Where it stands: **done.** Six runs on `expo2a` (origin/main): four tours of the 4-warp route (three default, one `HL_RB_LAG_KEEP=0`)
and the two injection arms (`HL_RB_TEST_DIRECT=12000:1500`, default against `KEEP=0`). Nothing of this stream is running or leased: the
last slot lease (`20261124-021044-expo2-slot-2fd9`) was released by `tour.sh` at 03:41:38 and slot a's own exe/dll are back
(`bak-a` matches). Builds and logs: `build/s5/bin/expo2a`, runs `build/s5/expo2a-{t2,t3,t4,k0,d1,kd1}`, summaries
`E:\OOT\scratch-expo2\*.run`, scripts `E:\OOT\scratch-expo2\{build,tour,tour_full,tour_live}.sh`, `zones.py`, `meter.py`,
`shots_by_zone.py`, `luma.py`, shots `E:\OOT\scratch-expo2\shots\expo2a-*`, tests `E:\OOT\scratch-expo2\tests-main.log`.

Tests (main worktree, `python -I -B tests/run_all.py` from `engine/`, llvm-mingw first on PATH): 504 passed, 3 failed, 53 skipped; the
failures are the known environmental ones (`nx2/test_nup_paths.py`, `nx2/test_nup_read_name.py`, `tests/test_renderer_new_handler.py`).

Not done: the long FOOT1 route (`tour_full.sh`, 15 warps) — its queued script was killed by the harness's 40-minute limit while the
machine was on another stream's speed lease; the ticket was released. The 4-zone route already reaches five maps and every zone change
shows the same direct write, take-over and 1-2 held reads. The PC 3050 was not used (the brief does not route it here).

## The question

PIPE2's warp tour (`docs/research/pipe2-order-thread.md` section 6) froze the meter after zone changes in both arms: the off arm's
last window 2000 of 2000 reads given the last result again, the on arm 395/681. PIPE2's build, `pipe2e`, is from `4b599eb04`;
EXPO1's fix `1aacae5ea` is **not** an ancestor of it (checked with `git merge-base --is-ancestor`). Does current main still freeze?

## Method

- Build: `build/s5/bin/expo2a`, main's tree, under build lease `expo2` (`mkg.ps1 -Root ...-wt/expo2/engine -Block -Lift -Pgo ...
  -Owner expo2`).
- Tour: Market save (`build/s5/savelib/market`), `kokiri-idle` scene, slot lease (priority 2), `HOS_INPUT_LIVE` fed by
  `tour_live.sh`; `!cheat` 1013 (Zora's Domain) at +15 s after play, 1007 (Lake Hylia) at +75, 1019 (inside the Deku Tree) at +135,
  1001 (Hyrule Field) at +195; `HL_METER_LOG=200`, `RX_VK_FLASH=1`, `RX_VK_SHOTS` (a shot every 300th present).
- Read: the `exposure sums: 2000 reads, M of them given the last result again (RX_VK_METER_HOLD)` lines, grouped by the `map:` line in
  force (`zones.py`); the `HL_METER_LOG` read rows and the `taken over again` rows (`meter.py`); the shots' mean luma
  (`shots_by_zone.py`, 96x54 grid).

## Results

### The three default tours (same build, same route)

| run | run length | maps | M per 2000-read window | flash rows | take-overs (real drops) |
|---|---|---:|---:|---:|---:|
| `expo2a-t2` | 255 s | Market, ZoraDomain, LakeHylia, DekuTree | 1 0 0 0 0 0 0 0 | 0 | 15 (11) |
| `expo2a-t3` | 330 s | Market, ZoraDomain, LakeHylia, DekuTree, HyruleField | 2 4 0 0 0 4 0 0 0 0 0 0 | 0 | 20 (16) |
| `expo2a-t4` | 330 s | same | 2 0 3 0 0 2 1 4 0 0 0 | 0 | 12 (8) |
| `expo2a-k0` | 330 s | same, `HL_RB_LAG_KEEP=0` | 2 0 0 0 2 0 0 0 0 0 22 0 0 0 4 0 0 0 0 0 0 0 0 | 0 | 0 |

No window is anywhere near "fully held" (a freeze in EXPO1's tables is 1990-2000 of 2000); the largest held count is 22 (1.1 %,
`expo2a-k0`, one window), and that run's first windows are 2 and 4.

The ring's own counters in the same runs say the same from the other side (`rbring R1:` rows, every 3000 reads): 2400 applied, **0
waited for the GPU, 0 not done in time**, and the age of every applied entry 2 frames (`age in frames ... 1/2/3/4+: 0/2400/0/0`). The
600 reads a window with no new entry are reads more frequent than their range's staging, or of a range the zone does not write; they
read the game's own zeros, not a stale result, and the hold only steps in for the 2-4 reads a zone change.

The "real drops" column counts the `taken over again ... (since the last staged one)` rows: a range that had been served, was written to
guest memory directly by a pool without a mirror at the zone change, and was taken back by the ring at its next binding in a mirror.
They are **four at a zone change**: the two 0x1040 blocks (A `0x113c88b000`, B `0x113c88e000`), the 0xc0 companion and one 0x2000
block. In `expo2a-t3`'s log they sit just **before** each `map:` line (take-overs 5-8 before `map: ZoraDomain_Child`, 9-12 before
`map: HyruleField_Child` = Lake Hylia, 13-15 before `map: InsideTheDekuTree`, 17-20 before the last `map: HyruleField_Child`): the
range is taken over again during the load itself, so the new zone's first frames are already served by the ring.

### One zone change in the log (`expo2a-t3`, take-overs 9-12, the load from Zora's Domain to Lake Hylia)

`meter.py`'s rows, in order (the blocks' newest entries and the read that consumed them):

- `f33833 0x113c88b000 ... ring does not serve: served 0 stageable 1 stg 2093/2096` — three written bindings since the last staged one
  went to guest memory directly (the pool lost its mirror across the load): the range is **not** served, the old path answers, and the
  read finds the direct binding's write-back, the new zone's real sum (`437c0000 00000000 00000000 00000000`).
- the next binding is in a mirror and takes the range over again (`rbring: 0x113c88b000 +0x1040 taken over again ... 3 of its 2097`);
  `f33834 ... HELD` (one read; the new entry `#15201 t33833` is not yet two frames old), `f33835 ... fresh` with the same
  `437c0000` and `age 2`.
- Block B (`0x113c88e000`) in the same frame: `f33834` one held read, `f33835` fresh (`c3d9a104 c52c1e5e`, the new zone's sums).

So the hold fires **once or twice per block per zone change**, which is what it is for (EXPO1's `0x113c88e000` rows: a read before the
new sums land is given the last result instead of zero), and the game has the new zone's sums one to two reads later.

The take-over is the whole of the fix: a range the ring cannot serve keeps its write-backs (`rb_ring::stage` returns false), and the
next binding in a mirror re-bases its staged count (`first_stage`), sets `settle` to that submission and serves it only once the GPU is
past it (`docs/research/expo1-stuck-meter.md`). Without it (`HL_RB_LAG_KEEP=0`) those later bindings are staged again, their write-backs
are left out, and the range stays unserved for good: the old path reads the game's own zeros and the hold repeats the last result at
every read — the freeze PIPE2 measured on a build without the fix.

### Pictures: the tour's zone changes

Mean luma (0-255) of the 96x54 grid of every shot, grouped by the warp interval it was written in (`shots_by_zone.py`; the first
interval holds the title screen and the save load):

| run | before 1013 | Zora's Domain | Lake Hylia | inside the Deku Tree | Hyrule Field |
|---|---|---:|---:|---:|---:|
| `expo2a-t2` | 0.0-107.7 (title/load/Market) | 43-49 (max 49.0) | **105-112** (max 112.3) | black (load, end of run) | not reached |
| `expo2a-t4` | 0.0-92.3 | 35.8 mean, max 47.1 | 60.4 mean, max 113.2 | 25.0 mean, max 43.0 | 40.5 mean, max 46.7 |
| `expo2a-k0` | 0.0-108.8 | 40.3 mean, max 47.7 | 96.6 mean, max 111.0 | 39.8 mean, max 111.2 | 41.0 mean, max 47.1 |

The Zora's Domain → Lake Hylia change (dark cave, then a bright outdoor lake at noon, `shots/expo2a-t2/vk_017100.png` against
`vk_023100.png`) shows no white flash and no washed-out frame: Lake Hylia's water and sky read 105-112 for the whole visit, the same
range as in the `HL_RB_LAG_KEEP=0` arm (96.6/111.0), i.e. the ring does not brighten the scene. Zero `vk: flash at` and zero
`vk: region flash` rows in all six runs. (The first frames after a load can be the zone's own title card — a white overlay with
"LAC HYLIA" on it, mean luma ~190 — and the shot cadence catches it at a different point in each arm; it is not the meter and the
steady frames after it are what is compared.)

### What is left of the hold, and why it is not a freeze

The hold still gives the last result when a block's own sums are zero for a few reads: `expo2a-k0` has one run of 22 held reads
(`f26719`-`f26798`, block A, `app 97438 -> 97964` advancing: the entries were applied and were zero, the block's previous sum was not).
That is the hold's old path behaviour, 22 reads long (~0.2-0.4 s at that run's read rate) and only while the game writes zeros (a load
or a fade); it ends by itself when the first nonzero sum is staged, and no window is even 2 % held. A block that no program writes at
all (the meter's third block, `0x113c891000`, in this route) keeps its zeros (its newest entries are all zero), so the hold has no last
nonzero result to give it: its reads are zeros, which is the truth.

## The counterfactual: the same code with the take-over off

The zone-change direct write is rare enough that one 330 s tour can miss it (the `expo2a-k0` run above did), so the freeze was also
produced on purpose with EXPO1's test switch, on the same build: each meter block's next written binding is sent to guest memory
directly once every 1500 frames from frame 12000 (`HL_RB_TEST_DIRECT=12000:1500`; 29 injections fired in each arm). Both arms are
otherwise the default build with shots and the flash detector on; the second turns the take-over off (`HL_RB_LAG_KEEP=0`).

| arm | injections | take-overs | M per 2000-read window | freeze rows (`read zero 600 times in a row`) |
|---|---:|---:|---|---:|
| `expo2a-d1` (default) | 29 | 42 | 4 2 1 6 0 2 2 0 12 1 2 1 5 2 0 2 | 0 |
| `expo2a-kd1` (`HL_RB_LAG_KEEP=0`) | 29 | 0 | **1744 1999 1995 1998 1998 2000 1998 1997 1999 1998 1996 1998 1998 2000 1998 1998** | 24 |

The rows around the first harmful injection (`expo2a-kd1`):

- `HL_RB_TEST_DIRECT: frame 15000, the binding of meter block 0x113c88e000 sent to guest memory directly (writes 256, staged 253)`;
- `meter read frame 15002 0x113c88e000: 00000000 ... zero, HELD ... ring does not serve: served 0 stageable 1 ... stg 254/257` — three
  written bindings went direct, later bindings are staged again, so `writes - staged` stays at 3 and the range is never served again;
  the old path reads the game's zeros and the hold gives the last result at every read;
- the `expo1-stuck-meter.md` warning appears: `exposure sums: block 0x113c88e000 read zero 600 times in a row, given the last result each
  time: its GPU results do not reach the game`.

With the take-over on (`expo2a-d1`), the same injection at frame 21000 gives `f21002 ... ring does not serve ... settle 147017` (the
range taken over, waiting for the GPU to pass that submission), and `f21003 0x113c88e000 42688a97 424ddb49 fresh ... app 5278` — one
held read, then the GPU's own sums. **The code still has the freeze; what main has is the recovery.** The real zone changes of the tours
above are the same event as the injection (a written binding that goes to guest memory while the pool has no mirror), which is why they
were each followed by a take-over row and no held reads beyond the changeover.

This is also the answer to "is the freeze gone because the trigger is gone": no, the trigger still happens (35 real drops in the three
tours, 29 injections here), the effect is gone.

## Since when, and why PIPE2 saw it

The freeze PIPE2 measured is the one EXPO1 fixed, not a new one: `pipe2e` (commit `0bb228966`) is built from `4b599eb04` (23 Nov
12:03), and `git merge-base --is-ancestor 1aacae5ea 0bb228966` says no — PIPE2's branch never got the 13:25 merge of `fix/expo1`.
PIPE2's section 6 is therefore the pre-fix behaviour on the pre-fix code (their "the next zone's blocks have nothing staged yet" is
the first half of the story: the blocks' new bindings *were* staged, but the range could never be served again, so the ring stayed
empty for good).

## Not measured / limits

- fps is not used here: these are picture/meter tours on a slot of a shared machine. The runs' summaries (e.g. `expo2a-t3.run`:
  165.5 fps, `expo2a-t4.run`: 90.0) are in `E:\OOT\scratch-expo2\*.run` and say nothing about this question.
- A block that a zone reads but no program writes, after an earlier zone gave it a nonzero sum, would be held at that old value for as
  long as the zone lasts. It was not observed in these tours (the reads' block is always the one the zone's programs write); the third
  block, which no program writes, has no nonzero sum to be held at.
- The PC 3050 (a GPU that runs behind) was not used; the brief does not route it here.

## Reproduce

```
cd /e/OOT/HeyListen
bash /e/OOT/scratch-expo2/build.sh expo2a 0                 # build lease expo2, mkg -Owner expo2, ~460 s
bash /e/OOT/scratch-expo2/tour.sh expo2a 'my-t1|-'          # slot lease prio 2, 4 warps, HL_METER_LOG=200, RX_VK_FLASH=1
python -I E:/OOT/scratch-expo2/zones.py build/s5/my-t1/game_log.txt
python -I E:/OOT/scratch-expo2/meter.py build/s5/my-t1/game_log.txt
python -I E:/OOT/scratch-expo2/shots_by_zone.py /e/OOT/scratch-expo2/my-t1.livelog E:/OOT/scratch-expo2/shots/my-t1
```

`zones.py` prints one row a 2000-read window with the `map:` line it was logged under; `meter.py` prints the `HL_METER_LOG` rows (the
block, the words the game read, HELD or fresh, the ring's standing and entries); `shots_by_zone.py` the shots' mean luma by warp
interval. The tour scripts are `tour.sh` (4 warps, pictures) and `tour_full.sh` (FOOT1's 15 warps, no pictures); both request a slot
lease and restore the slot's own exe/dll from `E:\OOT\scratch-expo2\bak-<slot>` at the end.



