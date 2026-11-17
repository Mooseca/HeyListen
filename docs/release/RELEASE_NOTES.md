# HeyListen {TAG}

HeyListen turns **your own** Switch 2 copy of *The Legend of Zelda: Ocarina of Time* into a native Windows and Linux
game. The release holds only the **HeyListen Builder**: no game code, data, keys or shaders. You dump your own game as a
`.nup`, the builder reads it, translates and compiles the game on your PC, prepares its shaders, and starts it. See the
[user guide](https://github.com/Sacrappy/HeyListen/blob/main/docs/USER_GUIDE.md).

🎮 To play, download the HeyListen Builder
=====
### [🪟  Download the Builder for Windows](https://github.com/Sacrappy/HeyListen/releases/download/{TAG}/HeyListenBuilder.exe)
### [🐧  Download the Builder for Linux (AppImage)](https://github.com/Sacrappy/HeyListen/releases/download/{TAG}/HeyListen-{TAG}-Linux-x64.AppImage)
Run it, pick your own `.nup` (Switch 2, version 131072): it builds the game on your PC and starts it. Nothing of the game is in
these files.

Also on [RecompLauncher](https://recomplauncher.com), if you use it: HeyListen is in its library, with the same build done for you
(`HeyListen-{TAG}-Windows-x64.zip` below is what the launcher installs; you don't need to download it).

**Shaders are prepared again once** with this release (the mesh programs are translated differently): the first start
takes a few minutes longer, later starts are as before.

{TAG}, new since v0.4.0
-----

### Features

* **builder:** the progress bar moves while your `.nup` is read (it used to sit at the start for minutes); a RecompLauncher setup also prepares the shaders and pipelines, with their progress, instead of the first start
* **telemetry:** opt-in crash reports and performance statistics, both off by default (Privacy settings in the game and in the launcher); no save, no game data, no account, user name and paths removed
* **vk:** `RX_VK_MESH_SHADERS=native` or `compute` picks the mesh path by hand
* **perf:** smaller mesh shaders: big mesh programs keep their memory helpers out of line, constant flag operations fold, each mesh invocation works its buffer ranges out once (-1.1 ms of GPU in Kokiri Forest on an RTX 3050)
* **perf:** fewer textures held back at area loads, the upload budget counts per thread ([#58](https://github.com/Sacrappy/HeyListen/pull/58))
* **perf:** upstream Hookshot's batch: background workers on 16-thread CPUs, texture spans aged once a frame, fewer copies and write-backs in the replay, the pipeline cache written only when it changed, passes ordered by the game's barriers on NVIDIA
* **perf:** fewer stalls: flat per-draw caches, only changed vertex streams bound, recording threads wait less on the copy lock ([#38](https://github.com/Sacrappy/HeyListen/pull/38) to [#42](https://github.com/Sacrappy/HeyListen/pull/42))
* **perf:** the program cache is packed (6.4 GB became 1.7 GB)
* **build:** the Vulkan back end can be built with a play profile ([#54](https://github.com/Sacrappy/HeyListen/pull/54))
* **launcher:** HeyListen can also be installed, started and set up from RecompLauncher: the game is built from your own copy with no window, settings are on the game's page, saves are found
* **launcher:** NVIDIA DLSS and AMD FSR 4 are ticks on the setup screen; NVIDIA's and AMD's files are downloaded from them, checked and put in place for you
* **launcher:** a `logs` folder keeps the last five runs' logs for the launcher's crash reports

### Fixes

* **vk:** AMD RX 6000 and the Steam Deck on Linux run mesh work on the compute path, the fix for device-lost crashes ([#51](https://github.com/Sacrappy/HeyListen/issues/51))
* **vk:** RX 6700 / 6800 on Windows draw task and mesh work on the compute path ([#57](https://github.com/Sacrappy/HeyListen/issues/57))
* **vk:** AMD lighting: storage buffers at the driver's 16-byte alignment ([#45](https://github.com/Sacrappy/HeyListen/pull/45))
* **fps:** above a 60 fps cap, sounds, moving platforms, the pick-up counter, the time of day, water ripples, the Deku Tree's web and the opening movie's cues keep their speed ([#46](https://github.com/Sacrappy/HeyListen/pull/46))
* **host:** no more quarter-second frames at a cap: no virtual core held while a thread sleeps on a lock ([#56](https://github.com/Sacrappy/HeyListen/pull/56))
* **vk:** a game folder built by an older version no longer aborts in the shader preparation ([#48](https://github.com/Sacrappy/HeyListen/pull/48))
* **vk:** fixes from Longshot: Intel compile faults and Arc B-series device loss, ASTC decoded on the CPU for AMD's integrated graphics (no more GPU resets in Kokiri Forest), the Steam Deck's Game Mode recompiling every pipeline, shader programs over 1 MiB, samplers past the driver's limit, read-backs after a timeout
* **linux:** the sound output is closed before it opens again ([#44](https://github.com/Sacrappy/HeyListen/pull/44)); short sleeps wait on the timer ([#43](https://github.com/Sacrappy/HeyListen/pull/43))
* **vk:** a stuck GPU's report says what it was running; `hookshot_env.txt` takes the hybrid engine's switches

Credits for every port are in the [README](https://github.com/Sacrappy/HeyListen#credits).
