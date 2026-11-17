// See report_info.h.
#include "report_info.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>

#include "vk_internal.h"

#ifdef _WIN32
#include <intrin.h>
#include <windows.h>
#else
#include <cpuid.h>
#include <sys/utsname.h>
#include <unistd.h>
#endif

namespace mkwvk::report_info {
namespace {

std::string trimmed(std::string s) {
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r' || s.back() == ' ')) s.pop_back();
    size_t i = 0;
    while (i < s.size() && s[i] == ' ') i++;
    return s.substr(i);
}

std::string cpu_name() {
    std::string cpu;
#if defined(__x86_64__) || defined(__i386__) || defined(_M_X64) || defined(_M_IX86)
    {   // (the processor's own name, the same on every system)
        unsigned r[12] = {};
#ifdef _WIN32
        int v[4];
        __cpuid(v, (int)0x80000000);
        const unsigned top = (unsigned)v[0];
        for (unsigned k = 0; k < 3 && top >= 0x80000004u; k++) {
            __cpuid(v, (int)(0x80000002u + k));
            for (int j = 0; j < 4; j++) r[k * 4 + j] = (unsigned)v[j];
        }
#else
        unsigned a, b, c, d;
        if (__get_cpuid(0x80000000u, &a, &b, &c, &d) && a >= 0x80000004u)
            for (unsigned k = 0; k < 3; k++) __get_cpuid(0x80000002u + k, &r[k * 4], &r[k * 4 + 1], &r[k * 4 + 2], &r[k * 4 + 3]);
#endif
        char name[49] = {};
        memcpy(name, r, 48);
        cpu = trimmed(name);
    }
#endif
    return cpu;
}

}   // namespace

std::string cpu_text() {
    std::string cpu = cpu_name();
    if (cpu.empty()) cpu = "an unknown CPU";
    if (const unsigned n = std::thread::hardware_concurrency()) cpu += " (" + std::to_string(n) + " threads)";
    uint64_t ram = 0;
#ifdef _WIN32
    MEMORYSTATUSEX m{};
    m.dwLength = sizeof m;
    if (GlobalMemoryStatusEx(&m)) ram = m.ullTotalPhys;
#else
    {
        const long pages = sysconf(_SC_PHYS_PAGES), page = sysconf(_SC_PAGE_SIZE);
        if (pages > 0 && page > 0) ram = (uint64_t)pages * (uint64_t)page;
    }
#endif
    char gb[32] = "";
    if (ram) snprintf(gb, sizeof gb, ", %llu GB", (unsigned long long)((ram + (1ull << 29)) >> 30));
    return cpu + gb;
}

std::string os_text() {
    std::string os;
#ifdef _WIN32
    {   // (RtlGetVersion: GetVersionEx answers as the program's manifest allows)
        typedef LONG(WINAPI * GetVersionFn)(OSVERSIONINFOW*);
        const HMODULE nt = GetModuleHandleA("ntdll.dll");
        const GetVersionFn get = nt ? (GetVersionFn)(void*)GetProcAddress(nt, "RtlGetVersion") : nullptr;
        OSVERSIONINFOW v{};
        v.dwOSVersionInfoSize = sizeof v;
        if (get && get(&v) == 0) {
            const bool eleven = v.dwMajorVersion == 10 && v.dwBuildNumber >= 22000;
            os = v.dwMajorVersion == 10 ? (eleven ? "Windows 11" : "Windows 10")
                                        : "Windows " + std::to_string(v.dwMajorVersion) + "." + std::to_string(v.dwMinorVersion);
            os += " (build " + std::to_string(v.dwBuildNumber) + ")";
        } else {
            os = "Windows";
        }
    }
#else
    for (const char* file : {"/etc/os-release", "/usr/lib/os-release"}) {
        FILE* f = fopen(file, "r");
        if (!f) continue;
        char line[256];
        while (fgets(line, sizeof line, f))
            if (!strncmp(line, "PRETTY_NAME=", 12)) {
                std::string v = trimmed(line + 12);
                if (v.size() >= 2 && (v[0] == '"' || v[0] == '\'')) v = v.substr(1, v.size() - 2);
                os = v;
            }
        fclose(f);
        if (!os.empty()) break;
    }
    if (os.empty()) os = "Linux";
    struct utsname u;
    if (!uname(&u)) os += std::string(" (") + u.sysname + " " + u.release + ")";
    {   // (the desktop and its display protocol: what a window problem depends on)
        const char* desktop = getenv("XDG_CURRENT_DESKTOP");
        const char* session = getenv("XDG_SESSION_TYPE");
        if (desktop && *desktop) os += std::string(", ") + desktop + (session && *session ? std::string(" (") + session + ")" : "");
    }
#endif
    return os;
}

std::string driver_text() {
    VkPhysicalDeviceDriverProperties drv{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
    VkPhysicalDeviceProperties2 p2{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};
    p2.pNext = &drv;
    if (dev.physical) vkGetPhysicalDeviceProperties2(dev.physical, &p2);
    std::string name(drv.driverName, strnlen(drv.driverName, sizeof drv.driverName)),
        info(drv.driverInfo, strnlen(drv.driverInfo, sizeof drv.driverInfo));
    if (name.empty() && info.empty()) {
        char b[32];
        snprintf(b, sizeof b, "%#x", dev.props.driverVersion);
        return b;
    }
    return info.empty() ? name : name.empty() ? info : name + " " + info;
}

void log_lines() {
    logf("vk: driver: %s", driver_text().c_str());
    // (the crash report's facts, as host/hos_crash_dialog.h reads the last of each; the GPU is the "vk: <device>, Vulkan" line)
    logf("report: cpu %s", cpu_text().c_str());
    logf("report: os %s", os_text().c_str());
    logf("report: renderer Vulkan");
}

}   // namespace mkwvk::report_info
