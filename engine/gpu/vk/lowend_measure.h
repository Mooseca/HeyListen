// Copyright (C) 2026 Sacrappy
// Is this integrated GPU too weak for the game at the player's own settings? Decided by a measure, not by a list of chips: the
// frames shown while play is on (the player runs: no load screen, no title, no menu-only time) are timed over a window that starts
// after the first seconds of play, and the average rate is compared with a threshold (vk_menu.cpp chooses the Lowest quality preset
// under it). The same rate as the benchmark's fps: frames over their total time. tests/test_lowend_measure.py
#pragma once
#include <cstdint>

namespace lowend_rule {

/// The threshold (average frames a second) under which the GPU counts as too weak. The reference laptop (Ryzen 7 5700U, Vega 8) runs
/// the game at 11-13 fps at its defaults; a Steam Deck, a ROG Ally, a Radeon 780M or an Intel Arc integrated GPU are well above 20
constexpr double kWeakFps = 20.0;
constexpr double kSkipPlayS = 15.0;     // play time before the window opens: the first seconds of a scene load shaders and textures
constexpr double kWindowPlayS = 10.0;   // the window, in play time
constexpr double kMaxWindowPlayS = 30.0;   // a window with fewer than kLeastFrames frames goes on to this: the game is very slow then
constexpr int kLeastFrames = 50;
constexpr double kGapNs = 2e9;          // a longer gap between two frames is not play (a stall, a load, a pause): not counted

/// The decision for a measured rate: too weak under the threshold
inline bool weak(double fps, double threshold = kWeakFps) { return fps < threshold; }

enum Verdict { PENDING, WEAK, FINE };

/// The measure, fed with every shown frame's time (ns) and whether play is on. Nothing is stored but five numbers
struct Probe {
    double skip_s = kSkipPlayS, window_s = kWindowPlayS, threshold = kWeakFps;
    int64_t last = 0;
    double play_s = 0, win_s = 0;   // play time so far; of it, the time inside the window
    int frames = 0;
    double fps = 0;                 // the measured rate when decided
    Verdict verdict = PENDING;
    /// A frame shown at now_ns (the clock's own origin) while play is `on` (the player ran in the last moment)
    Verdict feed(int64_t now_ns, bool on) {
        if (verdict != PENDING) return verdict;
        const int64_t prev = last;
        last = on ? now_ns : 0;
        if (!on || !prev || (double)(now_ns - prev) > kGapNs) return verdict;
        const double dt = (double)(now_ns - prev) / 1e9;
        play_s += dt;
        if (play_s < skip_s) return verdict;
        win_s += dt, frames++;
        if (win_s < window_s) return verdict;
        if (frames < kLeastFrames && win_s < kMaxWindowPlayS) return verdict;   // (too few frames to call it: a little longer)
        fps = frames / win_s;
        return verdict = weak(fps, threshold) ? WEAK : FINE;
    }
};

}  // namespace lowend_rule
