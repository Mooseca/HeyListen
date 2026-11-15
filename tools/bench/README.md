# tools/bench - frametime benchmark harness (TICK-001)

```
python tools/bench/run_bench.py --exe <HeyListen.exe|lichii.exe> --scene <name> --out <dir>
        [--duration 90] [--warmup-s N] [--repeat N] [--fps-limit 120] [--input-script S]
        [--presentmon <PresentMon.exe>] [--game <file for lichii -g>] [--build auto|hookshot|lichii]
python tools/bench/summarize.py [--warmup-s N] [--origin launch|first_present] <dir> [<dir> ...]
```

Runs one build, collects per-frame present intervals, writes `<dir>/bench.json`
(plus the raw `present_trace.csv` / `presentmon.csv` and `game_log.txt`).
Exit code 0 when frames were recorded, 2 when none were.

On Linux, `--exe` is the game folder's `hookshot`, and the running check uses `pgrep -x`. The run guards (copies
into `<dir>/save-guard/<n>` before, puts back after) every save folder the game may write that exists: `user/save`
beside the exe (and one folder up), and on Linux the game's data folder, `$XDG_DATA_HOME/heylisten/save` (when
`XDG_DATA_HOME` is an absolute path, as `engine/host/hos_main.c` reads it; else `~/.local/share/heylisten/save`), and
`.../hookshot/save`, where builds before the HeyListen names saved. `<dir>/save-guard/<n>.txt` names each copy's folder.
`BENCH_KEEP_GAME_SAVES=1` turns the guard off.

On Linux each run also records the machine (`environment` in bench.json) and, with an amdgpu card, the GPU's busy share
(`gpu_busy`, and every sample in `gpu_busy.csv`): see bench.json below. `summarize.py` prints them as a second table
when a directory has them.

`--repeat N` (TICK-009) runs N launches back to back into `<dir>/run1` .. `run<N>`
(each with its own watchdog, the game killed before the next one starts) and writes
`<dir>/repeat.json`: fps min/max/mean and `spread_pct` = (max - min) / mean. The
"within 5%" check is `within_limit`. `--repeat 1` (default) writes to `<dir>` directly.

`summarize.py <dir> ...` prints the Markdown table of `docs/benchmarks/2026-11-baseline.md`
(fps, p50/p95/p99/max, share of frames > 16.7 ms) for Hookshot traces and PresentMon CSVs.
Each directory's warm-up comes from its `bench.json`. Directories without one (the
TICK-004 captures) count from the first present. `--warmup-s 45 --origin first_present`
reproduces the baseline's Hookshot rows; Lichii rows are the whole capture.

## Summary metrics (TICK-013)

Added to the summary table and to `bench.json` (schema 3). All are computed from the raw
frame intervals after the warm-up, so bench.json of schema 1, 2 and 3 summarize the same way.

- **1% low fps** / **0.1% low fps**: `1000 / mean(frame time of the slowest 1% / 0.1% of frames)`.
  The slowest `ceil(share x N)` frames, and at least one frame, so a short run's 0.1% low is
  its single worst frame. Output keys: `fps_1pct_low`, `fps_0_1pct_low`.
- **frames > 8.33 ms** (the 120 Hz budget, 1000/120) and **frames > 6.94 ms** (144 Hz,
  1000/144): share of frames strictly above the budget, in percent. Keys
  `over_8_33_ms_pct`, `over_6_94_ms_pct`.
- **frames > 16.7 ms** (60 Hz): unchanged, also in bench.json as `over_16_7_ms_pct`.

The 120/144 shares only mean something when the game is not capped below that rate, so
bench at the rate you are checking (below).

## Benching at 120 / 144 / 240 Hz

The Hookshot frame cap is `--fps-limit` (sets `HOS_FPS_LIMIT`, default 120). Set it to the
target rate and read the matching budget column:

```
python tools/bench/run_bench.py --exe <HeyListen.exe> --scene hyrule-walk --out <dir> --fps-limit 120 --duration 115
python tools/bench/run_bench.py --exe <HeyListen.exe> --scene hyrule-walk --out <dir> --fps-limit 144 --duration 115
python tools/bench/run_bench.py --exe <HeyListen.exe> --scene hyrule-walk --out <dir> --fps-limit 240 --duration 115
python tools/bench/summarize.py <dir> ...
```

- 120 Hz: `--fps-limit 120`, judge by "frames > 8.33 ms" and "1% low".
- 144 Hz: `--fps-limit 144`, judge by "frames > 6.94 ms".
- 240 Hz: `--fps-limit 240`. There is no 240 Hz budget column; read the frame times
  (p95/p99, 1% low) against 1000/240 = 4.17 ms. Add a column if it is needed.

`--fps-limit` is Hookshot only (`HOS_FPS_LIMIT`). Lichii's cap is set in the emulator, and
its runs use PresentMon: the budget columns are then the host present intervals, not guest frames.
Compare runs only at the same `--fps-limit`: a run capped at 120 can never average more than
120 fps, so its 144 Hz column is not a 144 Hz result.

