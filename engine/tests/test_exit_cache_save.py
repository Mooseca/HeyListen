# Copyright (C) 2026 Sacrappy

"""STUT3: the window's close writes the pipeline cache before the process ends, and the exit stays prompt.

A close (host/hos_relaunch.c hos_window_closed_exit) ended the process at once, and the pipeline cache (mkw_vk_pipelines.bin) kept
only what a save in play had written: on the PC 3050 the in-play gate (RX_VK_PCACHE_PLAY_SAVE) seldom let one through, so the
session's new pipelines were compiled again at the next start. By the text:
  - the close asks the back end to save (rx_save_caches_at_exit) after its log line and before hos_crash_clean_end and ExitProcess,
    with a budget of at most a second;
  - the host's call goes through the renderer's table (MkwVkRenderer::save_caches, version 21) and is safe without the Vulkan back end;
  - the back end's save is the forced pipeline_cache_save, run on a thread of its own and waited for at most the budget, with
    RX_VK_EXIT_SAVE=0 to turn it off;
  - the cache file is written whole under another name and renamed, so a save cut short by the exit leaves the old file.

python -I -B tests/test_exit_cache_save.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    relaunch = (ROOT / "host/hos_relaunch.c").read_text(encoding="utf-8")
    close = block(relaunch, "void hos_window_closed_exit(")
    m = re.search(r"rx_save_caches_at_exit\((\d+)\);", close)
    assert m, "the window's close does not save the caches"
    assert 0 < int(m.group(1)) <= 1000, "the close's save may hold the exit for more than a second"
    i_log, i_save = close.index('"display: window closed, exiting"'), close.index("rx_save_caches_at_exit(")
    i_clean, i_exit = close.index("hos_crash_clean_end();"), close.index("ExitProcess(0);")
    assert i_log < i_save < i_clean < i_exit, "the save is not between the close's log line and the exit"

    backend = (ROOT / "host/rx_backend.c").read_text(encoding="utf-8")
    call = block(backend, "int rx_save_caches_at_exit(unsigned budget_ms) {")
    assert "vk && vk->save_caches ? vk->save_caches(budget_ms) : 0" in call, "the host's call is not guarded or not the table's"

    api = (ROOT / "gpu/vk/vk_api.h").read_text(encoding="utf-8")
    assert "#define MKWVK_API_VERSION 21" in api and "int (*save_caches)(uint32_t budget_ms);" in api
    assert api.index("save_caches") > api.index("nvn_release_may_wait"), "the new entry is not at the table's end"
    replay = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    assert "t.save_caches = caches_save_at_exit;" in block(replay, "void fill_replay_table(MkwVkRenderer& t) {")

    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    save = block(draw, "int caches_save_at_exit(uint32_t budget_ms) {")
    assert 'getenv("RX_VK_EXIT_SAVE")' in save, "no switch to turn it off"
    assert "pipeline_cache_save(true);" in save and "std::thread(" in save and ".detach();" in save, \
        "the save is not the forced one on a thread of its own"
    assert "std::chrono::milliseconds(budget_ms)" in save, "the wait is not bounded by the budget"
    whole = block(draw, "void pipeline_cache_save(bool force) {")
    assert 'pcache_path + ".tmp"' in whole and "MoveFileExA(" in whole, "the cache is not written aside and renamed"
    print("PASS the window's close saves the pipeline cache, bounded")


if __name__ == "__main__":
    main()
