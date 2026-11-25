// Copyright (C) 2026 Sacrappy

// The 1% low and 0.1% low of the FPS counter's full overlay (F10), by the benchmark's own definition (tools/bench/run_bench.py
// low_fps): 1000 / the mean frame time of the slowest ceil(fraction * N) frames of the window, at least one frame. Not the 99th
// percentile's frame time: the mean of the slowest frames, so one long stall counts for its length. The window is the last 10 s or
// the last 1000 frames, whichever is longer. The frames are the ones the counter counts: every frame shown (with frame generation
// the made ones too). tests/test_perf_lows.py
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>

namespace mkwvk {
namespace perflows {

constexpr int kCap = 16384;                    // frame times kept: 10 s up to 1600 shown frames a second
constexpr int kLeast = 1000;                   // the window holds at least this many frames...
constexpr int64_t kWindowNs = 10000000000LL;   // ...and at least this much time
constexpr int kShowFrom = 100;                 // fewer frames than this in the window: the lines read "-"

/// A ring of the latest frame times (ms) and when each ended (ns). Static storage, nothing allocated while frames come in
struct Ring {
    float ms[kCap];
    int64_t at[kCap];
    int pos, n;
    void clear() { pos = n = 0; }
    void add(float frame_ms, int64_t now) {
        ms[pos] = frame_ms, at[pos] = now;
        pos = (pos + 1) % kCap;
        if (n < kCap) n++;
    }
    /// The window's frame times, newest first, copied to out (room for kCap); how many
    int window(int64_t now, float* out) const {
        int c = 0;
        while (c < n) {
            const int k = (pos - 1 - c + kCap) % kCap;
            if (c >= kLeast && now - at[k] > kWindowNs) break;
            out[c++] = ms[k];
        }
        return c;
    }
};

/// The benchmark's low_fps for the slowest `fraction` of v[0..n) (reordered). 0 for no frames
inline double low_fps(float* v, int n, double fraction) {
    if (n <= 0) return 0.0;
    const int k = std::max(1, (int)std::ceil(fraction * n - 1e-9));
    std::nth_element(v, v + (n - k), v + n);   // the k slowest end up in v[n-k..n)
    double sum = 0;
    for (int i = n - k; i < n; i++) sum += v[i];
    return 1000.0 / (sum / k);
}
/// Both lows from one window (reordered): the 1% selection first, the 0.1% one inside it
inline void lows(float* v, int n, double* low1, double* low01) {
    *low1 = low_fps(v, n, 0.01);
    const int k1 = n > 0 ? std::max(1, (int)std::ceil(0.01 * n - 1e-9)) : 0;   // (low_fps just left the k1 slowest in v[n-k1..n))
    const int k01 = n > 0 ? std::max(1, (int)std::ceil(0.001 * n - 1e-9)) : 0;   // (<= k1: inside the slice the first selection left)
    *low01 = 0.0;
    if (k01 > 0) {
        float* top = v + (n - k1);
        std::nth_element(top, top + (k1 - k01), top + k1);
        double sum = 0;
        for (int i = k1 - k01; i < k1; i++) sum += top[i];
        *low01 = 1000.0 / (sum / k01);
    }
}
/// The line's number: "-" while the window holds too few frames to say
inline void text(char* b, size_t cap, double fps, int frames) {
    if (frames < kShowFrom || fps <= 0) std::snprintf(b, cap, "-");
    else std::snprintf(b, cap, "%.0f FPS", fps);
}

}  // namespace perflows
}  // namespace mkwvk