## Warm-up (TICK-009)

`--warmup-s` is counted from **game launch** (wall clock), not from the first present.
Default: **60 s for Hookshot**, 0 for Lichii (the baseline measured the whole capture).

How the default was chosen, from the TICK-004 traces (`build/bench/hookshot-*`, log
windows of 120 presents, trace times converted with the launch offset below):

- Kokiri Forest: fps drops from the capped title (120) to 45-60 at about 15.7-18.4 s
  after the first present, i.e. about 29-30 s after launch. Scene-entry hitches (up to
  ~500 ms) are over by ~18 s after the first present.
- Hyrule Field: the drop is at 41.3-44.6 s after the first present (about 53-57 s after
  launch). The last scene-entry hitch (~650 ms) is at 42.0-42.8 s after the first present.
- 60 s after launch covers both entries with a few seconds of margin and leaves
  about 30 s of gameplay in a 90 s run, or ~55 s in the 115 s maximum.

These are from the log and trace timing only, not a repeat of the baseline runs.

### Launch offset

`bench.json` records `launch_offset_s`, the time from the game launch to the first
present. `run_bench.py` takes `time.perf_counter_ns()` just before starting the game
and subtracts it from the first trace row's `return_ns`. Checked on the TICK-004 runs:
the trace clock is QPC since boot, which is what `perf_counter_ns` reads on Windows
(boot time from `Win32_OperatingSystem.LastBootUpTime` plus `return_ns` gives a first
present 11-13 s after the recorded `started_utc`, which is truncated to whole seconds;
the ~9 s shader precompile in the game log is most of that).

If the offset is implausible (outside 0-120 s, i.e. another clock), the offset is the
time the first trace row was seen on disk (polled during the run). That is an upper
bound because the file is buffered. If neither works, `launch_offset_s` is null and
`warmup_origin` is `first_present`, with a warning. Lichii has no launch offset (the
PresentMon capture starts after launch and its clock is not measured), so its warm-up
counts from the first PresentMon row.

## Window from play (schema 5)

A run counted from launch (`--warmup-s`) measures the title and the loading when it is late out of the title. The named
scenes (`kokiri-idle`, `kokiri-walk`, `hyrule-idle`, `hyrule-walk`, `castle-move`) therefore start the game with
`HL_SKIP_TITLE=1` (the game presses A through the title and the file list by itself, from the newest save in the
folder's `user/save`: `engine/host/oot_autoload.c`) and `HOS_INPUT_FROM_PLAY=1` (the scene's inputs count from the moment
play begins, so they carry no title presses), and cut the window at that moment:

- The game logs `play: began at clock <ns> ns, <s> s after the process started` when the player first runs. The harness
  reads it on its own clock (the same QPC clock) and writes `play_at_s` (seconds after launch) into bench.json;
  `warmup_origin` is `play` and `window_start_s` is where the window starts, in seconds after the first present.
  `--play-settle-s N` leaves N more seconds out (default 0). `--warmup-s` is not used then (a warning says so).
- A run that never reaches play (no save in the folder: the title stays; the presses did not get through) is
  `status: "failed"` with `failure`, `frames` 0 and exit code 2, not measured. The run ends as soon as the game
  logs that it stopped waiting for the title (no save), not at the end of the duration.
- `--title input` is the old way: the scenes' own presses through the title from launch (scripts `HOOKSHOT_SCENES`) and
  the `--warmup-s` window counted from launch, kept for comparisons with older runs. An `--input-script` also keeps it by
  default (its times were written for the launch clock); `--title skip --input-script S` makes them count from play.
  `--warmup-origin launch|play` chooses the cut apart from the title mode (`play` needs `--title skip`).
- `summarize.py` takes the window of a play-origin run from `window_start_s`; a failed run shows 0 frames.

## Watchdog

The game (and PresentMon) are launched as children of the script. They are killed
(`taskkill /F /T`) when the duration is over, by a timer thread at `duration + 20 s`
(never more than 120 s after launch), in a `finally` block on any exception, and by
`atexit`. `--duration` is clamped to 115 s. Killing the script itself with SIGKILL or
Task Manager is the one case this cannot cover.

## Hookshot

Same launch as `hookshot-fork/scripts/walk-test.sh`: cwd = the exe folder, env
`HOS_FPS_LIMIT`, `HOS_AUDIO=0`, `HOS_WINDOW_NOACTIVATE=1`, `HOS_INPUT_SCRIPT` (title
-> save via scripted A presses). Scenes: `kokiri-idle` (Link stands at the spawn point),
`kokiri-walk` (adds a walk at 76/83/89 s). `--input-script` overrides.

