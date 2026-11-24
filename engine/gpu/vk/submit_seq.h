// Copyright (C) 2026 Sacrappy
// The submit sequencer of the replay's lanes (stream DECOUPLE, docs/research/decouple-cross-frame.md stage 2, section 4.3 item 1).
// Every unit of the stream takes a ticket, in stream order, when the spine begins it: a plain recording (begin_recording), or a big
// command buffer's group of segments (its segments go out in their own order inside it, EarlyGroup's next_sub). A unit is finished
// when it is in the queue: a recording sent, a group whose every segment is sent, or a unit dropped (nothing of it goes out). A
// recording made ready while a ticket before it is still open is left ready; whoever finishes the one before sends it (ready_head).
// Today every group is joined before the next submission's first recording is sent, so units finish in ticket order; with the
// lanes (RX_VK_LANES) the spine goes on beside a pending group and the sequencer keeps the queue's order. RX_VK_LANES_CHECK=1 takes
// the tickets with today's joins and counts a unit finished while an earlier one is open (out_of_order: must read 0).
// The pure rules, with no Vulkan and no locking in them (the caller holds one mutex): tests/test_submit_seq.py.
#pragma once
#include <cstdint>
#include <cstdlib>
#include <deque>

namespace submit_seq {

constexpr unsigned kMaxLanes = 4;

/// RX_VK_LANES=<0..kMaxLanes> (unset or 0: off): how many submissions' groups may be pending at once
inline unsigned parse_lanes(const char* e) {
    if (!e || !*e) return 0;
    const long v = atol(e);
    return v < 0 ? 0u : v > (long)kMaxLanes ? kMaxLanes : (unsigned)v;
}

class Sequencer {
public:
    enum : uint8_t { kOpen = 0, kReady = 1, kDone = 2 };

    /// A unit begun by the spine: its ticket, the next in stream order
    uint64_t take() {
        st_.push_back(kOpen);
        taken_++;
        const uint64_t pend = next_ - head_ + 1;
        if (pend > max_pending_) max_pending_ = pend;
        return next_++;
    }
    /// Whether every unit before t is finished (t may go to the queue now)
    bool is_head(uint64_t t) const { return t == head_; }
    /// Whether t is taken and not finished
    bool open(uint64_t t) const { return t >= head_ && t < next_ && st_[t - head_] != kDone; }
    /// A recording made ready that may not go yet (a unit before it is open): it waits for ready_head()
    void ready(uint64_t t) {
        if (!open(t)) {
            unknown_++;
            return;
        }
        st_[t - head_] = kReady;
    }
    /// The head's ticket when its recording was left ready (to send now, then finish), else 0
    uint64_t ready_head() const { return !st_.empty() && st_[0] == kReady ? head_ : 0; }
    /// The unit is in the queue (counted out of order when a unit before it is still open). drop: it never goes (not counted)
    void finish(uint64_t t) { end(t, true); }
    void drop(uint64_t t) { end(t, false); }

    uint64_t head() const { return head_; }
    uint64_t pending() const { return next_ - head_; }
    int64_t taken() const { return taken_; }
    int64_t finished() const { return finished_; }
    int64_t dropped() const { return dropped_; }
    int64_t out_of_order() const { return out_of_order_; }
    int64_t unknown() const { return unknown_; }
    uint64_t max_pending() const { return max_pending_; }

private:
    void end(uint64_t t, bool sent) {
        if (!open(t)) {   // (0, finished twice, or never taken)
            unknown_++;
            return;
        }
        if (sent && t != head_) out_of_order_++;
        st_[t - head_] = kDone;
        (sent ? finished_ : dropped_)++;
        while (!st_.empty() && st_[0] == kDone) st_.pop_front(), head_++;
    }
    std::deque<uint8_t> st_;   // (the tickets head_ .. next_ - 1)
    uint64_t next_ = 1, head_ = 1, max_pending_ = 0;
    int64_t taken_ = 0, finished_ = 0, dropped_ = 0, out_of_order_ = 0, unknown_ = 0;
};

}   // namespace submit_seq
