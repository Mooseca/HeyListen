"""The Insert menu's Output device row (Gameplay): Default, or one of the audio outputs the host lists, by its name; kept in
hookshot_options.ini by its id; applied at once; given up for (the default stands in) when the device is not there.

Two real pieces are compiled with stand-ins for the system, no device or game opened:
  - host/nn_audio.c's choice (hos_out_count, hos_out_name, hos_out_id, hos_out_select, out_selected_index, out_mark_bad): the
    generation that tells the audio thread to reopen, and the rule for a device that is not there (the default, with a log
    line, until the menu asks again);
  - gpu/vk/vk_menu.cpp's row (tx_out, hn_out, refresh_outs, out_chosen, out_tell_host): the entries, the id that is told to
    the host, the "(not connected)" entry, and the row with Default only where the host lists none (Linux).
The reopen itself on the stream is in tests/audio_output_errors_test.c (the chosen_ cases).

python -I -B tests/test_audio_output_device.py [--cc gcc] [--cxx g++]
"""
import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

HOST_FIXTURE = r"""
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static char logged[512];
static int log_lines;
static void hos_log(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vsnprintf(logged, sizeof logged, format, args);
    va_end(args);
    log_lines++;
}
static const char *env_device;
static const char *test_getenv(const char *name) { return !strcmp(name, "HOS_AUDIO_DEVICE") ? env_device : NULL; }
#define getenv test_getenv
BLOCK1
/* (the system: three outputs; which of them have a waveOut number) */
struct Sys { const char *id, *name; int wave; };
static struct Sys sys[3] = {{"{0.0.0.00000000}.{aaaa}", "Speakers (Realtek)", 0}, {"{0.0.0.00000000}.{bbbb}", "Headset (USB)", 1},
                            {"{0.0.0.00000000}.{cccc}", "TV (HDMI)", 2}};
static int sys_count = 3;
static int out_enum(OutDev *list, int max) {
    int n = 0;
    if (sys_count < 0) return -1;
    for (int i = 0; i < sys_count && n < max; i++) {
        snprintf(list[n].id, sizeof list[n].id, "%s", sys[i].id);
        snprintf(list[n].name, sizeof list[n].name, "%s", sys[i].name);
        n++;
    }
    return n;
}
static int out_wave_index(const char *id, const char *name) {
    (void)name;
    for (int i = 0; i < sys_count; i++)
        if (!strcmp(sys[i].id, id)) return sys[i].wave;
    return -1;
}
BLOCK2
int main(void) {
    long gen = 0;
    /* (the list, as the menu reads it) */
    assert(hos_out_count() == 3);
    assert(!strcmp(hos_out_name(1), "Headset (USB)") && !strcmp(hos_out_id(1), "{0.0.0.00000000}.{bbbb}"));
    assert(!hos_out_name(5)[0] && !hos_out_id(-1)[0]);
    sys_count = 1;
    assert(hos_out_count() == 1 && !hos_out_name(1)[0]);   /* (listed again: one pulled out is gone from it) */
    sys_count = -1;   /* (no list on this system: Linux) */
    assert(hos_out_count() == -1 && !hos_out_name(0)[0]);
    sys_count = 3;
    /* (nothing chosen: the default, the generation as it was) */
    const long start = out_gen_now();
    hos_out_select(0, "", "");
    assert(out_gen_now() == start && out_selected_index(&gen) == -1 && gen == start);
    /* (a device chosen: a new generation, its waveOut number; the same choice again changes nothing) */
    hos_out_select(1, sys[1].id, sys[1].name);
    assert(out_gen_now() == start + 1 && strstr(logged, "Headset (USB)"));
    assert(out_selected_index(&gen) == 1 && gen == start + 1);
    hos_out_select(1, sys[1].id, sys[1].name);
    assert(out_gen_now() == start + 1);
    /* (another device, then Default: each its own generation) */
    hos_out_select(1, sys[2].id, sys[2].name);
    assert(out_gen_now() == start + 2 && out_selected_index(&gen) == 2);
    hos_out_select(0, "", "");
    assert(out_gen_now() == start + 3 && out_selected_index(&gen) == -1);
    /* (the device is not there: the default stands in, one line in the log, for this generation) */
    sys_count = 1;
    hos_out_select(1, sys[2].id, sys[2].name);
    const long gone = out_gen_now();
    log_lines = 0;
    assert(out_selected_index(&gen) == -1 && gen == gone && log_lines == 1 && strstr(logged, "TV (HDMI)") && strstr(logged, "not there"));
    log_lines = 0;
    assert(out_selected_index(&gen) == -1 && !log_lines);   /* (given up for: not asked of the system again, no second line) */
    hos_out_select(1, sys[2].id, sys[2].name);   /* (the menu asked again, still not there: a new generation, tried) */
    assert(out_gen_now() == gone + 1);
    assert(out_selected_index(&gen) == -1 && gen == gone + 1);
    /* (plugged in again: the menu asks again, and the device is the one that plays) */
    sys_count = 3;
    hos_out_select(1, sys[2].id, sys[2].name);
    assert(out_gen_now() == gone + 2 && out_selected_index(&gen) == 2);
    /* (a device that does not play, given up for by the audio thread: the default until the menu asks again) */
    out_mark_bad(gen);
    assert(out_selected_index(&gen) == -1);
    hos_out_select(1, sys[2].id, sys[2].name);
    assert(out_gen_now() == gen + 1 && out_selected_index(&gen) == 2);
    /* (a choice of another device is never held back by the one given up for) */
    out_mark_bad(gen);
    hos_out_select(1, sys[0].id, sys[0].name);
    assert(out_selected_index(&gen) == 0);
    /* (HOS_AUDIO_DEVICE, a waveOut number in the environment, wins over the menu) */
    env_device = "1";
    assert(out_selected_index(&gen) == -1);
    env_device = "";
    assert(out_selected_index(&gen) == 0);
    return 0;
}
"""

