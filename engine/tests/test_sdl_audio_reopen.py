"""Linux's sound output opened again (host/nn_audio.c output_reopen after 1.5 s of no sound): host/posix/win32_posix.c
waveOutClose closes the SDL device host/hos_sdl.c opened. It only emptied the queue, so the first device stayed open
and the default output refused a second open: the sound stayed off for the run.

Two runs of one driver: opened, a block played, closed and opened again four times, each new device taking its block.
- Over a stand-in for hos_sdl.c's sound (no SDL needed) that, like a held default output, refuses a second open while
  the first is open, and counts that every open was closed. This is the run that fails without the fix.
- Over the real SDL adapter and the system's SDL with its dummy driver (no sound card, nothing heard). SDL's dummy
  driver takes a second open with the first still open, so this run checks the close path works on a real SDL, not the
  refusal. Skipped where no SDL3 or SDL2 library is installed.

    python -I -B tests/test_sdl_audio_reopen.py [--cc gcc]

Ported from Hookshot f6e60978e (#2970); the stand-in run is HeyListen's.
"""
import argparse
import ctypes.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''#include <windows.h>
#include <mmsystem.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
void hos_log(const char *fmt, ...) { va_list a; va_start(a, fmt); vfprintf(stderr, fmt, a); va_end(a); fputc('\n', stderr); }
#ifdef STUB_ADAPTER
void stub_feed(void);
int stub_balanced(void);
#endif

static int played(WAVEHDR *h) {   /* (the device's callback took the block within 2 s) */
#ifdef STUB_ADAPTER
    stub_feed();   /* (the stand-in has no thread: its callback runs here) */
#endif
    for (int i = 0; i < 400; i++) {
        if (__atomic_load_n(&h->dwFlags, __ATOMIC_ACQUIRE) & WHDR_DONE) return 1;
        nanosleep(&(struct timespec){0, 5000000}, NULL);
    }
    return 0;
}

int main(void) {
    WAVEFORMATEX f = {0};
    f.wFormatTag = WAVE_FORMAT_PCM, f.nChannels = 2, f.nSamplesPerSec = 48000, f.wBitsPerSample = 16;
    f.nBlockAlign = 4, f.nAvgBytesPerSec = 48000 * 4;
    static short pcm[2 * 480];
    for (int i = 0; i < 4; i++) {
        HWAVEOUT w = NULL;
        if (waveOutOpen(&w, WAVE_MAPPER, &f, 0, 0, CALLBACK_NULL) != MMSYSERR_NOERROR) {
            printf("FAIL: open %d of the output was refused (the one before still open)\n", i + 1);
            return 1;
        }
        WAVEHDR h = {0};
        h.lpData = (LPSTR)pcm, h.dwBufferLength = sizeof pcm;
        waveOutPrepareHeader(w, &h, sizeof h);
        waveOutWrite(w, &h, sizeof h);
        if (!played(&h)) {
            printf("FAIL: open %d took no sound\n", i + 1);
            return 1;
        }
        waveOutReset(w);
        waveOutUnprepareHeader(w, &h, sizeof h);
        if (waveOutClose(w) != MMSYSERR_NOERROR) {
            printf("FAIL: close %d\n", i + 1);
            return 1;
        }
    }
#ifdef STUB_ADAPTER
    if (!stub_balanced()) {
        printf("FAIL: the device was not closed after each open\n");
        return 1;
    }
#endif
    return 0;
}
'''

# (the stand-in for hos_sdl.c's sound: one output at a time, as a default device that is still held)
STUB = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
static int open_now, opens, closes;
static void (*pull_fn)(void *, uint8_t *, int);
static void *pull_user;
void *hos_sdl_audio_open(int freq, int channels, int s16, void (*pull)(void *user, uint8_t *out, int len), void *user) {
    (void)freq, (void)channels, (void)s16;
    if (open_now) return NULL;   /* (still held: refused) */
    open_now = 1, opens++;
    pull_fn = pull, pull_user = user;
    return &open_now;
}
void hos_sdl_audio_close(void *out) {
    if (out != &open_now || !open_now) {
        printf("FAIL: closed what was not open\n");
        exit(1);
    }
    open_now = 0, closes++;
    pull_fn = NULL;
}
void stub_feed(void) {
    static uint8_t buf[4 * 480];
    if (pull_fn) pull_fn(pull_user, buf, (int)sizeof buf);
}
int stub_balanced(void) { return opens == 4 && closes == 4 && !open_now; }
'''


def build_and_run(cc, tmp, sources, defines, env, name):
    exe = tmp / name
    subprocess.run([cc, "-std=gnu11", "-D_GNU_SOURCE", "-w", *defines, "-I", str(tmp), "-I", str(ROOT / "host/posix"),
                    "-I", str(ROOT / "host"), *map(str, sources), str(ROOT / "host/posix/win32_posix.c"),
                    "-o", str(exe), "-lpthread", "-ldl", "-lm"], check=True)
    return subprocess.run([str(exe)], capture_output=True, text=True, env=env, timeout=60)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    if not sys.platform.startswith("linux"):
        print("SKIP: Linux's waveOut on SDL runs on Linux")
        return
    with tempfile.TemporaryDirectory(prefix="sdl-audio-reopen-") as tmp:
        tmp = Path(tmp)
        (tmp / "driver.c").write_text(DRIVER, encoding="utf-8")
        (tmp / "stub.c").write_text(STUB, encoding="utf-8")
        r = build_and_run(a.cc, tmp, [tmp / "driver.c", tmp / "stub.c"], ["-DSTUB_ADAPTER"], dict(os.environ), "stub")
        if r.returncode:
            raise SystemExit("FAIL: the sound output did not open again (stand-in adapter):\n" + r.stdout + r.stderr)
        print("pass: stand-in adapter refusing a second open: opened four times, each closed before the next")
        if not (ctypes.util.find_library("SDL3") or ctypes.util.find_library("SDL2-2.0")):
            print("PASS (SDL run skipped: no SDL3 or SDL2 library installed)")
            return
        # (hos_sdl.c beside a hos.h of its own: the real one needs the lifted game's headers, and hos_log is all it takes)
        (tmp / "hos.h").write_text("#define HOS_H\nvoid hos_log(const char *fmt, ...);\n", encoding="utf-8")
        (tmp / "hos_sdl.c").write_text((ROOT / "host/hos_sdl.c").read_text(encoding="utf-8"), encoding="utf-8")
        env = dict(os.environ, SDL_AUDIODRIVER="dummy", SDL_AUDIO_DRIVER="dummy")
        r = build_and_run(a.cc, tmp, [tmp / "driver.c", tmp / "hos_sdl.c"], [], env, "sdl")
        if "sdl: no SDL3 or SDL2 found" in r.stderr:
            print("PASS (SDL run skipped: SDL could not be loaded)")
            return
        if r.returncode:
            raise SystemExit("FAIL: the sound output did not open again:\n" + r.stdout + r.stderr)
    print("PASS: Linux's sound output closes its SDL device: opened again four times, each takes its sound")


if __name__ == "__main__":
    main()
