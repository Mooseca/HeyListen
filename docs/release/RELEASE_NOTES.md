# HeyListen {TAG}

HeyListen turns **your own** Switch 2 copy of *The Legend of Zelda: Ocarina of Time* into a native Windows and Linux
game. The release holds only the **HeyListen Builder**: no game code, data, keys or shaders. You dump your own game as a
`.nup`, the builder reads it, translates and compiles the game on your PC, prepares its shaders, and starts it. See the
[user guide](https://github.com/Sacrappy/HeyListen/blob/main/docs/USER_GUIDE.md).

## Download

- **Windows: HeyListenBuilder.exe**, the setup. Run it; it downloads the builder and its tools (checked by SHA-256) into
  `%LOCALAPPDATA%\HeyListenBuilder` and opens it. Already installed: the builder offers the update itself.
- **Linux: `HeyListen-{TAG}-x86_64.AppImage`** (glibc 2.35 and newer; see the Linux section of the user guide).
- `heylisten-setup.txt`, `heylisten-linux.txt`: the lists of parts the setup and the AppImage's update read (you do not
  need to download them). `SHA256SUMS.txt`, `SHA256SUMS-linux.txt`: checksums.

**Shaders are prepared again once with this release.** The way prepared shaders are recorded changed (below): the first
start after the update prepares them as a new install does. Later updates start at once.

## New in this release

**No more outlines and light rectangles around the HUD** (issue 16). The game's ASTC textures are re-encoded to BC7 on
your PC to save video memory, and the encoder stored fully transparent texels as white at alpha 1/255: on dark scenes
the whole quad of each HUD sprite (the map, item icons, the title logo) was lifted by a few levels. Alpha 0 and 255 are
now exact; the rectangles are gone, as they were with `RX_VK_ASTC_RGBA8=1`, at no cost in video memory.

**No more one-frame black world in Zora's Domain** (issues 3 and 14). When a frame's drawing was recorded on several
threads, a pass that only cleared two of the scene's images was not counted as having drawn them, and another thread
copied stale memory over them: the world went black for one frame, mostly while moving the camera. Measured with the
reporter's save: 24 to 36 black frames in every 10,000 before, none after (also confirmed by eye).

**A drawn image is no longer overwritten from memory** (issue 3). For textures in the game's virtual memory pools, the
engine did not note which pages back an image the GPU drew, and later uploaded the whole image from memory that never
held it (a black or stale surface for a moment). In Zora's Domain: 103 such re-uploads in a few minutes before, 1 after.

