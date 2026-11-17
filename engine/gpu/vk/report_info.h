// (heylisten) What a crash report and a performance summary say of the machine: the same words in both (the crash window reads
// the "report: " log lines this makes, host/hos_crash_dialog.h; the summary reads them directly, perf_report.cpp). No names of
// the player's: the CPU, the RAM, the operating system's version and the GPU driver, nothing else.
#pragma once

#include <string>

namespace mkwvk::report_info {

/// "AMD Ryzen 7 5800X 8-Core Processor (16 threads), 32 GB"
std::string cpu_text();
/// "Windows 11 (build 26200)", "Arch Linux (Linux 7.2.15), KDE (wayland)": the operating system and its version
std::string os_text();
/// The GPU driver as it names itself (VkPhysicalDeviceDriverProperties: "NVIDIA 580.95", "radv Mesa 25.2.4"), else its version number
std::string driver_text();
/// The log's lines the crash window reads: "report: cpu ...", "report: os ...", "report: gpu ...", "vk: driver: ..."
void log_lines();

}   // namespace mkwvk::report_info
