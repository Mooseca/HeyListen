# HUD1: HUD-less pictures for frame generation (2026-11-24)

Branch `feat/fg-hudless` (worktree `E:/OOT/HeyListen-wt/hud1`), from `docs/fg1` (main `5a5662a5b` plus the FG1 study,
`docs/research/fg1-frame-generation.md`). A port by behaviour of Longshot's HUD-less chain (#1464, #1691, #1487, #1538, #1755);
every step behind a switch that is off by default.

## State

- [x] Step 1: HUD-less capture at the gameplay upscale dispatch, `RX_VK_FSR_FG_HUDLESS` (code and test done; commit below)
- [x] Step 2: FSR 3.1 interpolates the HUD-less colour, the presented frame beside it (code, test, run_all done; pictures pending)
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

## Step 2: FSR 3.1 takes the HUD-less colour

- `shaders/fg_hud.comp` (new, header `fg_hud_comp_spv.h` made by `tests/test_fsr3fi_hudless_colour.py --write`): the picture before the
  HUD, cropped as the frame, equal to the presented frame's pixel wherever nothing was drawn over the picture and sRGB-encoded
  under the HUD (the picture is linear B10G11R11, the frame RGBA8 sRGB: taken as it was, FSR 3.1 found the two different everywhere
  and every made frame was the presented one, Longshot #1538).
- `vk_fsr3fi.h/.cpp`: `Inputs::present` (the presented frame; null: one colour as before). With it `hudless_attached_factor` is 1,
  binding 2 of the inpainting pass is the presented frame (binding 3 stays the HUD-less colour), and the history is reset when the
  kind of source changes (a present with the picture after one without).
- `vk_framegen.cpp` `hud_source()` copies the picture as presented at the present (`hud.after[k]`), runs the pass, `fsr3fi_frame`
  hands the result to FSR 3.1 as `color` and the presented frame as `present`.
- Not ported: Longshot's patched AMD passes (FI_PATCHES: the alpha mark of #1464, the overlay factor of 1 where the two differ of
  #1538): this tree's AMD shaders are AMD's own and are not regenerated. The factor AMD's pass computes grows with the difference, so
  soft HUD edges may be laid partly; the HUD layer of step 3 replaces that lay-over.
- Test: `engine/tests/test_fsr3fi_hudless_colour.py` (and `test_psychov35_fsr3_fg.py`'s fixture follows `present` and `hudless`).
