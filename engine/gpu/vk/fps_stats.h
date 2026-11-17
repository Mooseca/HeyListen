// (heylisten) What the performance summary (perf_report.h) takes of a frame. Longshot's FPS counter measures a frame's parts
// (game, render, GPU wait, pacing) and the draws left out; HeyListen's overlay does not, so those stay 0 here and the summary's
// parts_ms and draws_left_out are sent as 0: the payload keeps Longshot's field tables, which the server validates.
#pragma once

#include <cstdint>

namespace mkwvk::fps_stats {

enum Part { kGame, kRender, kGpuWait, kPace, kParts };

struct Frame {
    float ms = 0;               // (present to present)
    float part[kParts] = {};    // (ms; not measured here: 0)
    float gpu_ms = 0;           // (the GPU's own time since the frame before, 0 when not timed)
    uint16_t left_out = 0;      // (not counted here: 0)
};

}   // namespace mkwvk::fps_stats
