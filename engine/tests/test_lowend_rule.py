# Copyright (C) 2026 Sacrappy
"""Compile and run the low-end rules (gpu/vk/lowend_rule.h; no game/GPU): the volumetric fog's programs, the Volumetric fog row,
and the first-start rule that gives an integrated GPU without mesh shaders the Lowest quality preset (Render resolution 33%, the Handheld profile, the fog off)."""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def need(path, needles):
    src = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in src:
            raise SystemExit(path + " no longer has: " + needle)


def check_source():
    """The dispatch leaves the fog's programs out when the fog is off; the menu has the Lowest preset, the rule and its options-file
    line; the device setup asks the rule once the mesh shaders are known"""
    need("gpu/vk/vk_draw.cpp", ['#include "lowend_rule.h"', "lowend_rule::fog_program_index(cp->key)", "fog_gate.step(fog_runs(), fog_idx)",
                                "if (step == lowend_rule::FogStep::Clear) fog_clear_images(cmd, s, *cp);", "vkCmdClearColorImage(cmd, i.first->image"])
    need("gpu/vk/vk_menu.cpp", ['{TAB_GRAPHICS, "Volumetric fog", &opts.fog, 0, 1, 1, tx_onoff,',
                                'lowend_rule::fog_on(env, opts.fog)',
                                'lowend_rule::first_start(env_int("HL_LOWEND"), lowend_marked, integrated, untouched)',
                                "static void lowend_probe_frame() {", "lowend_probe_frame();   // (the Lowest preset measure, while it runs)",
                                "lowend_probe.feed(prof_now(), on) == lowend_rule::PENDING",
                                'getenv("HL_LOWEND_TEST")', 'getenv("HL_LOWEND_FPS")',
                                "this integrated GPU keeps its settings:",
                                'if (!strcmp(line, "lowend_rule")) lowend_marked = true;',
                                '"Lowest (integrated GPU)", "Minimum (4GB)", "Low (6GB)", "Balanced (8GB)", "High (12GB)", "Ultra (16GB+)"};',
                                '&opts.preset, 0, 6, 1, tx_preset',
                                "case 1: // Lowest (a weak integrated GPU)",
                                "opts.resolution = lowend_rule::kResolution; opts.upscale = 2; opts.sharpness = 30;",
                                "opts.handheld = lowend_rule::kHandheld; opts.fog = lowend_rule::kFog;",
                                "case 2: // Minimum (4GB VRAM / iGPU)\n        opts.resolution = 4;",
                                'key == "lowend_settings" ||', "lowend_rule::kPrevPrefix", 'put("options_version=4\\n");',
                                'if (!strcmp(line, "lowend_settings") && atoi(eq + 1) == 1) lowend_old_row = true;',
                                "lowend_rule::migrate_preset(version, saved_preset, lowend_old_row)",
                                "the Quality preset (Graphics tab) turned to Lowest",
                                "    opts.preset = 1;\n    apply_preset(1);",
                                'keys.push_back({"options_version", 4});',
                                "r.value == &opts.sharpness || r.value == &opts.pace || r.value == &opts.realtime)\n        lowend_touched = true;",
                                "static void ini_put_only(", 'fopen(ini_path().c_str(), "rb")', "lowend_rule::ini_put_text(in, keys);",
                                "lowend_mirror = lowend_rule::mirror_not_wait(vendor_id, integrated, mesh_shader);"])
    src = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")
    body = src[src.index("void menu_first_run_lowend("):]
    body = body[:body.index("\n}\n")]
    if "save();" in body:
        raise SystemExit("the low-end rule must write its own lines only (no whole save)")
    turn = src[src.index("static void lowend_turn_on("):]
    turn = turn[:turn.index("\n}\n")]
    if "save();" in turn:
        raise SystemExit("lowend_turn_on writes the preset's lines only (ini_put_only), never a whole save")
    need("gpu/vk/vk_api.h", ["int (*play_on)(void);", "#define MKWVK_API_VERSION 23"])
    need("host/rx_backend.c", ["hos_profile_threads, hos_oot_player_seen,"])
    need("gpu/vk/vk_memory.cpp", ["discrete || lowend_mirror_not_wait();"])
    need("gpu/vk/vk_replay.cpp", ["!lowend_mirror_not_wait());   // (LAPTOP1: the mirror in its place there)"])
    src = (ROOT / "gpu/vk/vk_main.cpp").read_text(encoding="utf-8")
    at = src.find("menu_first_run_lowend(dev.props.vendorID, dev.props.deviceType == VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU, dev.mesh_shader);")
    mesh = src.find("dev.mesh_shader = dev.mesh_shader && mesh.meshShader && mesh.taskShader;")
    if at < 0 or mesh < 0 or at < mesh:
        raise SystemExit("vk_main.cpp: the low-end rule must be asked after the mesh shaders are known")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="lowend-rule-") as tmp:
        exe = Path(tmp) / "lowend-rule"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/test_lowend_rule.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
