"""The replay's per-draw functions ask for their thread's pass and descriptor writer once, not at every use.

pass() and dw() (TLS_OBJECT in gpu/vk/vk_draw.cpp) are a call and a thread-local read each, which in the renderer's shared
library is __tls_get_addr on Linux. begin_pass, end_pass, draw, draw_hazards and dynamic_state take `Pass& ps = pass();` at
their top, bind_descriptors `DescWriter& wr = dw();`, and read through the reference. That is safe only while the thread's
object is made once and reset in place (draw_begin_recording's `pass() = Pass{}`, build_descriptors' reset), never swapped
for another: this checks both. From Hookshot 0df71f20f (#198). python -I -B tests/test_accessor_once.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def main():
    source = (ROOT / "gpu" / "vk" / "vk_draw.cpp").read_text(encoding="utf-8")
    once = {
        "void begin_pass(": ("pass", "Pass& ps = pass();"),
        "void end_pass(": ("pass", "Pass& ps = pass();"),
        "void draw(VkCommandBuffer cmd, NvnState& s, const DrawArgs& d)": ("pass", "Pass& ps = pass();"),
        "uint16_t draw_hazards(": ("pass", "Pass& ps = pass();"),
        "void dynamic_state(": ("pass", "Pass& ps = pass();"),
        "bool bind_descriptors(": ("dw", "DescWriter& wr = dw();"),
    }
    for marker, (acc, take) in once.items():
        fn = block(source, marker)
        if take not in fn:
            raise SystemExit("%s does not take its %s() once" % (marker, acc))
        n = len(re.findall(r"\b%s\(\)" % acc, fn))
        if n != 1:
            raise SystemExit("%s still asks %s() %d times besides its reference" % (marker, acc, n - 1))
    # (the reference stays the thread's object: made once by TLS_OBJECT, reset in place, never re-pointed)
    for acc in ("pass", "dw"):
        if not re.search(r"^TLS_OBJECT\(%s, " % acc, source, re.M):
            raise SystemExit("%s() is no longer a TLS_OBJECT" % acc)
        if re.search(r"\b%s_tls\s*=" % acc, source):
            raise SystemExit("%s_tls is re-pointed: a reference taken at a function's top could name the old object" % acc)
    if "pass() = Pass{};" not in block(source, "void draw_begin_recording("):
        raise SystemExit("draw_begin_recording no longer resets the pass in place")
    print("PASS: the per-draw functions take the thread's pass and writer once")


if __name__ == "__main__":
    main()