**Faster frames on mid-range PCs.** A copy step was hashing the game's memory twice for every submission (a regression
since sprint 5): on an RTX 3050 / i5-10400F, +13% in Castle Town and +9.5% in Kokiri Forest. On Linux with AMD
(RADV), the readback wait now covers only the light meter: +26% on an RX 9070 XT (a contributor's pull request, #25).

**Updates no longer wait for the shaders.** Each prepared program now carries a key of what the driver compiles; after
an update the game starts at once and the programs are checked in the background, and only those that really changed
go to the driver again. (This release itself still prepares once: the record starts with it.)

**Skip title screen** (Insert menu, Gameplay, off by default): a start goes straight into the most recent save.

**exeFS (code) mods**: the builder can apply IPS, IPS32 and pchtxt code mods before the translation (its "Code mods"
option); functions a mod patches are left to the translated code, and the log says which.

**Intel GPUs** (issue 23): Longshot's fixes for Intel's Windows driver: compute programs built without the optimizer
first (the freeze after loading a save on Intel laptops), a crash while saving the pipeline cache, white blocks on
integrated GPUs, a device loss on Arc B-series (Battlemage), and one shader compile at a time in Intel's compiler.

**Less memory on 16 GB PCs and the Steam Deck**: under 32 GB of RAM the game is told the memory it really maps, as on the
console, and stops growing its caches (1.2 to 2.6 GB less commit, up to 1.1 GB less RAM in Hyrule Field).

**Linux**: the AppImage now builds the game with the native engine's C++ (it failed with "'cstddef' file not found"
in the test builds); the title movie no longer judders (#22); the Full overlay shows AMD GPUs' load, temperature, power,
clock and VRAM (#24).

**Also**: the window's downscale averages a larger picture instead of sampling it (from Longshot); the Frame rate limit moved to
an option id of its own; the stall markers name the command a stuck GPU never finished (`RX_VK_CHECKPOINTS=1`).

**AMD FSR 4** as an Upscaler choice (and FSR 4's native anti-aliasing), next to DLSS, DLAA and FSR 3.1. It needs an
RDNA 4 card (RX 9000 series); we had none to try it on, so it ships untested: please report how it looks and runs.
The overlay's Scaling line now names the upscaler that draws (it said "bilinear" alone while DLSS drew).

**Linux diagnostics** (#26): job traces, readback call sites, the overlay's shader and pipeline waits counted apart,
the CPU's temperature in the Full overlay, and the early segments' GPU time in the log.

## Performance

In-game frame rates only, from the moment play begins (no title, loading or shader preparation): 2560x1440, 3D scene
at 100 %, no upscaling, no frame generation, no HDR, uncapped, Link idle in each zone loaded from the same saves.
PresentMon over the 40 s after each build's "in play" marker, without its first 3 s; the mean of two runs per zone.
Compared with NX2navi 0.11.0-rc4 and Longshot v3.0.0-rc.4. Full method, the whole-window tables and every caveat:
[docs/benchmarks/2026-11-16-v0.4.0-zones.md](https://github.com/Sacrappy/HeyListen/blob/main/docs/benchmarks/2026-11-16-v0.4.0-zones.md).

| Machine | Zones | NX2navi fps | NX2navi 1% low | Longshot fps | Longshot 1% low | **HeyListen fps** | HeyListen 1% low |
|---|---:|---:|---:|---:|---:|---:|---:|
| i5-10400F, RTX 3050 8 GB | 17 | 29.7 | 22.6 | 35.6 | 28.1 | **40.8** | 24.4 |
| Ryzen 7 7800X3D, RTX 5070 12 GB | 13 | 68.0 | 35.5 | 86.0 | 51.4 | **96.2** | 43.6 |

HeyListen has the highest average frame rate in 14 of 17 zones on the RTX 3050 and in 10 of 13 on the RTX 5070 (+15 %
and +12 % over Longshot, +37 % and +41 % over NX2navi). Its 1% lows are still below Longshot's (some 100-350 ms frames in
steady play); that is the next thing we work on.

<details><summary>Per zone, RTX 3050 + i5-10400F</summary>

| Zone | NX2navi fps | NX2navi 1% low | Longshot fps | Longshot 1% low | **HeyListen fps** | HeyListen 1% low | HeyListen vs the faster |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hyrule Field | 38.2 | 29.1 | 31.6 | 26.0 | **44.8** | 20.5 | +17% |
| Lost Woods | 30.0 | 17.0 | 35.7 | 23.4 | **38.1** | 22.9 | +7% |
| Sacred Forest Meadow | 27.3 | 21.7 | 32.9 | 28.0 | **37.2** | 19.8 | +13% |
| Great Fairy Fountain | 66.2 | 44.0 | 55.3 | 44.2 | **56.4** | 37.7 | -15% |
| Kokiri Forest | 18.8 | 15.5 | 31.7 | 26.4 | **36.7** | 21.6 | +16% |
| Inside the Deku Tree | 39.3 | 29.6 | 38.3 | 30.6 | **43.5** \* | 36.4 | +11% |
| Deku Tree meadow | 20.3 | 16.8 | 31.3 | 26.7 | **33.8** | 25.0 | +8% |
| Lake Hylia | 20.6 | 17.6 | 27.9 | 21.0 | **38.2** | 22.0 | +37% |
| Gerudo Valley | 23.3 | 19.1 | 30.3 | 26.2 | **35.2** | 21.2 | +16% |
| Lon Lon Ranch | 27.0 | 21.8 | 30.3 | 18.1 | **40.5** | 15.0 | +33% |
| Market | 25.5 | 20.2 | 33.7 | 25.9 | **41.7** | 25.5 | +24% |
| Temple of Time | 43.3 | 30.3 | 50.7 | 35.2 | **47.8** | 21.9 | -6% |
| Hyrule Castle | 25.9 | 21.0 | 33.8 | 29.6 | **37.8** | 24.7 | +12% |
| Kakariko Village | 23.1 | 18.8 | 35.2 | 28.4 | **44.7** | 22.5 | +27% |
| Graveyard | 22.0 | 18.5 | 29.8 | 24.5 | **31.0** | 14.6 | +4% |
| Death Mountain Trail | 33.8 | 25.8 | 43.8 | 37.8 | **49.7** | 40.3 | +14% |
| Zora's River | 19.9 | 16.6 | 32.4 | 25.9 | **36.4** | 23.7 | +13% |
| **Mean of 17 zones** | 29.7 | 22.6 | 35.6 | 28.1 | **40.8** | 24.4 | |

</details>

<details><summary>Per zone, RTX 5070 + Ryzen 7 7800X3D (13 zones; read the note below the table)</summary>

| Zone | NX2navi fps | NX2navi 1% low | Longshot fps | Longshot 1% low | **HeyListen fps** | HeyListen 1% low | HeyListen vs the faster |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hyrule Field | 63.1 | 29.4 | 93.7 | 61.9 | **111.9** | 41.1 | +19% |
| Lost Woods | 72.1 | 36.4 | 72.8 | 20.5 | **92.0** | 51.4 | +26% |
| Sacred Forest Meadow | 65.6 | 44.9 | 91.5 | 68.5 | **104.5** | 71.5 | +14% |
| Great Fairy Fountain | 106.9 | 61.7 | 111.3 | 79.9 | **117.7** | 51.5 | +6% |
| Kokiri Forest | 61.2 | 23.7 | 77.8 | 34.0 | **90.5** | 33.8 | +16% |
| Inside the Deku Tree | 83.9 | 43.2 | 108.5 | 86.0 | **122.2** | 83.7 | +13% |
| Deku Tree meadow | 64.6 | 28.7 | 85.8 | 63.0 | **91.5** | 54.8 | +7% |
| Lake Hylia | 43.8 | 22.8 | 38.9 | 0.8 | **73.0** | 31.7 | +67% |
| Gerudo Valley | 72.6 | 44.7 | 85.6 | 64.1 | **93.5** | 35.8 | +9% |
| Lon Lon Ranch | 57.6 \* | 21.1 | 84.6 | 51.3 | **88.7** | 23.5 | +5% |
| Market | 51.6 | 23.1 | 77.6 | 46.1 | **76.9** | 30.9 | -1% |
| Temple of Time | 84.9 | 50.0 | 104.8 | 32.3 | **102.5** | 17.5 | -2% |
| Hyrule Castle | 55.9 | 31.8 | 85.0 | 60.1 | **85.0** | 39.6 | 0% |
| **Mean of 13 zones** | 68.0 | 35.5 | 86.0 | 51.4 | **96.2** | 43.6 | |

On this PC the series ran while the PC was in use, mostly windowed, and NVIDIA's own shader cache sat at its 1 GB
default while the three games ran in turn, so they evicted each other's pipelines: some HeyListen and Longshot windows
hold multi-second frames that the RTX 3050 runs do not show. NX2navi ran with its performance overlay from the Great
Fairy Fountain to Lon Lon Ranch.

</details>

\* one valid run instead of two. Present modes differ: NX2navi and Longshot ran with immediate presents, HeyListen with
mailbox (its default, no tearing). The Great Fairy Fountain: the dump used has damaged files there, which NX2navi
replaces with stand-ins.

## Known issues

- Deep water's round ripple around Link jumps when the camera turns (Zora's River, Zora's Domain): known, cosmetic.
- Steam Deck and other AMD GPUs on Linux (RADV): a GPU fault or hang in some areas (issue 14). Until the fix (in the next
  release), `RX_VK_MESH_OPT=1` and `RX_VK_NULL_WRITE=1` in `hookshot_env.txt` stop it on the Steam Deck; one tester
  then sees some rendering glitches, which we are looking into.
- Intel integrated GPUs on Linux (Mesa ANV): very slow shader compiles and a black screen after loading a save on some
  machines (issue 23).
- Native HDR may flash on some displays (issue 13).
- A rare GPU loss shortly after entering an area ("the GPU device was lost" in the log, the game closes): about 1 area
  load in 25 on an RTX 3050 in our tests, rarer on faster cards; on AMD on Windows it can happen at every start of the
  first area (issue 27). Starting the game again works; the next start may prepare the shaders once more. A fix is being
  worked on.
- The first area load after a rebuild that changed the shaders can freeze for 30-45 s while the shaders are translated
  (not at the first start of v0.4.0, which prepares everything once).
- Long sessions: some players see the frame rate drop after 30-60 minutes (issue 30); being investigated.
- Tip for NVIDIA cards: the driver keeps compiled shaders in a cache of 1 GB by default, shared by every game. If you
  play several big games, HeyListen may find its shaders evicted and compile them again (longer starts, stutters).
  NVIDIA Control Panel > Manage 3D settings > Shader Cache Size: 10 GB or Unlimited avoids it.
