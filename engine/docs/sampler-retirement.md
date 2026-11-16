# Samplers: sharing, retirement and the count

A driver makes only so many samplers (`maxSamplerAllocationCount`: NVIDIA's about 4000, NVK's 4096). The renderer made one
for each sampler state it met and never destroyed any, and every Anisotropic filtering, Render resolution or Upscaler change
made a new set on top. Past the limit `vkCreateSampler` fails. This is one of the suspects for HeyListen issue 30 (a frame
rate that falls over a long session); whether a session reaches the limit is read from the log (below), not assumed.

The rule (`gpu/vk/vk_draw.cpp`, the samplers' section; ported from Longshot #442):

- **Sharing.** Keys whose Vulkan create info is equal in everything a sample reaches (`SamplerInfo`) share one sampler.
- **Room.** `sampler_room()` keeps the samplers made, and the retired ones the GPU may still use, under the driver's limit less 64
  (a quarter of a smaller limit), for the renderer's other samplers and an upscaler SDK's.
- **Retirement.** From 3/4 of the room each new sampler first retires the least recently resolved one. A retired sampler leaves
  every table at once: the book's keys, each thread's `mine`, `sampler_for`'s tables, the texture slots (`TexSlot::samp_retired`) and
  the descriptors kept by reuse (`samplers_changed()`). No descriptor made after it can name it.
- **Destruction.** A retired sampler is destroyed once the timeline reaches `vk_retirement_value()` taken at its retirement: a
  signal that follows every recording made so far, parallel segments included (the same rule the Longshot port gave the
  upscaler's images). Nothing is destroyed while the GPU may still read it.
- **Recency.** Near the limit (from half the retiring point) the threads' tables, and the texture slots, last one present, so the
  book sees each sampler in use once a present and the one retired is the least recently used.
- **Full.** When the made and the retired-but-not-yet-destroyed fill the room, nothing is made: the key that needs a new sampler
  fails for that present (one attempt a key and present, a log line, 8 at most) and is retried at a later one.

The count is in the periodic `vk: VRAM:` line (every 600 presents): `samplers N made (the device allows L), W retired waiting for the
GPU, R retired and D destroyed so far`. A session that stays under 3/4 of the room shows R = 0. The first retirement and every
1000th are logged as `vk: samplers: ... the least recently used retired`.

Check: `python -I -B tests/test_sampler_retirement.py --cxx <clang++> --headers <Vulkan include folder>` runs the section's code
against a modeled driver of 80 samplers and a modeled timeline (no GPU, no game).
