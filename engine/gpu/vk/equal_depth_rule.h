// Copyright (C) 2026 Sacrappy
// The depth margin a colour pass's EQUAL test gets (vk_draw.cpp dynamic_state): which GPUs have it by default.
// The rule is after tiktiki's (Longshot 03a6e8d0e, #1801: discrete Battlemage, 0xE2xx) and twisted89's (Longshot 641030ed9, #2299:
// Lunar Lake, 0x64xx) policy_rule::equal_depth_bias; this tree has no device_policy.h, so it sits here, on its own, to be tested.
// tests/test_equal_depth_rule.py
#pragma once
#include <cstdint>

namespace equal_depth_rule {

/// Intel's PCI vendor id
inline constexpr uint32_t kIntel = 0x8086;
/// The margin, in depth-bias units towards the camera, an EQUAL colour pass test gets by default (0: as the game asks).
/// The game draws a depth prepass, then colour passes that test EQUAL against it with another program, and Intel's compiler does
/// not give two programs the same position to the last bit: the ground came out in holes (issue 17, Arc B390), so every Intel GPU
/// has 64 units of margin (the test becomes LESS_OR_EQUAL). But the margin also passes every fragment in front of the prepass:
/// where the prepass cut a leaf away, the trunk behind it holds the depth, and the colour pass draws the whole quad over it, the
/// alpha-tested foliage as solid blocks. On Intel's Windows driver that showed on discrete Battlemage (0xE2xx, Arc B570 / B580:
/// fallen leaves, flowers, Link's hair, pine cards, Hyrule Field's billboards; Longshot issue 1413) and on Lunar Lake (0x64xx,
/// Arc 140V, driver 101.8991: Kokiri Forest's ivy, leaves and grass; the ground has no holes with the game's EQUAL there).
/// Those two have 0 on that driver. Other Intel GPUs and drivers (Mesa's included, as before) keep 64, and every other vendor 0.
/// intel_windows_driver: VK_DRIVER_ID_INTEL_PROPRIETARY_WINDOWS. RX_VK_EQ_BIAS (the caller) decides over this.
inline float default_margin(uint32_t vendor_id, uint32_t device_id, bool intel_windows_driver) {
    if (vendor_id != kIntel) return 0.0f;
    if (intel_windows_driver && ((device_id & 0xFF00u) == 0xE200u || (device_id & 0xFF00u) == 0x6400u)) return 0.0f;
    return 64.0f;
}

}  // namespace equal_depth_rule
