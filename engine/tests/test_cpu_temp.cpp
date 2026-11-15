// gpu/vk/cpu_temp.h against fake sysfs trees: the hwmon node and input chosen (k10temp's Tctl, coretemp's package), the
// others passed over, missing and bad files. With --real, the machine's /sys (a check by hand, not run by the suite).
#include "../gpu/vk/cpu_temp.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>

#define CHECK(name, condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s at line %d\n", name, __LINE__); return 1; } } while (0)

namespace fs = std::filesystem;
using namespace mkwvk;

static void put(const fs::path& p, const char* v) {
    fs::create_directories(p.parent_path());
    std::ofstream(p) << v << "\n";
}
// a hwmon node under devices/, and class/hwmon/<hwmonN> a link to it, as the kernel lays them out
static fs::path hwmon(const fs::path& sys, const char* n, const char* name) {
    const fs::path node = sys / "devices/platform" / name / "hwmon" / n;
    fs::create_directories(node);
    put(node / "name", name);
    fs::create_directories(sys / "class/hwmon");
    fs::create_directory_symlink(node, sys / "class/hwmon" / n);
    return node;
}
static bool near(float a, float b) { return std::fabs(a - b) < 0.01f; }

static int real() {
    const cpu_temp::Files f = cpu_temp::open("/sys");
    std::printf("hwmon %s (%s), file %s\n", f.hwmon.empty() ? "-" : f.hwmon.c_str(), f.name.empty() ? "-" : f.name.c_str(),
                f.temp.empty() ? "-" : f.temp.c_str());
    std::printf("CPU %.1f C\n", cpu_temp::sample(f));
    return f.any() ? 0 : 1;
}

int main(int argc, char** argv) {
    if (argc >= 2 && !std::strcmp(argv[1], "--real")) return real();
    if (argc < 2) return 2;
    const fs::path root = argv[1];

    {   // this machine's layout (Ryzen 5 5500X3D): nvme, amdgpu, then k10temp with Tctl at temp1 and Tccd1 at temp3
        const fs::path sys = root / "ryzen";
        put(hwmon(sys, "hwmon0", "nvme") / "temp1_input", "38850");
        put(hwmon(sys, "hwmon1", "amdgpu") / "temp1_input", "45000");
        const fs::path k = hwmon(sys, "hwmon2", "k10temp");
        put(k / "temp1_label", "Tctl"), put(k / "temp1_input", "53375");
        put(k / "temp3_label", "Tccd1"), put(k / "temp3_input", "51250");
        const auto f = cpu_temp::open(sys.string());
        CHECK("k10temp found", f.hwmon == "hwmon2" && f.name == "k10temp");
        CHECK("Tctl", f.temp == (sys / "class/hwmon/hwmon2/temp1_input").string());
        CHECK("Tctl value", near(cpu_temp::sample(f), 53.375f));
        put(k / "temp1_input", "61000");   // (read again at each sample)
        CHECK("read again", near(cpu_temp::sample(f), 61.0f));
        put(k / "temp1_input", "");
        CHECK("empty file", cpu_temp::sample(f) == -1);
        fs::remove(k / "temp1_input");
        CHECK("file gone", cpu_temp::sample(f) == -1);
    }
    {   // Tctl not at temp1 (the label decides), and hwmon10 after hwmon9 (the numbers, not the names, are sorted)
        const fs::path sys = root / "label";
        const fs::path k = hwmon(sys, "hwmon10", "k10temp");
        put(k / "temp1_label", "Tccd1"), put(k / "temp1_input", "40000");
        put(k / "temp2_label", "Tctl"), put(k / "temp2_input", "47000");
        const fs::path k9 = hwmon(sys, "hwmon9", "k10temp");
        put(k9 / "temp1_input", "30000");   // (no labels: temp1)
        const auto f = cpu_temp::open(sys.string());
        CHECK("lowest number", f.hwmon == "hwmon9" && near(cpu_temp::sample(f), 30.0f));
        fs::remove(sys / "class/hwmon/hwmon9");
        const auto g = cpu_temp::open(sys.string());
        CHECK("Tctl by its label", g.hwmon == "hwmon10" && near(cpu_temp::sample(g), 47.0f));
    }
    {   // Intel: coretemp's package (temp1, "Package id 0"), not a core; k10temp first when both are there
        const fs::path sys = root / "intel";
        const fs::path c = hwmon(sys, "hwmon3", "coretemp");
        put(c / "temp2_label", "Core 0"), put(c / "temp2_input", "70000");
        put(c / "temp1_label", "Package id 0"), put(c / "temp1_input", "72000");
        const auto f = cpu_temp::open(sys.string());
        CHECK("coretemp package", f.name == "coretemp" && near(cpu_temp::sample(f), 72.0f));
        const fs::path k = hwmon(sys, "hwmon5", "k10temp");
        put(k / "temp1_input", "50000");
        CHECK("k10temp first", cpu_temp::open(sys.string()).name == "k10temp");
    }
    {   // a k10temp with no input passed over; none at all, or no hwmon class: empty, -1
        const fs::path sys = root / "none";
        hwmon(sys, "hwmon0", "k10temp");
        put(hwmon(sys, "hwmon1", "nvme") / "temp1_input", "38000");
        fs::create_directories(sys / "class/hwmon/hwmonX");   // (not a node)
        const auto f = cpu_temp::open(sys.string());
        CHECK("none", !f.any() && f.hwmon.empty() && cpu_temp::sample(f) == -1);
        CHECK("no class", !cpu_temp::open((root / "missing").string()).any());
    }
    std::puts("cpu_temp: PASS");
    return 0;
}
