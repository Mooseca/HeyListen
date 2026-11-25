# Copyright (C) 2026 Sacrappy
"""The measure that decides whether an integrated GPU is too weak for the game (gpu/vk/lowend_measure.h): frames of play timed over a
window, the average rate against a threshold; and the wiring that feeds it (menu_note_frame, the host's play flag)."""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    menu = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")
    for needle in ["        lowend_probe_frame();   // (the Lowest preset measure, while it runs)", "host->play_on && host->play_on()"]:
        if needle not in menu:
            raise SystemExit("vk_menu.cpp no longer has: " + needle)
    host = (ROOT / "host/rx_backend.c").read_text(encoding="utf-8")
    if "hos_oot_player_seen" not in host:
        raise SystemExit("host/rx_backend.c no longer gives the back end the play flag")
    with tempfile.TemporaryDirectory(prefix="lowend-measure-") as tmp:
        exe = Path(tmp) / "lowend-measure"
        subprocess.run([args.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(ROOT / "tests/test_lowend_measure.cpp"), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()
