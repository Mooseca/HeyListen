// (HeyListen, v0.4.4) RX_VK_WAIT_OWN: how far behind the GPU the replay lets the game run at each present, for the hazard of a GPU
// that reads guest memory where it is (an integrated GPU: no VRAM mirror, vk_memory.cpp mirror_on) and a game that rewrites its HUD's
// records before a pass has read them (a Radeon 890M, ROG Xbox Ally X: icons flashing, the minimap drawn with another texture).
// Plain functions: tests/test_wait_own.py compiles this header and checks them.
//   0  no wait (any GPU's default but an AMD integrated one's)
//   1  each present waits for its own frame's GPU work: the GPU idle while the game builds the next frame, so the frame time is
//      the game's plus the GPU's (v0.4.3's rule on an AMD integrated GPU; the ROG Ally X and the BC-250 lost fps, #81, #67)
//   2  each present waits for the frame before's GPU work: the game is at most one frame ahead of the GPU, the console's own two
//      frames in flight (its records are a ring of two: a frame's are rewritten once the one before it is done), and the GPU works
//      while the game builds the next frame. The default on an AMD integrated GPU
#pragma once
#include <cstdint>
#include <cstdlib>

namespace wait_own {

/// The mode: RX_VK_WAIT_OWN's number when set (0, 1 or 2; any other nonzero number is 1: the switch's old rule), else 0 when
/// RX_VK_WAIT_GPU (a ring of frames) is set, else 2 on an AMD integrated GPU, else 0
inline int mode(const char* own_env, bool wait_gpu_set, bool amd_igpu) {
    if (own_env) {
        const int v = atoi(own_env);
        return v == 0 ? 0 : v == 2 ? 2 : 1;
    }
    if (wait_gpu_set) return 0;
    return amd_igpu ? 2 : 0;
}

/// The value this present waits for, given the mode, its own value and the value of the present before it (0: none yet); `prev`
/// is updated to this present's. 0: nothing to wait for
inline uint64_t target(int mode, uint64_t value, uint64_t& prev) {
    const uint64_t before = prev;
    prev = value;
    return mode == 1 ? value : mode == 2 ? before : 0;
}

}   // namespace wait_own