MENU_FIXTURE = r"""
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>

struct Row { int tab; const char* name; int* value; int lo, hi; };
struct { int out_dev = 0; } opts;
static Row rows[] = {{1, "Output device", &opts.out_dev, 0, 17}};
struct Host {
    int (*out_count)(void);
    const char* (*out_name)(int);
    const char* (*out_id)(int);
    void (*out_select)(int, const char*, const char*);
};
static const Host* host;
static const char* ids[3] = {"{0.0.0.00000000}.{aaaa}", "{0.0.0.00000000}.{bbbb}", "{0.0.0.00000000}.{cccc}"};
static const char* names[3] = {"Speakers (Realtek)", "Headset (USB)", "TV (HDMI)"};
static int listed = 3, order[3] = {0, 1, 2};
static int told_mode = -1;
static std::string told_id, told_name;
static int count() { return listed; }
static int told_calls;
static const char* name(int i) { return i >= 0 && i < listed ? names[order[i]] : ""; }
static const char* id(int i) { return i >= 0 && i < listed ? ids[order[i]] : ""; }
static void select_(int mode, const char* i, const char* n) { told_calls++, told_mode = mode, told_id = i, told_name = n; }
static const Host full = {count, name, id, select_};
static int count_none() { return -1; }
static const Host nolist = {count_none, name, id, select_};
static const Host none = {nullptr, nullptr, nullptr, nullptr};
constexpr size_t kMicNameKept = 60;
KEEP
MENU
int main() {
    host = &full;
    /* (no choice kept: Default, then each output by its name) */
    refresh_outs();
    assert(opts.out_dev == 0 && rows[0].hi == 3 && told_mode == 0);
    assert(!strcmp(tx_out(0), "Default") && !strcmp(tx_out(1), "Speakers (Realtek)") && !strcmp(tx_out(3), "TV (HDMI)"));
    assert(hn_out(0, 0) && hn_out(1, 0) && !strcmp(hn_out(1, 0), hn_out(2, -1)) && hn_out(3, 1) && !hn_out(1, 2));
    /* (the player picks the second: told by its id, and kept by it) */
    opts.out_dev = 2;
    out_chosen();
    assert(told_mode == 1 && told_id == ids[1] && told_name == "Headset (USB)" && out_want_id == ids[1] && !out_missing);
    /* (the list in another order, one more output: the choice stays on its id, not on its place) */
    order[0] = 2, order[1] = 0, order[2] = 1;
    refresh_outs();
    assert(opts.out_dev == 3 && told_id == ids[1] && !out_missing && rows[0].hi == 3);
    /* (the device unplugged: one entry more, "(not connected)", the kept id told so the host says it is not there) */
    listed = 2, order[0] = 2, order[1] = 0;
    refresh_outs();
    assert(out_missing && opts.out_dev == 3 && rows[0].hi == 3 && told_mode == 1 && told_id == ids[1]);
    assert(!strcmp(tx_out(3), "Headset (USB) (not connected)") && !strcmp(hn_out(3, -1), hn_out(3, 1)) && strcmp(hn_out(3, -1), hn_out(1, -1)));
    /* (the player goes back to Default: the kept choice is cleared, the host told) */
    opts.out_dev = 0;
    out_chosen();
    assert(out_want_id.empty() && !out_missing && rows[0].hi == 2 && told_mode == 0);
    /* (a choice read from the ini: the id and the name; the name of a renamed device is the new one) */
    listed = 3, order[0] = 0, order[1] = 1, order[2] = 2;
    out_want_id = mic_key(ids[2]), out_want_name = "Old name";
    refresh_outs();
    assert(opts.out_dev == 3 && out_want_name == "TV (HDMI)" && told_id == ids[2]);
    /* (a long name is cut to whole characters) */
    out_want_id = "x", out_want_name = std::string(200, 'a');
    refresh_outs();
    assert(out_missing && strlen(tx_out(4)) < 160 && strstr(tx_out(4), " (not connected)"));
    /* (a host that lists none, Linux: Default only, and the row says so) */
    host = &none;
    out_want_id.clear();
    opts.out_dev = 2;
    refresh_outs();
    assert(opts.out_dev == 0 && rows[0].hi == 0 && !strcmp(tx_out(0), "Default") && strstr(hn_out(0, 0), "Linux"));
    /* (a host that cannot list them, Linux: the same row, nothing told, and the id from a shared Windows ini kept) */
    host = &nolist;
    out_want_id = "{kept}", told_calls = 0;
    refresh_outs();
    assert(opts.out_dev == 0 && rows[0].hi == 0 && !out_missing && !told_calls && out_want_id == "{kept}");
    return 0;
}
"""


