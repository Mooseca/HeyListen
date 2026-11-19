# Contributing to HeyListen

HeyListen turns your own Switch 2 copy of *The Legend of Zelda: Ocarina of Time* into a native Windows and Linux game:
the game's code is translated to C ahead of time, the console's system and graphics API are implemented natively, and
the GPU work is replayed on Vulkan. The game is built on the player's PC, from the player's own dump.

Reports, tests on other hardware, fixes and documentation are all welcome. This page says what helps most, how to
report, how to build and test, and the rules that keep the project out of trouble.

## The rule with no exceptions

**No game files, keys, or anything made from them leave your PC.** The repository does not contain the game and never
will. That includes:

- the `.nup`, `romfs`, `exefs`, `.nso`, `.nca`, `.nsp`, `.xci`, `.nsz`/`.xcz` files, and any keys;
- the build's work folder: the extracted dump, `image.bin`, the lifted C, test builds, runs and their screenshots;
- `HeyListen.exe`, `hookshot_vk.dll`, the shader and pipeline caches (`hookshot_*.bin`) and other build output;
- saves (`user/`).

Do not open an issue or a pull request asking where to get the game, how to decrypt it, or for someone else's files.
A screenshot, a video and `hookshot_log.txt` are fine and often necessary: the log holds no game data.

## Ways to help

| | What |
|---|---|
| **Test on AMD and Intel GPUs** | Our test PCs are NVIDIA only. Reports from Radeon cards (RX 6000/7000/9000), Intel Arc and integrated GPUs, the Steam Deck and other Linux setups are the most useful thing you can send, even when everything works. |
| **Report what is broken** | A crash, a black or glitched picture, a stutter, a control that misbehaves. See *Reporting a problem* below. |
| **Suggest a feature** | Open an issue that says what you would like and why it matters to you. |
| **Play further** | Areas, cutscenes, items and menus we have not reached find problems we have not seen. |
| **Send a fix** | Fork, fix, test, open a pull request. Small, focused changes are the easiest to review. |
| **Improve the docs** | The [user guide](docs/USER_GUIDE.md), this page and the developer docs. Corrections and clearer steps are welcome. |
| **Join the Discord** | [discord.gg/34GV5hdC3Q](https://discord.gg/34GV5hdC3Q): help, test builds (pick *Tester* when you join) and development talk (*Developer*). Bugs still go to GitHub issues, so they are not lost. |

## Reporting a problem

1. Try the [newest release](https://github.com/Sacrappy/HeyListen/releases/latest) first, and search the
   [open issues](https://github.com/Sacrappy/HeyListen/issues): if yours is there, add your details to it.
2. [Open an issue](https://github.com/Sacrappy/HeyListen/issues/new) with:
   - the version (the release name, or the first line of `hookshot_log.txt`);
   - your GPU and driver version, CPU, RAM, and Windows or your Linux distribution;
   - where in the game it happened and what you did just before;
   - `hookshot_log.txt` from your game folder, attached right after the problem (each start writes a new one);
   - a screenshot or a short video for anything on screen.
3. Test without ReShade, overlays, shader-cache tools and frame-generation injectors when you report a graphics or
   performance problem: they change what the game does.
4. One problem per issue, in English please.

## Development

The developer documentation lives with the engine:

- [engine/docs/development.md](engine/docs/development.md): the build pipeline, every command and the switches for
  testing and debugging;
- [engine/docs/design.md](engine/docs/design.md): the architecture and the rules the GPU replay keeps;
- [engine/CONTRIBUTING.md](engine/CONTRIBUTING.md): the full development setup (Windows and Linux), the optional NVIDIA
  DLSS SDK, the builder and the checks, in detail;
- [engine/AGENTS.md](engine/AGENTS.md): what trips people up (tests read the source, the renderer's versioned interface,
  generated shader headers).

In short:

- You need your own supported dump: program `0400486024DEC000`, update v131072, build `e0f3ccfa`. A build needs about
  60 GB free.
- **Windows:** Python 3 from python.org, [llvm-mingw](https://github.com/mstorsjo/llvm-mingw) (`HOOKSHOT_MINGW`), and
  the tools the HeyListen Builder installs in `%LOCALAPPDATA%\HeyListenBuilder`. Build a game folder with
  `python -I engine/nx2/make_game.py --nup <your.nup> --out <folder>`.
- **Linux:** `engine/scripts/linux/deps.sh`, then `engine/scripts/linux/appimage.sh`, or the AppImage from the releases.
- **The builder** (Windows) is .NET 8 WPF: `dotnet build -c Release` in `engine/builder/HookshotBuilder`.

### Checks

The game-free checks need no dump and are what CI runs on every pull request:

```
cd engine
python -I -B tests/run_all.py
```

Add a game-free test with your fix where the behaviour can be checked without the game (`engine/tests/test_*.py` is
picked up by itself). For a fix in the renderer or the runtime, say what you saw before and after, on which GPU and
driver, and where in the game.

## Pull requests

1. Fork the repository and branch from `main`: `fix/...`, `feat/...`, `linux/...`, `builder/...`, `docs/...`.
2. One topic per pull request: a bug fix does not carry a refactor.
3. Title in the Conventional Commits form, as every commit: `type(scope): subject`, for example
   `fix(vk): the map keeps its transparency`, `feat(builder): mods chosen at install`. Types: `feat`, `fix`, `perf`,
   `docs`, `test`, `build`, `ci`, `refactor`, `chore`, `revert`. Details in
   [engine/docs/versioning.md](engine/docs/versioning.md).
4. Open the description with **why** the change is needed, in one or two plain sentences a player could follow. Then
   say what changed, how it was tested (GPU, driver, area, fps before and after), and link the issue.
5. Include screenshots when the change shows on screen: before and after for a fix.
6. CI must pass. Windows-side changes are tested in the game by the maintainer before they are merged.
7. No build output, dumps, generated files or game data. Check `git status` before you commit.

If you used an AI assistant, say so with `Assisted-by:` or `Co-Authored-By:` trailers.

## License

HeyListen is free software under the [GNU General Public License, version 3 or later](LICENSE). By submitting a change
you agree to license it under those terms. Only send code you can license that way: nothing from a project with an
incompatible license, and no decompiled or generated game code. Third-party parts keep their own notices
([THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)). NVIDIA's DLSS SDK is never in the repository.

Thanks for testing, reporting and sending fixes: every report from a different GPU moves the project forward.
