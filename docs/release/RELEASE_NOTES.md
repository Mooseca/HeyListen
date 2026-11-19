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

**Shaders are prepared again once** with this release: the first start takes a few minutes longer, and the first session
builds the driver's pipelines as you play, so it stutters more than usual. The second start is smooth again.

{TAG}, new since v0.4.1
-----

### Features

* **perf:** the capture copies only the memory the GPU can read (+13% fps on an RTX 3050)
* **perf:** the hybrid engine's native main loop, physics units and program-pick memo are on by default
* **builder:** the AMD FSR 4 tick downloads AMD's runtime, checks it and puts it in place, as the launcher does
* **crash reports:** the crash window's "report" button opens an issue that already holds the report (no paste needed)

### Fixes

* **crash:** the first start no longer uses up to 39 GB of memory while it builds pipelines: the game's two largest shader programs are left to the draws that need them (crashes at the title on 16 GB PCs)
* **crash:** at Windows' memory limit (RAM plus the page file) the game waits for memory and, if none comes back, stops with an out-of-memory message instead of crashing; the textures give memory back before the limit ([#62](https://github.com/Sacrappy/HeyListen/issues/62))
* **crash:** changing the frame generation multiplier while playing no longer crashes NVIDIA and AMD drivers
* **crash:** a model's full memory heap is tried in its parent heaps instead of handing the game an empty pointer
* **vk:** a pipeline is drawn only with the program it was built for: the device lost on AMD RDNA 2/3 and the Steam Deck at the same draw ([#14](https://github.com/Sacrappy/HeyListen/issues/14), [#51](https://github.com/Sacrappy/HeyListen/issues/51), [#63](https://github.com/Sacrappy/HeyListen/issues/63), tested in [#65](https://github.com/Sacrappy/HeyListen/pull/65))
* **vk:** GPU fault on RDNA 4 under Linux in Hyrule Field: buffer views go with the memory they were made on ([#61](https://github.com/Sacrappy/HeyListen/issues/61))
* **vk:** no more dark blocks on the water and floor in Jabu-Jabu and around characters ([#16](https://github.com/Sacrappy/HeyListen/issues/16), [#59](https://github.com/Sacrappy/HeyListen/issues/59))
* **vk:** three Vulkan usage errors the validation layer reported: the overlay's functions, 8/16-bit integers on cards without them, overlapping uniform updates ([#64](https://github.com/Sacrappy/HeyListen/pull/64))
* **vk:** fixes from Longshot rc6: AMD and Intel ports, RX 6800 (Navi 21) bounds, the ground texture garbling after minutes in one area

Credits for every port are in the [README](https://github.com/Sacrappy/HeyListen#credits).