Frame times come from `HOS_PRESENT_TRACE=<csv>` (native present-call returns,
`frame,return_ns,interval_ns`; not GPU completion or display times). The first
row (interval 0) is dropped. A forced kill may lose the last ~1 s of buffered rows.
The 120-present `vk: N presents, X fps` lines of the game log are copied to
`log_window_fps` as a cross-check only (they are one number per 120 frames).
The save is reached from the title, which takes a while; the default warm-up (60 s from
launch, see above) skips it. Use `--duration 115` to keep a useful measurement window
after the warm-up.

## Lichii (Eden fork)

No per-frame log exists: the emulator log (`%APPDATA%\eden\log\eden_log.txt`) has only
settings and no frame times. The source is **PresentMon** (not installed on this
machine at the time of writing). Without it the script exits before launching anything.
It runs `PresentMon --process_name lichii.exe --output_file presentmon.csv --timed N
--terminate_after_timed --stop_existing_session --no_console_stats` (PresentMon 2.6; 1.x used `--no_top`) and reads `msBetweenPresents`
(1.x) or `FrameTime` (2.x). Needs an elevated shell or Performance Log Users
membership for ETW. The scene is not controllable: Lichii has no input script, so
`--scene` is only a label and the user positions the game; this is a gap. These are
PresentMon's present intervals on the host swap chain, not guest (Switch) frames.

## bench.json (schema_version 5)

| key | type | meaning |
|---|---|---|
| schema_version | int | 5 (the play window: `title`, `play_at_s`, `window_start_s`, `status`, `failure`; `warmup_origin` may be `play`). 4 = environment and gpu_busy added; 3 = low fps and budget shares (TICK-013), 2 = launch-based warm-up, 1 = warm-up counted from the first present; all still read |
| build | "hookshot"/"lichii" | |
| exe, scene | string | inputs |
| source | "hos_present_trace"/"presentmon" | where frame times came from |
| started_utc | string | ISO 8601 |
| duration_requested_s, wall_clock_s | number | requested vs actual run time |
| warmup_s | number | frames before this many seconds are ignored (see Warm-up) |
| warmup_origin | "launch"/"first_present"/"play" | what warmup_s is counted from (absent in schema 1 = first_present); `play`: the window starts when play began and warmup_s is the settle time after it |
| title | "skip"/"input" | schema 5: how the run got through the title (see Window from play) |
| play_at_s | number/null | schema 5: seconds from launch to the game's `play: began` line (null when it never came, also in runs of the old way that did not log it) |
| window_start_s | number/null | schema 5: where the measured window starts, in seconds after the first present (null: failed) |
| status, failure | "ok"/"failed", string/null | schema 5: failed = a `play` run that never reached play, nothing measured |
| launch_offset_s | number/null | game launch to first present (see Warm-up) |
| killed_by_harness | bool | game still running at the end and was killed |
| watchdog_fired | bool | the hard timer (not the normal end) killed it |
| exit_code | int/null | null when killed |
| frames | int | frames counted |
| fps | number | frames / total frame time = 1000 / mean |
| frame_time_ms | object | `mean`, `p50`, `p95`, `p99`, `max` (percentiles interpolated linearly) |
| fps_1pct_low, fps_0_1pct_low | number | schema 3: 1000 / mean of the slowest 1% / 0.1% frames (see Summary metrics) |
| over_8_33_ms_pct, over_6_94_ms_pct, over_16_7_ms_pct | number | schema 3: % of frames above 8.33 / 6.94 / 16.7 ms |
| log_window_fps | [number] | Hookshot only, see above |
| environment | object/null | schema 4, Linux (null elsewhere), read before the launch: `cpu_governor` (the CPUs' `scaling_governor`s, comma-separated when they differ), `thp_enabled` and `thp_shmem_enabled` (the chosen word of `/sys/kernel/mm/transparent_hugepage/enabled` and `shmem_enabled`), `udmabuf_size_limit_mb` (`/sys/module/udmabuf/parameters/size_limit_mb`, null when udmabuf is not loaded), `loadavg_start` (`/proc/loadavg`'s three), `kernel`, `mesa` (the drivers' `driverInfo` from `vulkaninfo --summary`, null without it). A field that cannot be read is null |
| gpu_busy | object/null | schema 4, Linux with an amdgpu card (null otherwise; there is no NVIDIA reader): `source`, `from_s_after_launch` (the warm-up: samples before it are left out) and per card `pci`, `samples`, `mean_pct`, `p50_pct`, `p95_pct` of `/sys/class/drm/card<N>/device/gpu_busy_percent`, read every 0.2 s |
| warnings | [string] | caveats of this run |

## Tests

`python -m pytest -q tools/bench` - parsers on sample files in `testdata/`, the warm-up and
launch-offset logic, the fps spread, `summarize.py` on synthetic directories, the
watchdog, the 1% / 0.1% low fps and the 120 / 144 / 60 Hz budget shares on synthetic traces,
the save folders guarded and put back, the Linux environment and GPU busy readers on a fake sysfs,
and end-to-end runs (`--repeat 2` included) against a fake game process. No real game is started, and the tests use a
data folder of their own (`XDG_DATA_HOME`), never the user's saves.
