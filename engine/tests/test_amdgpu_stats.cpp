// gpu/vk/amdgpu_stats.h against fake sysfs trees: the card chosen (by PCI address, by ids), each number, missing files.
// With --real, the machine's /sys for a card given by its ids and PCI address (a check by hand, not run by the suite).
#include "../gpu/vk/amdgpu_stats.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>

#define CHECK(name, condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s at line %d\n", name, __LINE__); return 1; } } while (0)

namespace fs = std::filesystem;
using namespace mkwvk::amdgpu_stats;

static void put(const fs::path& p, const char* v) {
    fs::create_directories(p.parent_path());
    std::ofstream(p) << v << "\n";
}
// a card's PCI node under devices/, and class/drm/<card>/device a link to it, as the kernel lays them out
static fs::path card(const fs::path& sys, const char* name, const char* pci_path, const char* vendor, const char* device) {
    const fs::path node = sys / "devices" / pci_path;
    fs::create_directories(node);
    put(node / "vendor", vendor);
    put(node / "device", device);
    fs::create_directories(sys / "class/drm" / name);
    fs::create_directory_symlink(node, sys / "class/drm" / name / "device");
    return node;
}
static void full(const fs::path& node, const char* hw) {
    put(node / "gpu_busy_percent", "42");
    put(node / "mem_info_vram_used", "1621876736");     // 1546 MB
    put(node / "mem_info_vram_total", "17095983104");   // 16304 MB
    const fs::path h = node / "hwmon" / hw;
    put(h / "name", "amdgpu");
    put(h / "temp1_input", "55000");
    put(h / "temp1_label", "edge");
    put(h / "power1_average", "187000000");
    put(h / "freq1_input", "2970000000");
    put(h / "freq1_label", "sclk");
}
static bool near(float a, float b) { return std::fabs(a - b) < 0.01f; }

static int real(int argc, char** argv) {
    // --real <vendor> <device> [<domain> <bus> <dev> <function>]  (hex)
    if (argc < 4) return 2;
    Id id;
    id.vendor = (uint32_t)std::strtoul(argv[2], nullptr, 16), id.device = (uint32_t)std::strtoul(argv[3], nullptr, 16);
    if (argc >= 8) {
        id.has_pci = true;
        id.domain = (uint32_t)std::strtoul(argv[4], nullptr, 16), id.bus = (uint32_t)std::strtoul(argv[5], nullptr, 16);
        id.dev = (uint32_t)std::strtoul(argv[6], nullptr, 16), id.function = (uint32_t)std::strtoul(argv[7], nullptr, 16);
    }
    const Files f = open("/sys", id);
    std::printf("card %s (pci %s), matched by %s\n", f.card.empty() ? "-" : f.card.c_str(), f.pci.c_str(), id.has_pci ? "PCI address" : "ids");
    std::printf("files: busy=%s\n  vram_used=%s\n  vram_total=%s\n  temp=%s\n  power=%s\n  clock=%s\n", f.busy.c_str(), f.vram_used.c_str(),
                f.vram_total.c_str(), f.temp.c_str(), f.power.c_str(), f.clock.c_str());
    const Sample s = sample(f);
    std::printf("GPU %.0f %%  %.1f C  %.1f W  %.0f MHz  VRAM %.0f / %.0f MB\n", s.gpu_pct, s.temp_c, s.power_w, s.clock_mhz, s.vram_used_mb,
                s.vram_total_mb);
    return f.any() ? 0 : 1;
}

