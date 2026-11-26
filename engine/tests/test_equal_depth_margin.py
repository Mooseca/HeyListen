"""A colour pass that tests depth EQUAL gets a margin towards the camera on Intel.

The game draws a depth prepass, then colour passes that test EQUAL against it with another program. Intel's compiler
does not give the two programs the same position to the last bit, so most ground pixels failed the test and the sky
showed through (issue 17, Arc B390). The test becomes LESS_OR_EQUAL with a depth bias towards the camera, only where depth
is tested, not written, and the game asked for EQUAL. RX_VK_EQ_BIAS=<units> chooses it on any GPU, 0 turns it off. A draw
that blends keeps EQUAL: LESS_OR_EQUAL drew a haze sheet the game keeps to its own depth over Death Mountain Trail's mountain.
python -I -B tests/test_equal_depth_margin.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gpu" / "vk" / "vk_draw.cpp"


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def main():
    source = SOURCE.read_text(encoding="utf-8")
    state = block(source, "void dynamic_state(VkCommandBuffer cmd")
    if 'getenv("RX_VK_EQ_BIAS")' not in state:
        raise SystemExit("no RX_VK_EQ_BIAS switch")
    # (the default is equal_depth_rule.h's: 64 on Intel, 0 on Intel's Windows driver for Battlemage 0xE2xx and Lunar Lake 0x64xx;
    # tests/test_equal_depth_rule.py has it on each GPU; Longshot 03a6e8d0e and 641030ed9)
    if "equal_depth_rule::default_margin(pr.properties.vendorID, pr.properties.deviceID," not in state or             "drv.driverID == VK_DRIVER_ID_INTEL_PROPRIETARY_WINDOWS" not in state:
        raise SystemExit("the margin's default is not equal_depth_rule's, from the device and its driver")
    if "const float value = getenv(\"RX_VK_EQ_BIAS\") ? (float)atof(getenv(\"RX_VK_EQ_BIAS\")) : rule;" not in state:
        raise SystemExit("RX_VK_EQ_BIAS does not decide over the default")
    rule = (ROOT / "gpu" / "vk" / "equal_depth_rule.h").read_text(encoding="utf-8")
    if "if (vendor_id != kIntel) return 0.0f;" not in rule or "return 64.0f;" not in rule:
        raise SystemExit("the margin is not on by default on Intel only")
    cond = "if (eq_bias > 0 && d.dt && !d.dw && d.dop == VK_COMPARE_OP_EQUAL && !blends)"
    if cond not in state:
        raise SystemExit("the margin is not limited to EQUAL tests that do not write depth and do not blend")
    before = state[:state.index(cond)]
    if "(s.color.blend_en >> i & 1) && at.color_format[i]" not in before:
        raise SystemExit("the margin does not look at the targets' blending")
    # (blending on with ONE, ZERO is no blending: such colour passes keep the margin, or the ground has holes)
    if "blend_factor(b.src_rgb) != VK_BLEND_FACTOR_ONE || blend_factor(b.dst_rgb) != VK_BLEND_FACTOR_ZERO" not in before:
        raise SystemExit("blending with ONE, ZERO counts as blending")
    margin = block(state, cond)
    for line in ("d.dop = VK_COMPARE_OP_LESS_OR_EQUAL;", "d.bias_en = VK_TRUE;", "d.bias[0] = -eq_bias"):
        if line not in margin:
            raise SystemExit("the margin lacks %r" % line)
    if not state.index("d.dop = compare_op(s.ds.df);") < state.index(cond):
        raise SystemExit("the margin must come after the game's compare op is read")
    print("EQUAL depth margin ok")


if __name__ == "__main__":
    main()
