// Copyright (C) 2026 Sacrappy

// The VRAM allowance as the renderer's rules take it (Longshot #1091's vram_compact::past_allowance, on its own here).
#pragma once
#include <cstdint>

namespace vram_allowance {
/// An allowance the driver gives as the count itself is past: AMD's Windows driver, once a process is over what it allows, reports
/// the allowance as what the process uses (an RX 6600 at 5940 of 5940 MB). Taken as it is, every give-back rule saw the count within
/// it while the driver paged (frames of 1-15 s). Within kAtCount of the count it is taken a tenth under the count, so the rules give
/// back until the driver says again how much it allows. An allowance under the count is past already and stays; 0 (unknown) too
inline constexpr uint64_t kAtCount = 16ull << 20;
inline constexpr uint64_t kPastShare = 10;
inline uint64_t past_allowance(uint64_t used, uint64_t allowed) {
    if (!allowed || allowed + kAtCount < used || allowed > used + kAtCount) return allowed;
    return used - used / kPastShare;
}

/// (Longshot 8941d01b4, #2082) A floor under the textures' budget as the rules may hold it: none once the driver's count is past its
/// allowance. There the driver pages VRAM out to system memory and every frame reads some of it over PCIe, which costs more than
/// textures made again: a GTX 1060 6 GB (Longshot #939) sat at 6128 MB of the 5231 it allowed with 1606 MB of textures, under the
/// floor of Longshot's texture cache, so no rule could take one, and Hyrule Field went from 31 to 14 fps until a restart. Past the
/// allowance what stays is the textures the last presents drew from (vk_texture.cpp texture_frame's `recent`) and the eviction's own
/// 60 presents; within it the floor keeps the working set from a downward ratchet. 0 (no allowance known): the floor as it is
inline uint64_t floor_within(uint64_t floor, uint64_t used, uint64_t allowed) { return allowed && used > allowed ? 0 : floor; }
/// The floor of the TICK-023 rule (vk_texture.cpp texture_frame: the process held to RX_VK_VRAM_TARGET_PCT of the allowance, the
/// textures getting what the rest leaves, but not below 1 GB). Longshot's other floors (its 1800 MB texture_min_floor, the dynamic
/// floor, the compaction's hold) do not exist here; this is the one the textures' budget has
inline constexpr uint64_t kTargetFloor = 1024ull << 20;
inline uint64_t target_floor(uint64_t used, uint64_t allowed) { return floor_within(kTargetFloor, used, allowed); }
} // namespace vram_allowance