def between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i)]


def build(cc, std, source, exe, work):
    subprocess.run([cc, std, "-Wall", "-Wextra", "-Werror", str(source), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], cwd=work, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="gcc")
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()

    audio = (ROOT / "host/nn_audio.c").read_text(encoding="utf-8")
    menu = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")

    # the row: Gameplay, "Output device", opts.out_dev, Default and up to sixteen outputs and the unplugged one, not a restart
    # row, the player's own (not the preset's); its key is output_device, its id and name are kept beside it
    row = re.search(r'\{TAB_GAMEPLAY, "Output device", &opts\.out_dev, 0, 1 \+ kMaxOuts, 1, tx_out,\s*"[^{}]*?", hn_out,\s*'
                    r'false, true\},', menu)
    assert row, "the Insert menu has no Output device row"
    for needle in ('"output_device_id"', '"output_device_name"', 'put("output_device_id=%s\\noutput_device_name=%s\\n"',
                   "if (r.value == &opts.out_dev && can_out()) out_chosen();", "refresh_outs();   // (heylisten: and the outputs)"):
        assert needle in menu, needle
    api = (ROOT / "gpu/vk/vk_api.h").read_text(encoding="utf-8")
    assert "void (*out_select)(int mode, const char *id, const char *name);" in api
    backend = (ROOT / "host/rx_backend.c").read_text(encoding="utf-8")
    assert "hos_out_count, hos_out_name, hos_out_id, hos_out_select," in backend

    block = between(audio, "#define OUT_MAX_DEV", "/* (Windows' endpoints) */")
    split = block.index("/* (the platform's:")
    keep = re.search(r"^size_t text_char_start.*?^const char\* tx_mic\(", menu, re.S | re.M).group(0)[:-len("const char* tx_mic(")]
    out_rows = between(menu, "// (heylisten) the Output device row: Default", "const char* tx_rumble(int v)") + \
        between(menu, "// (heylisten) the Output device row's choice to the host", "// (HeyListen) the options file's lowend_rule line")
    with tempfile.TemporaryDirectory(prefix="audio-output-device-") as tmp:
        work = Path(tmp)
        (work / "host.c").write_text(HOST_FIXTURE.replace("BLOCK1", block[:split]).replace("BLOCK2", block[split:]), encoding="utf-8")
        build(args.cc, "-std=gnu11", work / "host.c", work / "host.exe", work)
        (work / "menu.cpp").write_text(MENU_FIXTURE.replace("KEEP", keep).replace("MENU", out_rows), encoding="utf-8")
        build(args.cxx, "-std=c++17", work / "menu.cpp", work / "menu.exe", work)
    print("PASS: Output device: Default or an output by name, kept by its id, applied at once (a new generation), the default "
          "stands in for one that is not there")


if __name__ == "__main__":
    main()
