"""The pools made of several dma-bufs: their sparse binds on a queue of their own with RX_VK_SPARSE_QUEUE=1, and the
start-up hint about udmabuf's size limit (issue 14). Compiles gpu/vk/sparse_queue.h's test and reads the source; no
game or GPU. A bind on the replay's queue waited for every frame queued before it (~1 s on a Steam Deck).

    python -I -B tests/test_sparse_queue.py [--cxx g++]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
fails = []


def need(ok, what):
    if not ok:
        fails.append(what)


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def body(src, head):
    """The function starting at `head`, to its closing brace at the start of a line"""
    i = src.find(head)
    if i < 0:
        fails.append("no " + head)
        return ""
    return src[i:src.find("\n}\n", i) + 3]


def check_source():
    mem = read("gpu/vk/vk_memory.cpp")
    pieces = body(mem, "bool import_dma_buf_pieces(")
    own = pieces.find("vkQueueBindSparse(dev.sparse_queue")
    shared = pieces.find("vkQueueBindSparse(dev.queue")
    need(own >= 0 and shared >= 0, "import_dma_buf_pieces: a bind on the sparse queue and one on the replay's")
    if own >= 0 and shared >= 0:
        branch = pieces[pieces.find("if (dev.sparse_queue) {"):pieces.find("} else {", own)]
        need(branch and own > pieces.find("if (dev.sparse_queue) {") > 0, "the sparse queue's bind is in its own branch")
        # (the sparse queue is nobody else's: no replay lock, no flush, no late fix; fence_mu is its lock)
        for word in ("present_mu", "queue_flush_locked", "late_fix_wait_unlocked"):
            need(word not in branch, f"the sparse queue's bind takes {word}")
        need(0 <= pieces.find("std::lock_guard fk(fence_mu);") < own, "the sparse queue's bind under fence_mu")
        wait = pieces.find("vkWaitForFences(dev.device, 1, &fence")
        need(wait > max(own, shared), "both binds' fence waited for before the pool is used")
    need("its fence %.1f" in pieces, "the import's time split, with the fence wait, is logged")

    # (nothing else sends to the sparse queue: it has no lock but fence_mu)
    for path in sorted((ROOT / "gpu/vk").glob("*.cpp")):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"dev\.sparse_queue", src):
            line = src.count("\n", 0, m.start()) + 1
            if path.name == "vk_memory.cpp":
                need(pieces and pieces in src and src.find(pieces) <= m.start() < src.find(pieces) + len(pieces),
                     f"vk_memory.cpp:{line}: dev.sparse_queue outside import_dma_buf_pieces")
            elif path.name != "vk_main.cpp":
                need(False, f"{path.name}:{line}: dev.sparse_queue used")

    dma = body(mem, "bool import_dma_buf(uint64_t lo")
    need("sparse_queue::limit_hint(dmabuf_limit)" in dma and "size_limit_mb" in dma[dma.find("limit_hint"):],
         "import_dma_buf: the hint to raise udmabuf's limit")

    main = read("gpu/vk/vk_main.cpp")
    dev = body(main, "bool create_device() {")
    sw = dev.find('getenv("RX_VK_SPARSE_QUEUE")')
    need(sw >= 0, "vk_main.cpp: the queue only with RX_VK_SPARSE_QUEUE")
    need("sparse_queue::pick_family(" in dev[sw:sw + 1500], "vk_main.cpp: the family from sparse_queue::pick_family")
    need("dev.sparse_family = UINT32_MAX;" in dev[:sw], "vk_main.cpp: no family without the switch")
    need("ci.queueCreateInfoCount = queue_infos;" in dev, "vk_main.cpp: the queue infos counted")
    need("vkGetDeviceQueue(dev.device, dev.sparse_family, 0, &dev.sparse_queue)" in dev, "vk_main.cpp: the queue fetched")
    need(dev.find("#ifdef __linux__", 0, sw) >= 0, "vk_main.cpp: Linux only (the dma-buf pools are)")

    need("`RX_VK_SPARSE_QUEUE=1`" in read("docs/development.md"), "docs/development.md: RX_VK_SPARSE_QUEUE in the table")
    need("size_limit_mb=1024" in (ROOT.parent / "docs/USER_GUIDE.md").read_text(encoding="utf-8"),
         "docs/USER_GUIDE.md: how to raise udmabuf's limit")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    check_source()
    with tempfile.TemporaryDirectory(prefix="sparse-queue-") as tmp:
        exe = Path(tmp) / "sparse-queue"
        subprocess.run([args.cxx, "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/test_sparse_queue.cpp"), "-o", str(exe)], check=True)
        run = subprocess.run([str(exe)], text=True, capture_output=True)
        need(run.returncode == 0, "sparse_queue.h: " + (run.stderr.strip() or f"exit {run.returncode}"))
    if fails:
        for f in fails:
            print("FAIL:", f)
        return 1
    print("test_sparse_queue: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
