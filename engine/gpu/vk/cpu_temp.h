// (HeyListen, Linux) The full FPS overlay's CPU temperature (vk_perf.cpp) from the kernel's hwmon files, which Windows has no
// equivalent of without a driver:
//   /sys/class/hwmon/hwmon*/name         "k10temp" (AMD) or "coretemp" (Intel)
//   /sys/class/hwmon/hwmon*/temp*_input  millidegrees: k10temp's whose label is "Tctl", coretemp's "Package id 0" (the
//                                        package; its other inputs are the cores), else temp1_input
// The file is found once (open, k10temp before coretemp, the lowest hwmon number first); a sample reads only it at the
// sampler's half-second cadence. A file missing or unreadable leaves the temperature at -1 (the overlay's empty cell).
// Pure, no Vulkan: tests/test_cpu_temp.cpp builds a fake sysfs tree.
#pragma once
#include "amdgpu_stats.h"   // (its file readers, amdgpu_stats::detail)

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

namespace mkwvk::cpu_temp {

struct Files {   // ("": not there)
    std::string hwmon;   // ("hwmon2")
    std::string name;    // ("k10temp")
    std::string temp;    // its temp*_input
    bool any() const { return !temp.empty(); }
};

// sysroot: "/sys" (a test passes its fake tree)
inline Files open(const std::string& sysroot) {
    namespace fs = std::filesystem;
    namespace d = amdgpu_stats::detail;
    std::vector<std::pair<long, fs::path>> nodes;   // (hwmon number, its directory)
    std::error_code ec;
    for (fs::directory_iterator it(fs::path(sysroot) / "class/hwmon", ec), end; !ec && it != end; it.increment(ec)) {
        const std::string n = it->path().filename().string();
        if (n.size() <= 5 || n.compare(0, 5, "hwmon") || n.find_first_not_of("0123456789", 5) != std::string::npos) continue;
        nodes.emplace_back(std::strtol(n.c_str() + 5, nullptr, 10), it->path());
    }
    std::sort(nodes.begin(), nodes.end());
    for (const char* want : {"k10temp", "coretemp"}) {
        const std::string label_want = std::string(want) == "k10temp" ? "Tctl" : "Package id 0";
        for (const auto& [num, h] : nodes) {
            std::string name;
            if (!d::read_line((h / "name").string(), name) || name != want) continue;
            Files r;
            for (int i = 1; i <= 64 && r.temp.empty(); i++) {
                std::string label;
                const std::string base = "temp" + std::to_string(i);
                if (d::read_line((h / (base + "_label")).string(), label) && label == label_want)
                    r.temp = d::if_file(h / (base + "_input"));
            }
            if (r.temp.empty()) r.temp = d::if_file(h / "temp1_input");
            if (r.temp.empty()) continue;
            r.hwmon = h.filename().string(), r.name = name;
            return r;
        }
    }
    return {};
}

// degrees C, -1 when the file is gone or holds no number
inline float sample(const Files& f) {
    uint64_t v;
    if (f.temp.empty() || !amdgpu_stats::detail::read_u64(f.temp, v)) return -1;
    return v / 1000.0f;
}

}  // namespace mkwvk::cpu_temp
