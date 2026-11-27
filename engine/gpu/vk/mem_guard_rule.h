// Copyright (C) 2026 Sacrappy
// (HeyListen, LAP2) Where the memory guard (vk_ram_guard.cpp) is on: nothing of Vulkan here, tests/mem_guard_rule_test.cpp.
//
// The guard keeps descriptor pools (and, with RX_VK_MEM_GUARD_BLOCKS=1, memory blocks) from being asked of the driver when the
// heaps the GPU reaches are at their ceiling: AMD's Windows driver (amdvlk64.dll 31.0.21925.1001) aborts the process (0xc0000409) in
// vkCreateDescriptorPool then. It is a Windows driver's bug on a GPU whose memory is the PC's RAM, so by default it is on for an
// integrated AMD GPU on Windows, the pools only. "Integrated" is the driver's own word: VkPhysicalDeviceType INTEGRATED_GPU (the Ryzen
// APUs, the Steam Deck's and the ROG Ally's, report it). A Radeon that reports DISCRETE_GPU (any card with its own memory), and an APU a
// driver reports as discrete or other, are not matched: RX_VK_MEM_GUARD=1 (RX_VK_MEM_GUARD_POOLS=1) turns it on for them.
//   RX_VK_MEM_GUARD       1: pools and blocks, anywhere   0: nothing, anywhere   unset: the rule above (pools)
//   RX_VK_MEM_GUARD_POOLS / RX_VK_MEM_GUARD_BLOCKS   1 / 0: that part on / off, whatever the above says
#pragma once
#include <cstdint>
#include <cstdlib>

namespace mem_guard {

constexpr uint32_t kVendorAmd = 0x1002;

/// an environment switch: -1 unset (or empty), else 0 or 1
inline int env_switch(const char* v) { return !v || !*v ? -1 : (std::atoi(v) != 0 ? 1 : 0); }

/// the rule's own choice for this GPU, with no switch set
inline bool automatic(uint32_t vendor_id, bool integrated, bool windows) { return windows && integrated && vendor_id == kVendorAmd; }

struct Rule {
    bool pools = false;       // descriptor pools not made at the ceiling
    bool blocks = false;      // memory blocks not asked at the ceiling (and the textures' budget cut with them)
    bool automatic = false;   // the rule turned the pools on (no switch did)
    bool on() const { return pools || blocks; }
};

/// master, pools_env, blocks_env: env_switch of RX_VK_MEM_GUARD, RX_VK_MEM_GUARD_POOLS, RX_VK_MEM_GUARD_BLOCKS
inline Rule decide(uint32_t vendor_id, bool integrated, bool windows, int master, int pools_env, int blocks_env) {
    Rule r;
    const bool rule = automatic(vendor_id, integrated, windows);
    const bool pools_from_master = master == 1 ? true : master == 0 ? false : rule;
    const bool blocks_from_master = master == 1;   // (blocks never by the rule)
    r.pools = pools_env >= 0 ? pools_env == 1 : pools_from_master;
    r.blocks = blocks_env >= 0 ? blocks_env == 1 : blocks_from_master;
    r.automatic = r.pools && master < 0 && pools_env < 0;
    return r;
}

}  // namespace mem_guard
