// (heylisten) The HDR row's "Native + our tone mapper" (vk_menu.cpp: opts.hdr 3): the game's tone-mapping pass replaced by
// ours. The game, told it has an HDR10 display (vk_replay.cpp hdr_game_native), renders its final scene image as the float
// light it is and tone-maps it to the window's PQ image itself: a colour matrix (Rec. 709 in, Rec. 2020 nits out, the display
// white it was told — and whatever else its CPU folds into it, its exposure — baked in) then ST 2084 PQ. Its map is linear,
// so the light above what the matrix makes of the picture's white runs straight past what the display shows (measured: its
// brightest highlight ~260 nits, nothing rolled toward a brighter display's range). Our pass, in that draw's place, keeps the
// pass's own inputs — the same scene image, the same constants (its colour matrix, read where its shader reads it) — and
// adds the curve the game's lacks: BT.2390's EETF rolls the light above its knee to the player's peak brightness, the
// saturation the player's (shaders/hdr_tonemap.comp, our own shader from the published curves). Under the knee the picture
// is the game's own native HDR, so the paper white (the row tells the game, the game's matrix carries it) and the game's
// exposure policy hold as they are; above it our curve takes over. The game's draw is kept for SDR and the other modes, and
// taken back without a word if ours cannot run (another kind of target, no 10-bit storage): the game's pass then draws
// exactly as it would have.
// The draws this replaces are found by the program's key alone (RX_VK_HDR_FIND=1 says it, with the images and uniform
// buffers: nothing of the game's shader is read or kept by us).
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>

#include "vk_hdr_tonemap.h"
#include "vk_draw.h"   // (extern_guarded_shader_module, extern_guarded_compute)
#include "vk_menu.h"   // (opts.hdr_white, opts.hdr_peak, opts.hdr_saturation)
#include "vk_texture.h"

#include "shaders/hdr_tonemap_comp_spv.h"
#include "vk_work.h"   // (after the others: counts the commands that do GPU work, for full_barrier)

