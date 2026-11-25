// Copyright (C) 2026 Sacrappy
// lowend_measure (gpu/vk/lowend_measure.h): the measure that decides whether an integrated GPU is too weak. tests/test_lowend_measure.py
#include "../gpu/vk/lowend_measure.h"

#include <cstdio>
#include <vector>

using namespace lowend_rule;

static int failures = 0;
static void expect(bool ok, const char* what) {
    if (!ok) {
        std::printf("FAIL: %s\n", what);
        failures++;
    }
}

/// Frames of frame_ms each for seconds, play on, the clock continuing from t (ns); the verdict at the end
static Verdict run(Probe& p, int64_t& t, double frame_ms, double seconds, bool on = true) {
    const int n = (int)(seconds * 1000.0 / frame_ms);
    for (int i = 0; i < n; i++) {
        t += (int64_t)(frame_ms * 1e6);
        p.feed(t, on);
    }
    return p.verdict;
}

int main() {
    expect(weak(11.0) && weak(13.0) && weak(19.9), "the reference laptop's 11-13 fps and just under 20: weak");
    expect(!weak(20.0) && !weak(30.0) && !weak(60.0), "20 and over: fine");
    expect(weak(25.0, 30.0) && !weak(25.0, 20.0), "the threshold is a parameter");
    {   // the reference laptop: 12 fps at its defaults
        Probe p;
        int64_t t = 1000000000;
        expect(run(p, t, 1000.0 / 12, 14.0) == PENDING, "14 s of play: the window has not opened");
        expect(run(p, t, 1000.0 / 12, 12.0) == WEAK, "12 fps over the window: weak");
        expect(p.fps > 11.5 && p.fps < 12.5, "the measured rate is 12 fps");
    }
    {   // a Steam Deck-class machine: 45 fps
        Probe p;
        int64_t t = 1000000000;
        expect(run(p, t, 1000.0 / 45, 30.0) == FINE, "45 fps: fine");
        expect(p.fps > 44.5 && p.fps < 45.5, "the measured rate is 45 fps");
    }
    {   // just under and just over 20
        Probe a, b;
        int64_t t = 0;
        expect(run(a, t, 1000.0 / 19.0, 30.0) == WEAK, "19 fps: weak");
        t = 0;
        expect(run(b, t, 1000.0 / 21.0, 30.0) == FINE, "21 fps: fine");
    }
    {   // a title or a load screen (play off) is not counted: the window needs its own seconds of play
        Probe p;
        int64_t t = 1000000000;
        expect(run(p, t, 1000.0 / 60, 40.0, false) == PENDING, "40 s with play off: nothing measured");
        expect(run(p, t, 1000.0 / 12, 14.0) == PENDING, "play on, 14 s: still before the window");
        run(p, t, 1000.0 / 60, 20.0, false);   // a load screen in the middle, at a fast rate that must not count
        expect(p.verdict == PENDING && p.win_s == 0, "the load screen left the window closed");
        expect(run(p, t, 1000.0 / 12, 12.0) == WEAK, "after it, play's own frames decide: 12 fps");
    }
    {   // a stall of seconds in the window is a gap, not frames of play
        Probe p;
        int64_t t = 0;
        run(p, t, 1000.0 / 40, 16.0);
        t += 5000000000LL;   // five seconds without a frame
        p.feed(t, true);
        expect(p.play_s < 17.0, "a gap over 2 s adds nothing to the play time");
        expect(run(p, t, 1000.0 / 40, 12.0) == FINE, "40 fps either side of it: fine");
    }
    {   // a very slow game: fewer than 50 frames in the window goes on, then decides weak
        Probe p;
        int64_t t = 0;
        expect(run(p, t, 500.0, 26.0) == PENDING, "2 fps: 11 frames in the 10 s window: not enough frames yet");
        expect(run(p, t, 500.0, 30.0) == WEAK, "2 fps: weak at the longest window");
    }
    {   // the window and skip are parameters (the test hook's)
        Probe p;
        p.skip_s = 1, p.window_s = 1;
        int64_t t = 0;
        expect(run(p, t, 1000.0 / 60, 3.0) == FINE, "a 1 s skip and a 1 s window decide quickly");
    }
    if (failures) return 1;
    std::printf("lowend_measure: all checks passed\n");
    return 0;
}