int main(int argc, char** argv) {
    if (argc >= 2 && !std::strcmp(argv[1], "--real")) return real(argc, argv);
    if (argc < 2) return 2;
    const fs::path root = argv[1];

    {   // an integrated GPU as card0, the RX 9070 XT as card1: the second matches, by PCI address
        const fs::path sys = root / "two";
        const fs::path igpu = card(sys, "card0", "pci0000:00/0000:0e:00.0", "0x1002", "0x13c0");
        full(igpu, "hwmon0");
        put(igpu / "gpu_busy_percent", "3");
        const fs::path gpu = card(sys, "card1", "pci0000:00/0000:00:03.1/0000:09:00.0/0000:0a:00.0/0000:0b:00.0", "0x1002", "0x7550");
        full(gpu, "hwmon1");
        fs::create_directories(sys / "class/drm/card1-DP-1");   // (a connector: not a card)
        fs::create_directories(sys / "class/drm/renderD128");
        Id id;
        id.vendor = 0x1002, id.device = 0x7550, id.has_pci = true, id.bus = 0x0b;
        const Files f = open(sys.string(), id);
        CHECK("two: card1 by PCI", f.card == "card1" && f.pci == "0000:0b:00.0" && f.any());
        const Sample s = sample(f);
        CHECK("two: busy", near(s.gpu_pct, 42));
        CHECK("two: vram", near(s.vram_used_mb, 1546) && near(s.vram_total_mb, 16304));
        CHECK("two: temp", near(s.temp_c, 55));
        CHECK("two: power", near(s.power_w, 187));
        CHECK("two: clock", near(s.clock_mhz, 2970));

        Id byid;   // (no VK_EXT_pci_bus_info: the vendor and device ids)
        byid.vendor = 0x1002, byid.device = 0x7550;
        CHECK("two: card1 by ids", open(sys.string(), byid).card == "card1");
        byid.device = 0x13c0;
        CHECK("two: card0 by ids", open(sys.string(), byid).card == "card0");
        byid.device = 0x1234;
        CHECK("two: no match by ids", open(sys.string(), byid).card.empty() && !open(sys.string(), byid).any());
        Id other = id;
        other.bus = 0x0c;   // (an address no card has: no fallback to another card)
        CHECK("two: no match by PCI", open(sys.string(), other).card.empty());
    }
    {   // missing and odd files: each leaves its own number empty
        const fs::path sys = root / "sparse";
        const fs::path gpu = card(sys, "card0", "pci0000:00/0000:03:00.0", "0x1002", "0x73bf");
        put(gpu / "mem_info_vram_total", "8589934592");
        put(gpu / "gpu_busy_percent", "");   // (an empty read, as a card in runtime suspend can give)
        const fs::path h = gpu / "hwmon/hwmon3";
        put(h / "power1_input", "95500000");   // (no power1_average: the newer firmware's file)
        put(h / "freq1_input", "1000000000");
        put(h / "freq1_label", "mclk");        // (not the shader clock)
        Id id;
        id.has_pci = true, id.bus = 3;
        const Files f = open(sys.string(), id);
        CHECK("sparse: found", f.card == "card0" && f.any());
        CHECK("sparse: no used, temp or clock file", f.vram_used.empty() && f.temp.empty() && f.clock.empty());
        const Sample s = sample(f);
        CHECK("sparse: busy empty", s.gpu_pct < 0);
        CHECK("sparse: vram used empty, total read", s.vram_used_mb < 0 && near(s.vram_total_mb, 8192));
        CHECK("sparse: temp empty", s.temp_c < 0);
        CHECK("sparse: power1_input", near(s.power_w, 95.5f));
        CHECK("sparse: clock empty", s.clock_mhz < 0);

        fs::remove(gpu / "mem_info_vram_total");   // (a file gone after open: empty, no failure)
        CHECK("sparse: removed later", sample(f).vram_total_mb < 0);
    }
    {   // a card without any amdgpu files (another vendor's driver): found, nothing to read
        const fs::path sys = root / "none";
        card(sys, "card0", "pci0000:00/0000:01:00.0", "0x10de", "0x2c05");
        Id id;
        id.vendor = 0x10de, id.device = 0x2c05;
        const Files f = open(sys.string(), id);
        CHECK("none: nothing", f.card == "card0" && !f.any());
        const Sample s = sample(f);
        CHECK("none: all empty", s.gpu_pct < 0 && s.temp_c < 0 && s.power_w < 0 && s.clock_mhz < 0 && s.vram_used_mb < 0 && s.vram_total_mb < 0);
        CHECK("no class/drm at all", !open((root / "missing").string(), id).any());
    }
    std::puts("amdgpu_stats: ok");
    return 0;
}
