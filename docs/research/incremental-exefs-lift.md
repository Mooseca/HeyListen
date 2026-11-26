# Retranslate only the functions an exeFS patch touches

Status: design only, nothing implemented. Written 2026-11-16 against `main` c1adfed3. Read: `engine/nx2/make_game.py`
(`lift_key`, `apply_code_mods`, the lift and compile steps of `main`), `engine/nx2/lift.py`, `chunks.py`, `split_hot.py`,
`engine/nx2/exefs_mods.py` (`patched_functions`), `engine/third_party/a64-kit/lift/a64_lift.py`, `hos/nx_image.py`, `engine/nx2/build.py`
(`object_key`). No timing was measured for this note; where a gain depends on one, the note says what to measure.

## Where the time goes today

A code mod changes bytes of the work copy of the modules, so `lift_key` (it hashes the exefs files) changes and the whole
lift runs again: image, discovery of every function, the emit of every function, the post passes, `split_hot.py`. The
compile is already incremental: `build.py` keys an object by `sha1(source + flags + headers)` in `work/objcache`, so a chunk
whose C text is byte-identical is never compiled twice, and the chunk boundaries are guest addresses (`chunks.txt`), so a
function that changes stays in its chunk. The two things to save are therefore:

1. the lift's time (the 9 minutes of "translation" in `CodeMods.RebuildAbout`), and
2. the compile of chunks that did not need it. This one is saved by the cache as soon as the text of the untouched chunks is
   byte-identical, which the lift already produces; the work is to *prove* it, and to keep the baseline around (below).

A patch writes in place (offsets inside .text/.rodata/.data, never past the module), so no guest address moves.

## What a function's C text depends on

`emit_function(e)` is a function of: the body of `e` (the instructions `walk(e)` reaches, stopping at other entries), its labels,
the jump tables of its `br`s (`L.jt`), which branch targets are entries (goto or tail call: `transfer`, `dead_flags`,
`dirty_regs`), the PLT stubs its `bl` targets resolve through (`callee`, read from the GOT slot in .data), the HLE hooks, the
setjmp owners, the words of its instructions (and their pc for pc-relative ones), and the hooks of `oot_wide`, `oot_jitter`,
`oot_occlusion` keyed by pc. The instruction-translation texts are per word, shared and pure. `dead_flags` and
`dirty_regs` look only at the function itself. The data the lifter reads at lift time is small and named: jump-table entries
(`img.read(table + i*size)`), PLT GOT slots (`plt_target`), and, for the entry set, `.eh_frame` function starts, the dynamic
symbols, the relocations that point into code (RELATIVE and ABS64 values), `DT_INIT/FINI`, the init arrays, every `bl`
target in .text, and the code addresses `adr_entries.py` finds. Everything else in .rodata/.data is read by the running game
from `image.bin`, which is rewritten by every lift in any case, so a patch to plain data needs no retranslation at all.

## Part 1: how the lift could retranslate only the touched functions

The baseline is the lift of the same game, tools and environment without the patches (the lift key computed on
`.hookshot_exefs`). The patched run keeps three things from it, as a small **manifest** written next to `sa/gen` by every lift:

- per function: address, the chunk file it went to, `sha1` of its final text, its refs, the pc range of its body, and the
  table byte ranges and GOT slots it read;
- the global inputs as fingerprints: the entry set, `eh_starts`, hooks, the PLT map, the jump-table map, the setjmp owners,
  the instruction-translation header `a64_fpx.h` (it lists the guard shapes any instruction used);
- per chunk file: the object key `build.py` used for it (so an untouched chunk can be linked without its text).

Steps of the patched build:

1. Build the patched image (`EdenImage`, cheap compared with the emit) and recompute the global fingerprints. If any differs
   from the manifest, the patch changed what the lifter derives globally: **full lift** (next section).
2. Seeds: the functions whose body pcs intersect the patched ranges (the build already has the ranges and
   `patched_functions`); the functions whose recorded table range or GOT slot intersects them; for a patched PLT stub, its
   callers (`callee` maps through it).
3. Closure: the seeds, plus every function whose body contains a seed's entry or shares code with it (the lifter lets bodies
   overlap, `affected = {e for e ... if pc in body}`), from an inverted index pc -> functions made from the manifest.
4. Dirty chunks = the chunk files holding the closure. **Re-lift those whole chunks**, not single functions: walk and emit every
   function whose address lies in a dirty chunk's address range (`chunks.txt` gives the range), with the same `Lifter`, the same
   `chunks.write` boundaries and `split_big` rule, then the same post passes on those files only: `poll`, `group_marks`,
   `oot_patches`, `hl_gates.apply(skip=patched)`. Whole chunks keep the preamble (declarations), the part splits and the
   byte layout identical to a full lift, and need no baseline text: the manifest is enough, so the baseline `sa/gen` (about a
   gigabyte) can still be freed after the build as `Storage.Freeable` does today.
5. The other chunks are not written. `build.py` is told their object keys from the manifest and restores the objects from
   `objcache` (the cache is kept after a build; `Storage` keeps it on purpose). A missing object, or a missing manifest, is
   the full-lift case.
6. Hot functions: `code_hot.c` is one file split into 8 pieces by `split_hot.py` along the call graph. A patch in a hot
   function dirties the hot file; the split must keep each function in its old piece (record the piece in the manifest, as
   `chunks.txt` does for chunks) or all 8 -O2 pieces, the slowest part of the compile, would move. Without that, a patched
   hot function is the case where the saving is small, and it is the first thing to measure.
