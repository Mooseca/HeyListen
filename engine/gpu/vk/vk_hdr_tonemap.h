// (heylisten) The HDR row's "Native + our tone mapper" (opts.hdr 3, vk_hdr_tonemap.cpp): the game's own tone-mapping pass —
// the full-screen draw that reads the final scene image and writes the HDR10 window image — done by our pass instead, with
// the game's exposure and our tone curve (peak brightness, paper white, saturation: the Insert menu's rows).
#pragma once

#include "vk_internal.h"

namespace mkwvk {

/// Whether our pass is to take the game's tone-mapping draws this frame (the HDR row on "Native + our tone mapper", the
/// game told it has an HDR10 display). The menu's value is read on the replay thread, where the draws are recorded
bool hdr_tonemap_wanted();
/// Whether key is the game's tone-mapping program: found by RX_VK_HDR_FIND (vk_draw.cpp), known only by its key — the pass
/// that samples the final scene image (a float image the game's own pass reads) and writes the HDR10 window image.
/// RX_VK_HDR_TM_KEYS=<key prefixes,...> (default the one found; "-": none, the game's pass is kept) is the way to name
/// another, if a game update changes the shader
bool hdr_tonemap_key(uint64_t key);
/// Our pass, recorded where the game's draw was: scene (the image its pass samples, any size the target's) into out (w x h,
/// the game's HDR10 window image, PQ codes), the game's own uniform buffer bound as its pass has it (the exposure word
/// comes from there). false: ours could not be made, and the game's draw is kept as it was
bool hdr_tonemap_record(VkCommandBuffer cmd, uint64_t key, VkImageView scene, VkImageView out, uint32_t w, uint32_t h,
                        const VkDescriptorBufferInfo& uniforms);

}  // namespace mkwvk