namespace mkwvk {
bool hdr_game_native();   // (vk_replay.cpp: the game is told it has an HDR10 display and its PQ picture is taken as it is)

namespace {

/// Our pass's pipeline: a sampled scene image, the PQ image written, and the game's own uniform buffer of the pass bound as
/// its fragment stage had it. Push descriptors, as the framegen passes do; a GPU without them keeps the game's draws
bool pipe_make(VkPipeline& pipe, VkPipelineLayout& layout, VkSampler& scene_sampler) {
    const auto undo = [&] {
        if (pipe) vkDestroyPipeline(dev.device, pipe, nullptr);
        if (layout) vkDestroyPipelineLayout(dev.device, layout, nullptr);
        if (scene_sampler) vkDestroySampler(dev.device, scene_sampler, nullptr);
        pipe = VK_NULL_HANDLE, layout = VK_NULL_HANDLE, scene_sampler = VK_NULL_HANDLE;
        return false;
    };
    if (!dev.push_descriptor || !vkCmdPushDescriptorSetKHR) return false;
    const VkDescriptorSetLayoutBinding b[3] = {{0, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},
                                              {1, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr},
                                              {2, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr}};
    VkDescriptorSetLayoutCreateInfo li{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    li.flags = VK_DESCRIPTOR_SET_LAYOUT_CREATE_PUSH_DESCRIPTOR_BIT_KHR;
    li.bindingCount = 3, li.pBindings = b;
    VkDescriptorSetLayout set = VK_NULL_HANDLE;
    if (vkCreateDescriptorSetLayout(dev.device, &li, nullptr, &set) != VK_SUCCESS) return undo();
    const VkPushConstantRange pr{VK_SHADER_STAGE_COMPUTE_BIT, 0, 16};
    VkPipelineLayoutCreateInfo pi{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    pi.setLayoutCount = 1, pi.pSetLayouts = &set, pi.pushConstantRangeCount = 1, pi.pPushConstantRanges = &pr;
    if (vkCreatePipelineLayout(dev.device, &pi, nullptr, &layout) != VK_SUCCESS) {
        vkDestroyDescriptorSetLayout(dev.device, set, nullptr);
        return undo();
    }
    vkDestroyDescriptorSetLayout(dev.device, set, nullptr);   // (the pipeline layout keeps its own copy)
    VkShaderModuleCreateInfo mi{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
    mi.codeSize = sizeof HDR_TONEMAP_COMP_SPV, mi.pCode = HDR_TONEMAP_COMP_SPV;
    VkShaderModule m = VK_NULL_HANDLE;
    IntelDriverGate gate;
    if (extern_guarded_shader_module(&mi, &m) != VK_SUCCESS) return undo();
    VkComputePipelineCreateInfo ci{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    ci.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    ci.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    ci.stage.module = m;
    ci.stage.pName = "main";
    ci.layout = layout;
    const VkResult r = extern_guarded_compute(VK_NULL_HANDLE, &ci, &pipe);
    vkDestroyShaderModule(dev.device, m, nullptr);
    if (r != VK_SUCCESS) return undo();
    VkSamplerCreateInfo si{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
    si.addressModeU = si.addressModeV = si.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    si.maxLod = 0.25f;
    if (vkCreateSampler(dev.device, &si, nullptr, &scene_sampler) != VK_SUCCESS) return undo();
    logf("vk: HDR: our tone-mapping pass ready (shaders/hdr_tonemap.comp)");
    return true;
}

}  // namespace

bool hdr_tonemap_wanted() { return opts.hdr == 3 && hdr_game_native(); }

bool hdr_tonemap_key(uint64_t key) {
    // (the pass found with RX_VK_HDR_FIND: the program that samples the final scene image and writes the HDR10 window image.
    // RX_VK_HDR_TM_KEYS=<key prefixes,...>, "-": none, for a game update whose shader has another key)
    static const char* keys = getenv("RX_VK_HDR_TM_KEYS") ? getenv("RX_VK_HDR_TM_KEYS") : "dbb1015dd9fcec75";
    char hex[24];
    snprintf(hex, sizeof hex, "%016llx", (unsigned long long)key);
    for (const char* q = keys; *q;) {
        const char* e = q;
        while (*e && *e != ',') e++;
        if (e > q && *q != '-' && !strncmp(hex, q, (size_t)(e - q))) return true;
        q = *e ? e + 1 : e;
    }
    return false;
}

bool hdr_tonemap_record(VkCommandBuffer cmd, uint64_t key, VkImageView scene, VkImageView out, uint32_t w, uint32_t h,
                        const VkDescriptorBufferInfo& uniforms) {
    static VkPipeline pipe = VK_NULL_HANDLE;
    static VkPipelineLayout layout = VK_NULL_HANDLE;
    static VkSampler scene_sampler = VK_NULL_HANDLE;
    static bool tried = false;   // (read as made; only the making is behind the lock)
    if (!tried) {
        static std::mutex mu;
        std::lock_guard lk(mu);
        if (!tried) tried = pipe_make(pipe, layout, scene_sampler);
    }
    if (!tried || !scene || !out || !uniforms.buffer || !w || !h) return false;
    // (the paper white is not here: it reaches the picture through the game's own colour matrix — the white the game was
    // told, HOS_OPT_HDR_WHITE, baked in by its CPU — which our curve takes the colour through as the game's pass does)
    const struct {
        float peak, saturation, pad0, pad1;
    } pc{(float)std::clamp(opts.hdr_peak, 400, 10000), std::clamp(opts.hdr_saturation, 50, 150) / 100.0f, 0.0f, 0.0f};
    const VkDescriptorImageInfo ii[2] = {{scene_sampler, scene, VK_IMAGE_LAYOUT_GENERAL},
                                         {VK_NULL_HANDLE, out, VK_IMAGE_LAYOUT_GENERAL}};
    const VkWriteDescriptorSet ws[3] = {
        {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, nullptr, 0, 0, 0, 1, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, &ii[0], nullptr, nullptr},
        {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, nullptr, 0, 1, 0, 1, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, &ii[1], nullptr, nullptr},
        {VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, nullptr, 0, 2, 0, 1, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, nullptr, &uniforms, nullptr}};
    vkCmdBindPipeline(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, pipe);
    vkCmdPushDescriptorSetKHR(cmd, VK_PIPELINE_BIND_POINT_COMPUTE, layout, 0, 3, ws);
    vkCmdPushConstants(cmd, layout, VK_SHADER_STAGE_COMPUTE_BIT, 0, sizeof pc, &pc);
    vkCmdDispatch(cmd, (w + 7) / 8, (h + 7) / 8, 1);
    static std::atomic<int> logged{0};
    if (logged.fetch_add(1, std::memory_order_relaxed) == 0)
        logf("vk: HDR: the game's tone-mapping pass (program %016llx) replaced by ours: its own light under the knee, "
             "the highlights rolled off to the peak %d nits, the saturation %d%%",
             (unsigned long long)key, (int)pc.peak, (int)std::lround(pc.saturation * 100));
    return true;
}

}  // namespace mkwvk