7. The lift key: the patched build writes the key of its own exefs as today, plus the baseline key it derived from, so the next
   build (a different mod set) starts from the same baseline, never from another patched build.

The lift work saved is the emit and walk of the untouched chunks (the dominant part of the translation) and the writing
of about a gigabyte of C; image construction, entry derivation and the translation of the distinct instruction words of
the dirty chunks remain. What the compile saves is what the cache already saves, now guaranteed. Measure first: time of
image+fingerprints, emit per chunk, and how many chunks a typical mod (a few functions) dirties.

## When the build must fall back to the full lift

Any one of these, tested by comparing the patched image with the manifest, not by reading the patch:

- **The entry set changed** (a patch that adds a `bl` or `b` to a target that was not an entry, a reloc or init-array pointer
  in .data now pointing into code, a changed `.eh_frame`/dynsym/dynamic entry). A new entry splits an existing function at
  that point and turns gotos into tail calls in every function that branched there. The closure in step 3 covers this in
  principle, but the first version should not: it adds a new function (a patch writing new code into padding or an unused
  area, reached by a new `bl`) and moves nothing else only when the fingerprint says so.
- **A jump table changed**: any table entry or bound read by `jump_table` now differs, a `br` that had a table has none
  (or the reverse), or a table the lifter could not resolve before now resolves. The second pass of `discover` re-walks
  functions because of newly resolved tables, so this is the same global effect.
- **The GOT/PLT map changed** (a patched slot or a stub).
- **The patch touches rtld, sdk or the header segment** that `nx_image` reads for relocation and symbols: always full (these
  modules are small to patch and rare to mod, and the derivation reads them whole).
- **`a64_fpx.h` differs** (a new floating-point guard shape): every chunk includes it and its hash is in every object key.
- **The setjmp owner set changed** (callers elsewhere wrap their calls).
- **The baseline is unusable**: no manifest, a key that does not match tools/environment (`lift_key` without the exefs part),
  a missing object, a manifest from a build that failed.
- **Too much is dirty**: the closure covers more than a threshold of chunks (start at 30%): the gain is gone and the
  incremental path is the one more thing to go wrong.
- **A post pass cannot be applied to a part**: `oot_patches` insists on finding its output-size places in the whole lift
  (`required=` only for the supported build); an incremental run must either know those edits are in untouched chunks
  (the manifest records which chunk holds each) or fall back.

A patch that only changes data (constants, strings, tables the game reads at run time) falls in none of these and dirties
nothing: the build rewrites `image.bin` and compiles nothing. A patch that rewrites instructions in place, without new
branch targets, is the target case.

## How to prove the output for untouched functions is byte-identical

Three layers, cheapest first; the first two do not need the game in CI.

1. **A differential test against the full lift, on a synthetic image.** `tests/test_exefs_mods.py` already builds NSO files and
   patches; the same approach, with a small image whose code is written in the test (a few functions, a jump table, a PLT
   stub, a shared tail), lifts it twice: baseline, then patched both ways, full and incremental. Assert that **every file
   of the incremental output is byte-identical to the full lift of the patched image** (chunks, `a64_table.c`, `functions.txt`,
   the manifest). That is stronger than "untouched functions are unchanged" and is the property the build needs. Cases:
   an in-place instruction edit; an edit inside a shared tail; a patched jump-table entry; a patched GOT slot; a data-only
   patch (nothing dirty); a new `bl` (must fall back, asserted by the reason it gives); a patch in a hot function. The
   existing `test_parallel_emit.py` is the model: it already asserts the forked emit equals the one-process emit byte for byte.
2. **A per-function ledger, checked on the real game by whoever has one.** The manifest's per-function `sha1` makes a second
   assertion cheap: after a *full* lift of the patched game (a local script, run once per change to the lifter, never in CI), the
   set of functions whose hash differs from the baseline must be a subset of the closure the incremental path computed. A
   function outside the closure that changed means a dependency missing from section "What a function's C text depends
   on", and is a bug in the closure, not in the patch.
3. **A guard inside the build.** With an environment switch (for the first releases, on for any bug report), the build runs
   the full lift beside the incremental one into a second folder and compares the file lists and `sha1`s before the compile;
   a difference fails the build with the file names and keeps the full-lift result. The check costs the lift the feature saves
   once, so it is a switch and not the default; the same comparison is what layer 2 runs.

At run time nothing depends on the proof: if the incremental lift is wrong the symptom is a missing or wrong function in a
chunk, which the link (undefined or doubly defined `f_xxxxxxxx`) and `lifted_cut_short` already catch, and the build's failure
path forgets the lift key and the objects, so the next build is a full one.

## Conclusion

The compile is already incremental by content; the saving is in the lift, and it is real only for patches that rewrite
instructions in place without changing the entry set, the jump tables or the GOT: the fingerprint comparison decides, not the
patch's size. The design re-lifts whole dirty chunks from a small manifest, so no gigabyte of baseline C has to be kept, and
falls back to the full lift on any change to what the lifter derives globally. The risky parts are the hot pieces (stable
piece assignment) and the post passes that today see the whole lift. Build the synthetic differential test (layer 1) first:
it fixes the contract (incremental output equals full output) before any lifter code changes.
