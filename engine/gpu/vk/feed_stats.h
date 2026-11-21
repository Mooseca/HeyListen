/* Why the GPU sat idle between two recordings (vk_replay.cpp, stream ORDER3, RX_VK_FEED_LOG).
   The GPU's own gap before a recording starts is split by what the host knew about that recording, in one clock:
     ready   the host had finished it (its commands recorded, or a segment waiting for the ones before it in the queue's order)
     sent    the host's vkQueueSubmit2 that carries it (for a recording held back for a late fix or a batch, the flush's)
     start   the GPU's first timestamp in it
   Idle time from the end of what ran before it, e, to start, g:
     not ready   e..ready          the replay had not finished recording what the GPU runs next: the feed is late
     held        ready..sent       done but not handed to the queue: the in-order submit of the segments before it, a late fix, a batch
     after send  sent..g           handed over, the GPU not on it yet (the driver and the hardware's start latency)
     queued      the whole gap     it was sent before the GPU went idle: waits inside the GPU or the driver, not the host's doing
   No Vulkan in here: the times are numbers, so tests/test_feed_stats.cpp runs it with made-up ones. */
#pragma once

#include <algorithm>
#include <cstdint>
#include <vector>

namespace mkwvk::feed {

/// One recording as the host and the GPU saw it (ns on one clock; kind: 0 a whole recording, 1 a segment, 2 the early pre-sync's)
struct Rec {
    double ready = 0, sent = 0, start = 0, end = 0;
    int kind = 0;
};

struct Totals {
    double busy = 0;            // (the union of the recordings' run times)
    double idle = 0;            // (gaps of under 100 ms between them)
    double not_ready = 0, held = 0, after_send = 0, queued = 0;
    double not_ready_kind[3] = {0, 0, 0};
    int64_t gaps = 0, big_gaps = 0;   // (gaps of 0.5 ms and over)
    double big_idle = 0;              // (their time)
    double longest = 0;
    double window = 0;          // (first start to last end, gaps of 100 ms or more left out)
    int64_t recs = 0;
};

/// The recordings of a window, any order: sorted by start, each gap against the latest end so far
inline Totals attribute(std::vector<Rec> v, double tolerance_ns = 50e3) {
    Totals t;
    std::sort(v.begin(), v.end(), [](const Rec& a, const Rec& b) { return a.start < b.start; });
    double end = 0, lo = 0;
    bool have = false;
    for (const Rec& r : v) {
        if (r.end <= r.start) continue;
        t.recs++;
        const bool first = !have;
        if (first) lo = r.start, have = true;
        if (!first && r.start > end) {
            const double e = end, g = r.start, gap = g - e;
            if (gap < 1e8) {
                t.idle += gap, t.gaps++;
                t.longest = std::max(t.longest, gap);
                if (gap >= 0.5e6) t.big_gaps++, t.big_idle += gap;
                if (r.sent && r.sent < e - tolerance_ns) {   // (sent well before the GPU went idle)
                    t.queued += gap;
                } else {
                    const double ready = r.ready ? std::clamp(r.ready, e, g) : e;
                    const double sent = r.sent ? std::clamp(r.sent, ready, g) : ready;
                    t.not_ready += ready - e, t.not_ready_kind[r.kind < 0 || r.kind > 2 ? 0 : r.kind] += ready - e;
                    t.held += sent - ready;
                    t.after_send += g - sent;
                }
            } else {
                t.window -= gap;
            }
        }
        if (r.end > end) {
            t.busy += r.end - std::max(end, r.start);
            end = r.end;
        }
    }
    if (have) t.window += end - lo;
    return t;
}

/// a window's totals added to the run's
inline void accumulate(Totals& a, const Totals& b) {
    a.busy += b.busy, a.idle += b.idle, a.not_ready += b.not_ready, a.held += b.held, a.after_send += b.after_send, a.queued += b.queued;
    for (int k = 0; k < 3; k++) a.not_ready_kind[k] += b.not_ready_kind[k];
    a.gaps += b.gaps, a.big_gaps += b.big_gaps, a.big_idle += b.big_idle, a.window += b.window, a.recs += b.recs;
    a.longest = std::max(a.longest, b.longest);
}

} // namespace mkwvk::feed
