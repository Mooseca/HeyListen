// Copyright (C) 2026 Sacrappy
// lowend_rule (gpu/vk/lowend_rule.h): the volumetric fog's programs and the first-start rule for low-end GPUs.
// tests/test_lowend_rule.py
#include "../gpu/vk/lowend_rule.h"

#include <cstdio>
#include <string>
#include <utility>
#include <vector>

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

    expect(first_start(-1, false, true, true) == PROBE, "an integrated GPU, never asked, settings the player's own: measured");
    expect(first_start(-1, true, true, true) == NONE, "asked once already: never again");
    expect(first_start(-1, false, false, true) == NONE, "a discrete GPU: never");
    expect(first_start(-1, false, true, false) == NONE, "the row or its settings touched by the player: not measured");
    expect(first_start(0, false, true, true) == NONE, "HL_LOWEND=0: never");
    expect(first_start(1, false, false, true) == APPLY_THIS_RUN, "HL_LOWEND=1 on any GPU: this run only");
    expect(first_start(1, true, true, false) == APPLY_THIS_RUN, "HL_LOWEND=1 after it was asked: this run only, nothing saved");

    expect(mirror_not_wait(0x1002, true, false), "AMD integrated without mesh shaders (a Vega 8): the mirror, no wait");
    expect(!mirror_not_wait(0x8086, true, false), "Intel integrated without mesh shaders: not measured, as before");
    expect(!mirror_not_wait(0x1002, true, true), "AMD integrated with mesh shaders (780M): as before");
    expect(!mirror_not_wait(0x1002, false, false), "AMD discrete: as before");
    expect(kResolution == 6 && kHandheld == 1 && kFog == 0, "the rule's rows: 33%, handheld, fog off");
    {   // (the options file's own lines and line endings kept; only the rule's keys rewritten or added)
        const std::vector<std::pair<std::string, int>> keys = {{"resolution", 6}, {"handheld_profile", 1}, {"volumetric_fog", 0},
                                                               {"lowend_rule", 1}};
        const std::string crlf = "microphone=2\r\nresolution=4\r\nframe_pacing=0\r\nhandheld_profile=0\r\n";
        expect(ini_put_text(crlf, keys) == "microphone=2\r\nresolution=6\r\nframe_pacing=0\r\nhandheld_profile=1\r\n"
                                           "volumetric_fog=0\r\nlowend_rule=1\r\n", "a CRLF file stays CRLF, appended lines too");
        const std::string lf = "resolution=4\nx=1\n";
        expect(ini_put_text(lf, keys) == "resolution=6\nx=1\nhandheld_profile=1\nvolumetric_fog=0\nlowend_rule=1\n", "an LF file stays LF");
        expect(ini_put_text("", keys) == "resolution=6\nhandheld_profile=1\nvolumetric_fog=0\nlowend_rule=1\n", "no file: the keys alone");
        expect(ini_put_text("resolution_x=1\r\nlast=2", keys).rfind("resolution_x=1\r\nlast=2\r\nresolution=6\r\n", 0) == 0,
               "a key that only starts the same is not the key; a last line without its ending gets the file's");
    }
    {   // (the Lowest preset's first start: the preset's line and the rows it sets in place, other lines and endings kept)
        const std::vector<std::pair<std::string, int>> on = {{"quality_preset", 1}, {"resolution", kResolution}, {"handheld_profile", kHandheld},
                                                             {"volumetric_fog", kFog}, {"options_version", 4}, {"lowend_rule", 1}};
        for (const char* eol : {"\r\n", "\n"}) {
            const std::string e = eol;
            const std::string before = "a=1" + e + "resolution=0" + e + "options_version=3" + e + "handheld_profile=0" + e + "x=2" + e;
            expect(ini_put_text(before, on) == "a=1" + e + "resolution=6" + e + "options_version=4" + e + "handheld_profile=1" + e + "x=2" + e +
                                                   "quality_preset=1" + e + "volumetric_fog=0" + e + "lowend_rule=1" + e,
                   "the rows in place (the version too), the others at the end, the file's endings");
        }
    }
    // (the Quality preset's numbers: a file from before version 4 has Minimum to Ultra at 1 to 5; the old Low-end settings row On is Lowest)
    expect(migrate_preset(3, 0, false) == 0, "Custom stays Custom");
    expect(migrate_preset(3, 1, false) == 2 && migrate_preset(3, 3, false) == 4 && migrate_preset(3, 5, false) == 6, "Minimum, Balanced, Ultra move up one");
    expect(migrate_preset(0, 2, false) == 3, "a file with no version is the old numbering too");
    expect(migrate_preset(4, 1, false) == 1 && migrate_preset(4, 6, false) == 6, "version 4: as saved (1 is Lowest)");
    expect(migrate_preset(3, 0, true) == kLowestPreset && migrate_preset(3, 4, true) == kLowestPreset && migrate_preset(4, 0, true) == kLowestPreset,
           "the old row On: the Lowest preset, whatever the file's preset was");
    expect(migrate_preset(3, 9, false) == kPresets, "a number past the list stops at the last");
    if (failures) return 1;
    std::printf("lowend_rule: all checks passed\n");
    return 0;
}
