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
    {   // (the Low-end settings row: On sets the three rows and keeps theirs from before, Off puts them back; other lines and endings stay)
        const std::vector<std::pair<std::string, int>> on = {{"resolution", kResolution}, {"handheld_profile", kHandheld},
                                                             {"volumetric_fog", kFog}, {"lowend_settings", 1},
                                                             {"lowend_prev_resolution", 4}, {"lowend_prev_handheld_profile", 0},
                                                             {"lowend_prev_volumetric_fog", 1}};
        const std::vector<std::string> drop = {"lowend_prev_resolution", "lowend_prev_handheld_profile", "lowend_prev_volumetric_fog"};
        const std::vector<std::pair<std::string, int>> off = {{"resolution", 4}, {"handheld_profile", 0}, {"volumetric_fog", 1},
                                                              {"lowend_settings", 0}};
        for (const char* eol : {"\r\n", "\n"}) {
            const std::string e = eol;
            // the lines in the middle of the file, the row's own line there too, and lines after them that must not move
            const std::string before = "a=1" + e + "resolution=4" + e + "handheld_profile=0" + e + "x=2" + e + "volumetric_fog=1" + e +
                                       "lowend_settings=0" + e + "y=3" + e;
            const std::string applied = ini_edit_text(before, on);
            expect(applied == "a=1" + e + "resolution=6" + e + "handheld_profile=1" + e + "x=2" + e + "volumetric_fog=0" + e +
                                  "lowend_settings=1" + e + "y=3" + e + "lowend_prev_resolution=4" + e +
                                  "lowend_prev_handheld_profile=0" + e + "lowend_prev_volumetric_fog=1" + e,
                   "On: the lines in place, the memory at the end");
            expect(ini_edit_text(applied, off, drop) == before, "Off: exactly the earlier bytes, the memory gone");
            expect(ini_edit_text(ini_edit_text(applied, off, drop), on) == applied, "On, Off, On: as the first On");
            // the first start's marker stays after Off: never again by itself
            const std::string marked = ini_edit_text(applied, {{"lowend_rule", 1}});
            expect(ini_edit_text(marked, off, drop).find("lowend_rule=1") != std::string::npos, "Off keeps the first start's marker");
        }
        {   // (a row the file never had: Off writes its value from before, the default, explicitly)
            const std::string r = ini_edit_text(ini_edit_text("a=1\n", on), off, drop);
            expect(r == "a=1\nresolution=4\nhandheld_profile=0\nvolumetric_fog=1\nlowend_settings=0\n", "Off with lines the file never had");
        }
        expect(ini_edit_text("lowend_prev_x=1\nlowend_prev_resolution=1", {}, drop) == "lowend_prev_x=1\n", "drop: whole keys only");
        // (a row the player changed by hand since keeps his value; a row still at the rule's value goes back)
        expect(restore_value(6, kResolution, 4) == 4, "Off: the resolution still at the rule's value goes back");
        expect(restore_value(3, kResolution, 4) == 3, "Off: a resolution the player changed since stays his");
        expect(restore_value(1, kHandheld, 0) == 0 && restore_value(0, kHandheld, 1) == 0, "handheld: back if at the rule's value, else his");
        expect(restore_value(0, kFog, 1) == 1 && restore_value(1, kFog, 0) == 1, "fog: back if at the rule's value, else his");
        expect(kOff == 0 && kOn == 1, "the row's values: Off 0 (the default), On 1");
    }
    if (failures) return 1;
    std::printf("lowend_rule: all checks passed\n");
    return 0;
}
