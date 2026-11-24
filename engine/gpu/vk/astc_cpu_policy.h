// Copyright (C) 2026 Sacrappy
// Which GPUs decode ASTC on the CPU by default, when RX_VK_ASTC_CPU is not set (vk_texture.cpp astc_cpu_wanted).
// tests/test_astc_cpu_policy.py
#pragma once
#include <cstdint>

namespace astc_cpu_policy {

// On Windows, AMD's integrated GPUs (vendor 0x1002, device type INTEGRATED_GPU): the Ryzen 7000/9000 desktop CPUs' 2-CU graphics
// (Longshot's #489) and the APUs' larger ones. Issue 127: on an Xbox Ally X (Radeon 890M, driver 26.10.1) the driver reset the GPU
// while a save loaded, in a burst of GPU ASTC decodes (491 ms of uploads in one frame); the CPU decode fixed it. The two Ryzen
// device ids stay named whatever type the driver reports. Not other vendors, not AMD's discrete cards, not off Windows.
inline bool by_default(bool windows, uint32_t vendor_id, uint32_t device_id, bool integrated) {
    if (!windows || vendor_id != 0x1002) return false;
    return integrated || device_id == 0x164E || device_id == 0x13C0;
}

} // namespace astc_cpu_policy
