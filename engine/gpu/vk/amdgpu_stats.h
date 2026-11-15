// (HeyListen, Linux) The full FPS overlay's GPU numbers (vk_perf.cpp) from the amdgpu driver's sysfs files, where NVML gives
// nothing: AMD cards have no NVML, and Linux had no NVML loader at all. The card is the one Vulkan renders on: its PCI address
// (VK_EXT_pci_bus_info) names its node, else its vendor and device ids; a machine may have an integrated GPU as card0.
//   device/gpu_busy_percent                         load, %
//   device/mem_info_vram_used, mem_info_vram_total  bytes
//   device/hwmon/hwmon*/temp1_input                 millidegrees ("edge")
//   device/hwmon/hwmon*/power1_average|power1_input microwatts (power1_input on newer cards' firmware, average on older)
//   device/hwmon/hwmon*/freq1_input                 Hz, when its label is "sclk" (the shader clock)
// The files are found once (open); a sample reads only those, a few bytes each, at the sampler's half-second cadence. A file
// missing or unreadable leaves its number at -1 (the overlay's empty cell).
// Pure, no Vulkan: tests/test_amdgpu_stats.cpp builds a fake sysfs tree.
#pragma once
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

namespace mkwvk::amdgpu_stats {

struct Id {   // the Vulkan device's
    uint32_t vendor = 0, device = 0;
    bool has_pci = false;   // (VK_EXT_pci_bus_info's address below)
    uint32_t domain = 0, bus = 0, dev = 0, function = 0;
};

struct Files {   // the files found for the card ("": not there)
    std::string card;   // ("card1")
    std::string pci;    // ("0000:0b:00.0", the card's node)
    std::string busy, vram_used, vram_total, temp, power, clock;
    bool any() const { return !busy.empty() || !vram_used.empty() || !temp.empty() || !power.empty() || !clock.empty(); }
};

struct Sample {
    float gpu_pct = -1, temp_c = -1, power_w = -1, clock_mhz = -1, vram_used_mb = -1, vram_total_mb = -1;
};

namespace detail {
inline bool read_line(const std::string& p, std::string& out) {
    std::ifstream f(p);
    out.clear();
    return f && std::getline(f, out) && !out.empty();
}
// a decimal (or 0x hex: the ids) number; false when the file is missing, unreadable or not a number
inline bool read_u64(const std::string& p, uint64_t& v) {
    std::string s;
    if (!read_line(p, s)) return false;
    char* end = nullptr;
    v = std::strtoull(s.c_str(), &end, 0);
    return end != s.c_str();
}
inline std::string if_file(const std::filesystem::path& p) {
    std::error_code ec;
    return std::filesystem::is_regular_file(p, ec) ? p.string() : std::string();
}
// "card1", not "card1-DP-1" (a connector) or "renderD128"
inline bool is_card(const std::string& n) {
    if (n.size() < 5 || n.compare(0, 4, "card")) return false;
    for (size_t i = 4; i < n.size(); i++)
        if (n[i] < '0' || n[i] > '9') return false;
    return true;
}
}  // namespace detail

// sysroot: "/sys" (a test passes its fake tree). Finds the card and its files; an empty Files when no card matches.
inline Files open(const std::string& sysroot, const Id& id) {
    namespace fs = std::filesystem;
    Files r;
    char want[32];
    std::snprintf(want, sizeof want, "%04x:%02x:%02x.%x", id.domain & 0xffff, id.bus & 0xff, id.dev & 0x1f, id.function & 7);
    std::error_code ec;
    fs::path best;
    std::string best_name;
    for (fs::directory_iterator it(fs::path(sysroot) / "class/drm", ec), end; !ec && it != end; it.increment(ec)) {
        const std::string n = it->path().filename().string();
        if (!detail::is_card(n)) continue;
        const fs::path d = it->path() / "device";
        bool match;
        if (id.has_pci) {
            std::error_code ec2;
            const fs::path real = fs::canonical(d, ec2);
            match = !ec2 && real.filename().string() == want;
        } else {
            uint64_t v = 0, dv = 0;
            match = detail::read_u64((d / "vendor").string(), v) && detail::read_u64((d / "device").string(), dv) && v == id.vendor &&
                    dv == id.device;
        }
        // (by ids, two cards of one model: the lowest card number, as the order is not sorted)
        if (match && (best_name.empty() || n.size() < best_name.size() || (n.size() == best_name.size() && n < best_name)))
            best = d, best_name = n;
    }
    if (best_name.empty()) return r;
    r.card = best_name;
    {
        std::error_code ec2;
        const fs::path real = fs::canonical(best, ec2);
        r.pci = ec2 ? std::string() : real.filename().string();
    }
    r.busy = detail::if_file(best / "gpu_busy_percent");
    r.vram_used = detail::if_file(best / "mem_info_vram_used");
    r.vram_total = detail::if_file(best / "mem_info_vram_total");
    // (one hwmon node under an amdgpu card; the first one that has any of the files)
    for (fs::directory_iterator it(best / "hwmon", ec), end; !ec && it != end; it.increment(ec)) {
        const fs::path h = it->path();
        const std::string t = detail::if_file(h / "temp1_input");
        std::string p = detail::if_file(h / "power1_average");
        if (p.empty()) p = detail::if_file(h / "power1_input");
        std::string c = detail::if_file(h / "freq1_input"), label;
        if (!c.empty() && detail::read_line((h / "freq1_label").string(), label) && label != "sclk") c.clear();
        if (t.empty() && p.empty() && c.empty()) continue;
        r.temp = t, r.power = p, r.clock = c;
        break;
    }
    return r;
}

inline Sample sample(const Files& f) {
    Sample s;
    uint64_t v;
    if (!f.busy.empty() && detail::read_u64(f.busy, v) && v <= 100) s.gpu_pct = (float)v;
    if (!f.vram_used.empty() && detail::read_u64(f.vram_used, v)) s.vram_used_mb = (float)(v >> 20);
    if (!f.vram_total.empty() && detail::read_u64(f.vram_total, v) && v) s.vram_total_mb = (float)(v >> 20);
    if (!f.temp.empty() && detail::read_u64(f.temp, v)) s.temp_c = v / 1000.0f;
    if (!f.power.empty() && detail::read_u64(f.power, v)) s.power_w = v / 1e6f;
    if (!f.clock.empty() && detail::read_u64(f.clock, v) && v) s.clock_mhz = v / 1e6f;
    return s;
}

}  // namespace mkwvk::amdgpu_stats
