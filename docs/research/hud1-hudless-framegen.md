# HUD1: HUD-less pictures for frame generation (2026-11-24)

Branch `feat/fg-hudless` (worktree `E:/OOT/HeyListen-wt/hud1`), from `docs/fg1` (main `5a5662a5b` plus the FG1 study,
`docs/research/fg1-frame-generation.md`). A port by behaviour of Longshot's HUD-less chain (#1464, #1691, #1487, #1538, #1755);
every step behind a switch that is off by default.

## State

- [x] Step 1: HUD-less capture at the gameplay upscale dispatch, `RX_VK_FSR_FG_HUDLESS` (code and test done; commit below)
- [ ] Step 2: FSR 3.1 interpolates the HUD-less colour, the presented frame beside it
- [ ] Step 3: HUD layer fit and lay-over, `RX_VK_FSR_FG_HUD_LAYER`
- [ ] Step 4: the same pair for the built-in interpolator, `RX_VK_FG_HUDLESS`
- Not touched on purpose: DLSS-G, FSR 4 (the brief), Native HDR's PQ present (falls back to the presented picture), PsychoV35's
  RGBA16F picture (not copied: another encoding than the frame's).

## Step 1: the capture

- `vk_draw.cpp` `upscale_picture()` finds the gameplay upscale's output (as `temporal_stand_in` does; at 100% render resolution
  the known gameplay pass writes the scene's own size, Longshot #1691), the dispatch calls `framegen_hud_before()` after whichever
  drew it: the game's own network, FSR 3.1's, the temporal chain's, the Upscaler Off pass, the TAAU stand-in, and the stub
  (`upscale_stub`'s `stub_picture`).
- `vk_framegen.cpp` `framegen_hud_before()` copies the B10G11R11 picture into one of two images (`hud.before[k]`), `hud_source()`
  takes it as the present's own when it is fresh, still the picture it was copied from (`texture_alive`, new in vk_texture.cpp)
  and the presented picture's size. A present with no copy (menus, movies, loading) takes nothing and goes on as before.
- Nothing consumes the copy yet: with the switch on, step 1 changes no picture, it only counts (the 600-present `fsr3fi` line says
  how many presents had the picture from before the HUD).
- Test: `engine/tests/test_fsr3fi_hud_capture.py`.
