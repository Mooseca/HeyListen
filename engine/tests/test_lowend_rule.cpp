// Copyright (C) 2026 Sacrappy
// lowend_rule (gpu/vk/lowend_rule.h): the volumetric fog's programs and the first-start rule for low-end GPUs.
// tests/test_lowend_rule.py
#include "../gpu/vk/lowend_rule.h"

#include <cstdio>

static int failures = 0;
static void expect(bool ok, const char* what) {
    if (!ok) {
        std::printf("FAIL: %s\n", what);
        failures++;
    }
}

int main() {
    using namespace lowend_rule;
    expect(fog_program(0x27ee9883e2a20323ull), "the 96x72x88 fog volume");
    expect(fog_program(0xee7764a6b1ef459cull), "the 48x36x48 fog volume");
    expect(fog_program(0x1e2fcee33a0c7209ull), "the pass after the first volume");
    expect(!fog_program(0x53509044401d78d2ull), "not the noise volumes' program (the foliage's crossfade needs it)");
    expect(!fog_program(0x27ee9883e2a20324ull), "whole keys only");

    expect(fog_on(-1, 1), "row on, no switch: on");
    expect(!fog_on(-1, 0), "row off, no switch: off");
    expect(fog_on(1, 0), "RX_VK_FOG=1 over the row");
    expect(!fog_on(0, 1), "RX_VK_FOG=0 over the row");

    expect(lowend_gpu(true, false), "integrated without mesh shaders (a Vega 8)");
    expect(!lowend_gpu(true, true), "integrated with mesh shaders (a 780M)");
    expect(!lowend_gpu(false, false), "discrete without mesh shaders (an RX 5700): not this rule");
    expect(!lowend_gpu(false, true), "discrete with mesh shaders");

    expect(first_start(-1, false, true) == APPLY_AND_SAVE, "low-end GPU, never applied: applied and saved");
    expect(first_start(-1, true, true) == NONE, "applied once already: the player's rows stay");
    expect(first_start(-1, false, false) == NONE, "another GPU: nothing");
    expect(first_start(0, false, true) == NONE, "HL_LOWEND=0: never");
    expect(first_start(1, false, false) == APPLY_THIS_RUN, "HL_LOWEND=1 on any GPU: this run only");
    expect(first_start(1, true, true) == APPLY_THIS_RUN, "HL_LOWEND=1 after it was applied: this run only, nothing saved");

    if (failures) return 1;
    std::printf("lowend_rule: all checks passed\n");
    return 0;
}
