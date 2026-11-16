/* (HeyListen) The game's time step under a frame rate cap above 60: the host's measured frame time at the engine's two
   step divides (after upstream Hookshot a2a89ae11, "keep the game at real speed under a Frame rate cap above 60").

   The engine makes its time step in two places from its integer nominal frame rate (the framework's +0x2c8), each a float
   divide "base / nominal": f_80706be0 (the module system's frame: base 60, 30 in the half-rate mode; the frame's step,
   added to the game clock at +0xd58 and handed to the frame-time object, docs/native-engine/main-loop.md) and f_83b6ea90
   (the game's framework's prepare: the global step 60 / nominal, the float at 0x84d61fc8). The engine's own rate is 60
   over a whole number of display intervals, never above 60, and its controller puts 60 back before the steps are made:
   the old way (the measured rate written into +0x2c8, nn_os_sync.c TICK-014) reached the first divide only, and the
   global step stayed a whole 1/60 s a frame: what reads it ran fps / 60 too fast (cutscenes, voice lines, the Deku Tree
   boss above 60). With the hooks the step is base x the frame's seconds at both, whatever the rate.

   The hooks are lines nx2/hl_gates.py puts after the two divides (HL_STEP_HOOK below: both or neither) in the lifted work
   folder, which every worktree shares: a tree without this file asks for none and takes them out, so it links without
   the two symbols. nn_vi.c publishes the frame's seconds (hos_frame_seconds_bits) while the cap is above 60 and the hook
   is in (hos_step_probe set by the first one), and keeps the nominal rate at 60 at most then. HOS_FPS_STEP=0: as before. */
#include "hl_host.h"
#include <windows.h>   /* (SRWLOCK: hos_movie_frames) */
#include <stdlib.h>
#include <string.h>

volatile uint32_t hos_frame_seconds_bits = 0;   /* the frame's seconds as a float's bits; 0: the game's own divide */
volatile uint64_t hos_step_probe = 0;           /* f_80706be0's object (its +0xd58: the game clock in 1/60 s) once the hook ran */

HL_STEP_HOOK(80706be0, "9e4c8d7da24dafcf", 8, 1);   /* the frame's step (vreg 8), and the probe */
HL_STEP_HOOK(83b6ea90, "1f02e7327f22f9b9", 0, 0);   /* the global step (vreg 0) */

/* A movie's frame count above a 60 cap (after upstream Hookshot a7cc747d5 and 244a71e00). The game's movie player adds 1 to
   a count at +760 of itself each update (f_83b7c710), and a cutscene that shows a movie takes that count as its timeline's
   frame (f_83b5ec10, f_83b5e9a0): its narration, its rumble and its own end are placed by it. The movie's picture and sound
   follow the clock, so above 60 fps the count ran fps / 60 times too fast: the narration lines started over each other, and
   the opening story movie went black at half its length at a cap of 120 (the cutscene ended, the decoder played on).
   The hook (HL_MOVIE_HOOK below, a line nx2/hl_gates.py puts after that add) makes the step hos_movie_frames(player): how
   many 60ths of a second this update is worth while the host publishes the frame's seconds (hos_frame_seconds_bits: a cap
   above 60 with the step hooks in), the rest carried to that player's next update; 1, the game's own step, otherwise, and
   with HOS_FPS_MOVIE=0 (for comparisons).
   The step is more than 1 when a frame takes longer than a 60th (up to 4, the longest step nn_vi.c publishes), and the
   count then passes values over. The timeline does not need each one: it fires the events whose time lies between its last
   frame and the new one, walking a list sorted by time (f_8124cfc0). Measured upstream at 36 fps under a cap of 120, steps
   of 1 and 2 all the way: every narration line and the rumble as at 60. A step held at 1 would lose that time instead. */
HL_MOVIE_HOOK(83b7c710, "5d406bbf9b83d30a", 760);

uint32_t hos_movie_frames(uint64_t player) {
    enum { PLACES = 16 };
    const uint32_t bits = __atomic_load_n(&hos_frame_seconds_bits, __ATOMIC_RELAXED);   /* (nn_vi.c writes it at each present) */
    if (!bits) return 1;
    static SRWLOCK lock = SRWLOCK_INIT;
    static int timed = -1;   /* (these four under the lock) */
    static struct { uint64_t player, used; double part; } carry[PLACES];
    static uint64_t calls;
    static unsigned made;
    float secs;
    uint32_t n = 1;
    memcpy(&secs, &bits, 4);
    AcquireSRWLockExclusive(&lock);
    if (timed < 0) timed = !(getenv("HOS_FPS_MOVIE") && !atoi(getenv("HOS_FPS_MOVIE")));
    if (timed) {
        int i = 0;
        while (i < PLACES && carry[i].player != player) i++;
        if (i == PLACES) {
            /* (a player not seen yet takes the place used longest ago, so a movie that plays keeps its own while others come
               and go: its count is exact while no more than PLACES players, itself among them, update in turn. It starts at a
               part of a 60th drawn from a hash of how many places were made: with that many players at once every update is a
               first one, and each count then still grows by the frames' time on average instead of standing still) */
            uint32_t x = made++;
            x ^= x >> 16, x *= 0x85ebca6bu, x ^= x >> 13, x *= 0xc2b2ae35u, x ^= x >> 16;   /* (MurmurHash3's last step) */
            i = 0;
            for (int k = 1; k < PLACES; k++)
                if (carry[k].used < carry[i].used) i = k;
            carry[i].player = player, carry[i].part = x / 4294967296.0;
        }
        carry[i].used = ++calls;
        carry[i].part += (double)secs * 60.0;
        n = (uint32_t)carry[i].part;
        carry[i].part -= n;
    }
    ReleaseSRWLockExclusive(&lock);
    return n;
}
