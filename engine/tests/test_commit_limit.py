"""Windows' commit limit (RAM plus the page file; HeyListen issues 55 and 62, Hookshot 2972, Longshot 91a1ae8b). Every VRAM block is
charged to the process's commit, as the guest's memory is: a run held private commit at the VRAM blocks plus ~21 GB the whole way,
and a 32 GB PC reached its commit limit in Hyrule Field (the renderer's own C++ allocation refused: exception 0x20474343).

Checked here: the textures' budget has a commit rule. Below RX_VK_COMMIT_RESERVE_MB of headroom (GlobalMemoryStatusEx's
ullAvailPageFile, Windows only) the shortfall comes off the budget, as the driver's limit's excess does, and the eviction gives
blocks back; "vk: commit limit near:" says so, at most every 600 frames.
python -I -B tests/test_commit_limit.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(text, head):
    at = text.find(head)
    if at < 0:
        raise SystemExit("FAIL: not found: " + head)
    depth, i = 0, text.index("{", at)
    for j in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[j], 0)
        if depth == 0:
            return text[at:j + 1]
    raise SystemExit("FAIL: unbalanced: " + head)


def main():
    tex = (ROOT / "gpu" / "vk" / "vk_texture.cpp").read_text(encoding="utf-8")
    head = block(tex, "static bool commit_headroom(uint64_t* free_bytes)")
    if "ullAvailPageFile" not in head or "#if defined(_WIN32)" not in head:
        raise SystemExit("FAIL: commit_headroom does not read GlobalMemoryStatusEx's ullAvailPageFile on Windows only")
    reserve = block(tex, "static uint64_t commit_reserve()")
    if "RX_VK_COMMIT_RESERVE_MB" not in reserve or "2560ull << 20" not in reserve:
        raise SystemExit("FAIL: commit_reserve is not RX_VK_COMMIT_RESERVE_MB with a 2560 MB default")
    rule = re.search(r"if \(reserve && commit_headroom\(&commit_free\) && commit_free < reserve\) \{(.*?)\n        \}", tex, re.S)
    if not rule:
        raise SystemExit("FAIL: the textures' budget has no commit rule")
    body = rule.group(1)
    for need in ("const uint64_t over = reserve - commit_free;",
                 "budget = std::min(budget, total_bytes > over ? total_bytes - over : 0);",
                 "vk: commit limit near:"):
        if need not in body:
            raise SystemExit("FAIL: the commit rule lacks: " + need)
    # (the rule sits among the budget's limits, before the budget is used to evict)
    if tex.find("commit_headroom(&commit_free)") > tex.find("static int failures_seen = 0;"):
        raise SystemExit("FAIL: the commit rule comes after the budget's last limit")
    print("PASS: the textures give commit back near Windows' commit limit")


if __name__ == "__main__":
    main()
