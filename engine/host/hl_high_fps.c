/* (HeyListen, after upstream Hookshot 8fcc8c22b, "keep sound and moving platforms working above a 60 fps cap", and 9df055f23,
   "the sound clock keeps its remainder around 60 fps, and cap 60 runs every phase") The sound manager's job at 60 Hz and the
   physics solver's steps rounded up, under a Frame rate cap above 60: host/oot_high_fps.h has why and the logic.

   Upstream edits the lifted f_80435300, f_838ceb80 and f_838cfc10 in nx2/oot_patches.py. Here the lifted work folder is shared
   by every worktree, so the calls go in the way the step and movie hooks do (host/hl_step.c): lift hooks, HL_SOUND_HOOK and
   HL_SOLVER_HOOK below with each function's text hash, lines nx2/hl_gates.py puts after anchors in that text, marked
   "hl gate <address + 1>", so a tree that does not ask for them takes them out. The functions' hashes are unchanged by them,
   and an exeFS mod that patches one leaves its hook out. The game's own code still runs: the sound job's step line sets
   vreg 0 again after the game's load, the solver's line sets x1 again after the game's cut.

   Both act only while the host publishes the frame's seconds (hos_frame_seconds_bits: a cap above 60 with the step hooks in).
   HOS_FPS_SOUND=0: the sound job every frame with the game's step; HOS_FPS_SOLVER=0: the game's solver count (comparisons;
   HeyListen's, upstream has no switch). HOS_FPS_LOG (set): what they do, every 600 calls. */
#include "hl_host.h"
#include "oot_high_fps.h"
#include <windows.h>   /* (SRWLOCK, InterlockedIncrement64) */
#include <stdlib.h>

HL_SOUND_HOOK(80435300, "795ee90e082f72a1");    /* the sound manager's job: its head, and its load of the game step */
HL_SOLVER_HOOK(838ceb80, "c4203f2465e06081");   /* the solver's step count, the two places the game sets it */
HL_SOLVER_HOOK(838cfc10, "228fd7a71a1ca0f0");

extern volatile uint32_t hos_frame_seconds_bits;   /* (hl_step.c: the frame's seconds, 0 at a cap of 60) */

/* (an env switch read once: 0 turns it off, anything else or unset leaves it on) */
static int switched(int *on, const char *name) {
    int v = __atomic_load_n(on, __ATOMIC_RELAXED);
    if (v < 0) v = !(getenv(name) && !atoi(getenv(name))), __atomic_store_n(on, v, __ATOMIC_RELAXED);
    return v;
}
static int sound_timed(void) {
    static int on = -1;
    return __atomic_load_n(&hos_frame_seconds_bits, __ATOMIC_RELAXED) != 0 && switched(&on, "HOS_FPS_SOUND");
}
static int solver_timed(void) {
    static int on = -1;
    return __atomic_load_n(&hos_frame_seconds_bits, __ATOMIC_RELAXED) != 0 && switched(&on, "HOS_FPS_SOLVER");
}
static int fps_log(void) {
    static int on = -1;   /* (read by the game's threads) */
    int v = __atomic_load_n(&on, __ATOMIC_RELAXED);
    if (v < 0) v = getenv("HOS_FPS_LOG") != NULL, __atomic_store_n(&on, v, __ATOMIC_RELAXED);
    return v;
}

static OotSoundGate sound_gate = OOT_SOUND_GATE_INIT;
static long long sound_calls, sound_runs;   /* (HOS_FPS_LOG's counts, under sound_lock) */
static SRWLOCK sound_lock = SRWLOCK_INIT;   /* (the job's phases may come from different threads) */

/* f_80435300's head: phase w2, slot the guest address of the pointer to the object whose +0x10 is the game step (the job's own
   load). 0: the job returns at once */
int hos_oot_sound_gate(Ctx *c, uint32_t phase, uint64_t slot) {
    (void)c;
    float step = 1.0f;
    const int t = sound_timed();
    if (t && phase == 0) {
        const uint64_t object = G64(slot);
        const uint64_t time = object ? G64(object) : 0;
        if (time) step = oot_bits_float(G32(time + 0x10));
    }
    long long ran = -1;
    AcquireSRWLockExclusive(&sound_lock);
    const int run = oot_sound_gate(&sound_gate, phase, step, t);
    if (phase == 0 && fps_log()) {
        sound_runs += run;
        if (!(++sound_calls % 600)) ran = sound_runs, sound_runs = 0;
    }
    ReleaseSRWLockExclusive(&sound_lock);
    if (ran >= 0)
        hos_log("oot: sound job ran %lld of the last 600 frames (step %.3f%s)", ran, step,
                oot_sound_partial(step, t) ? ", held to 60 Hz" : "");
    return run;
}

/* The step f_80435300's phase 0 hands to the sound engine (its float's bits) */
uint32_t hos_oot_sound_step(uint32_t step_bits) {
    return oot_sound_step(step_bits, sound_timed());
}

/* The solver steps of f_838ceb80 / f_838cfc10: game, the game's count; scaled_bits, the float it cut; per_frame_bits, the steps
   of a 60 fps frame (a float) */
uint32_t hos_oot_solver_steps(uint32_t game, uint32_t scaled_bits, uint32_t per_frame_bits) {
    const int32_t steps = oot_solver_steps((int32_t)game, scaled_bits, per_frame_bits, solver_timed());
    if (fps_log()) {
        static volatile LONG64 calls;
        const LONG64 n = InterlockedIncrement64(&calls);
        if (n % 600 == 1)
            hos_log("oot: physics solver steps %d (the game's %d: frame step %.3f x %.0f steps a 60 fps frame)", steps, (int32_t)game,
                    (oot_bits_float(scaled_bits) - 0.001f) / oot_bits_float(per_frame_bits), oot_bits_float(per_frame_bits));
    }
    return (uint32_t)steps;
}
