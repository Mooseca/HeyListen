// (hookshot) The storm hold's state machine, with no game and no GPU behind it: a cold area's arrival queues hundreds
// of shader translations (the fade rewrites the texture handles every game frame, each frame's picks pushing new
// variants), and the frames drawn while the queue is that deep sample the fade's transient words — the white/cyan
// blowouts and green bands of the picture regression that #1714's render-instead-of-stall unmasked.
//
// While the hold latches, the *present* is withheld (RX_VK_STORM_HOLD_PRESENT, the default): the frames go on being
// drawn — the game's state, its upload stream and its exposure meter stay live — and present_image() shows nothing, so
// the compositor keeps the last good picture and none of the churn's frames reaches the screen. With
// RX_VK_STORM_HOLD_PRESENT=0 the draws are left out instead, as the hold's first version did (the frames then show the
// area's earlier picture, or the teleport's black).
//
// The release rule is the game's, counted in presents (texture_frame_no): no release within RX_VK_STORM_MIN_FRAMES
// presents of the engage — past the seam a phase pause showed (~250), well under the hold that over-adapted the
// exposure (~2300) — and none while a job was pushed in the last RX_VK_STORM_QUIET_FRAMES presents (a gap the churn's
// bursts never bridged, ~30 at their widest). Both 0: the first version's rule, the queue dipping below half the
// engage depth.
//
// RX_VK_STORM_HOLD=0: no hold at all, drawn and shown as before (yesterday's behaviour). storm_hold_tick() is called
// once a present (vk_replay.cpp's do_present) and storm_hold_draws_held()/storm_hold_presents_held() are read by the
// draw path (vk_draw.cpp) and present_image().
#pragma once

#include <cstdint>

namespace mkwvk {

/// The hold's numbers, from the environment once (RX_VK_STORM_HOLD, _MIN_FRAMES, _QUIET_FRAMES, _HOLD_PRESENT)
struct StormHoldRules {
    int deep = 200;             ///< engage at this many queued jobs (<= 0: no hold)
    int64_t min_frames = 400;   ///< no release within this many presents of the engage
    int64_t quiet_frames = 100; ///< none while a job was pushed in the last this many presents (<= 0: the depth rule)
    int64_t off_depth = 100;    ///< (quiet_frames <= 0) release below this many queued jobs: half the engage depth
    bool hold_present = true;   ///< withhold the present (the default), not the frame's draws
};

enum class StormHoldEvent { None, Engaged, Released };

/// One latch for every thread: a churn is the whole frame's, and a thread that missed the threshold crossing kept
/// drawing the churn's frames while the others held.
struct StormHold {
    bool on = false;
    uint64_t since_frame = 0;   ///< the present the latch engaged at

    /// One tick a present. pending: jobs queued; push_age: presents since the last push; frame: this present's number.
    StormHoldEvent tick(const StormHoldRules& r, int64_t pending, int64_t push_age, uint64_t frame) {
        if (r.deep <= 0) {
            on = false;   // (RX_VK_STORM_HOLD=0: never held)
            return StormHoldEvent::None;
        }
        if (!on) {
            if (pending < r.deep) return StormHoldEvent::None;
            on = true, since_frame = frame;
            return StormHoldEvent::Engaged;
        }
        const int64_t held = (int64_t)(frame - since_frame);
        const bool quiet = r.quiet_frames > 0 ? push_age >= r.quiet_frames : pending < r.off_depth;
        if (quiet && held >= r.min_frames) {
            on = false;
            return StormHoldEvent::Released;
        }
        return StormHoldEvent::None;
    }
};

/// The switches and the one hold of this process (defined in vk_replay.cpp)
const StormHoldRules& storm_hold_rules();
/// Ticks the hold for the present just recorded: the queue's depth, how long it has gone unpushed, the present's number
StormHoldEvent storm_hold_tick(int64_t pending, int64_t push_age, uint64_t frame);
/// The latch, as the last tick left it
bool storm_hold_on();
/// Whether the frame's draws are what is held back (RX_VK_STORM_HOLD_PRESENT=0), read by the draw path
bool storm_hold_draws_held();
/// Whether the present is what is held back (the default), read by present_image()
bool storm_hold_presents_held();

} // namespace mkwvk
