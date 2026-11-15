"""The full overlay's "Pipeline waits" and "Shader waits" rows (vk_overlay.cpp) from vk_draw.cpp's waits, split: a wait for a
program still being translated (a draw's cp->ready, a dispatch's) is a shader wait, a wait for its pipeline's build
(pe->ready) a pipeline wait, and vk_replay.cpp hands both to perf_set_waits. A source check (no GPU or game data).

python -I -B tests/test_overlay_waits.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    replay = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    bad = []
    # every wait on a ready flag is counted, and as which kind
    for m in re.finditer(r"wait_for\((\w+)->ready(?:, (true|false))?\)", draw):
        want = "true" if m.group(1) == "cp" else "false"
        if m.group(2) != want:
            bad.append("vk_draw.cpp: %s should be wait_for(%s->ready, %s)" % (m.group(0), m.group(1), want))
    waits = re.findall(r"jobs_wait\((\w+)->ready\);\s*st_waits\+\+;([^}]*)}", draw)
    if not waits or any(obj != "cp" or "st_shader_wait_ms += ms" not in rest for obj, rest in waits):
        bad.append("vk_draw.cpp: the dispatch's program wait is not counted as a shader wait")
    if "if (shader) st_shader_wait_ms += ms;" not in draw:
        bad.append("vk_draw.cpp: wait_for no longer counts its shader waits")
    for needle in ("w.shader_wait_ms = (float)overlay_shader_wait_ms;",
                   "w.pipe_wait_ms = (float)std::max(0.0, overlay_wait_ms - overlay_shader_wait_ms);"):
        if needle not in replay:
            bad.append("vk_replay.cpp no longer has: " + needle)
    if bad:
        print("\n".join(bad))
        sys.exit(1)
    print("overlay waits: shader and pipeline waits counted apart")


if __name__ == "__main__":
    main()
