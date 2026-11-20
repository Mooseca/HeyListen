"""The native HDR mode's tone mapper (gpu/vk/shaders/hdr_tonemap.comp, vk_hdr_tonemap.cpp, the hook in vk_draw.cpp):
hdr_tonemap_comp_spv.h names the sha256 of the shader it was compiled from, and with glslangValidator (--glslang) the
header's code is the shader compiled now. The curve itself, checked in Python as the shader has it: ST 2084 (PQ) and
BT.2390's EETF identity below the knee (the game's own picture under it: the paper white holds, the map of the game's
colour matrix unchanged), the roll-off to the peak above it, monotonic, the saturation and the over-10000 desaturation.
The C++ shapes are read from the sources: the pass's default key, the draw replaced only when ours runs (the game's kept
as it was otherwise), the same uniform buffer the game's fragment stage reads, the menu's rows and the kept meanings of
the saved values 0..2.

    python -I -B tests/test_hdr_tonemap.py [--glslang glslangValidator]
"""
import argparse
import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu" / "vk"
SHADERS = VK / "shaders"

# ST 2084 (PQ) and the BT.2390 EETF, as shaders/hdr_tonemap.comp has them
M1, M2, C1, C2, C3 = 0.1593017578125, 78.84375, 0.8359375, 18.8515625, 18.6875


def pq_enc(nits):
    l = min(max(nits / 10000.0, 0.0), 1.0) ** M1
    return ((C1 + C2 * l) / (1 + C3 * l)) ** M2


def pq_dec(e):
    p = min(max(e, 0.0), 1.0) ** (1 / M2)
    return 10000.0 * (max(p - C1, 0.0) / (C2 - C3 * p)) ** (1 / M1)


def eetf(nits, peak):
    """BT.2390-3 annex 5.4: nits to a display of peak nits, the light under the knee as it is (the shader's
    mix(e1, p, step(ks, e1)) as an if)"""
    e1 = pq_enc(nits)
    max_lum = pq_enc(peak)
    ks = 1.5 * max_lum - 0.5
    if e1 < ks:
        return pq_dec(e1)
    t = min(max((e1 - ks) / max(1 - ks, 1e-6), 0.0), 1.0)
    t2, t3 = t * t, t * t * t
    p = (2 * t3 - 3 * t2 + 1) * ks + (t3 - 2 * t2 + t) * (1 - ks) + (-2 * t3 + 3 * t2) * max_lum
    return pq_dec(p)


# The game's colour matrix as its pass has it (Rec. 709 in, Rec. 2020 nits out, the display's white baked in: BT.2087's
# matrix scaled), three rows, one per output channel
def game_matrix(white):
    k = float(white)
    return [[k * 0.6274, k * 0.3293, k * 0.0433],
            [k * 0.0691, k * 0.9195, k * 0.0114],
            [k * 0.0164, k * 0.0880, k * 0.8956]]


def tonemap(c, m, peak, sat=1.0):
    """The shader's main(): a Rec. 709 scene colour through the game's matrix, our curve, saturation, desaturation.
    Returns the PQ codes and the output luminance in nits"""
    c = [x if x >= 0.0 else 0.0 for x in c]   # (clamped at 0; a NaN channel read as 0)
    nits = [sum(m[ch][i] * c[i] for i in range(3)) for ch in range(3)]
    nits = [x if x >= 0.0 else 0.0 for x in nits]   # (the matrix's light at 0, a stray NaN as 0)
    y = 0.2627 * nits[0] + 0.6780 * nits[1] + 0.0593 * nits[2]   # Rec. 2020's luminance weights
    out_y = eetf(y, peak)
    scale = out_y / max(y, 1e-6)
    nits = [x * scale for x in nits]
    nits = [out_y + (x - out_y) * sat for x in nits]
    mx = max(nits)
    over = min(max((mx - 10000.0) / max(10000.0 - out_y, 1e-3), 0.0), 1.0)
    nits = [x + (out_y - x) * over for x in nits]
    return [pq_enc(x) for x in nits], out_y


def check_curve():
    # PQ's known points (the same ones test_hdr_encode.py checks)
    assert abs(pq_enc(100) - 0.5081) < 0.001 and abs(pq_enc(1000) - 0.7518) < 0.001 and pq_enc(0) < 1e-6, "PQ curve"
    # the EETF: identity below the knee (a PQ round trip's error, ~1e-9), the peak reached, never passed, monotonic
    knee = pq_dec(1.5 * pq_enc(1000) - 0.5)
    assert abs(eetf(0, 1000)) < 1e-9 and abs(eetf(knee, 1000) - knee) < 1e-6, "identity below the knee"
    for y in (100, knee * 0.5, knee):
        assert abs(eetf(y, 1000) - y) < 1e-6, "the game's own light under the knee"
    assert abs(eetf(10000, 1000) - 1000) < 1e-6, "the brightest light reaches the peak"
    for y in (knee, 400, 800, 1600, 3200, 6400, 10000, 50000):
        assert eetf(y, 1000) <= 1000 + 1e-6, "never past the peak"
    # BT.2390's own numbers (the table the design was checked against)
    for y, want in ((800, 639.3), (1600, 844.9), (6400, 997.7)):
        assert abs(eetf(y, 1000) - want) < 0.5, "BT.2390's roll-off"
    assert all(eetf(a, 1000) <= eetf(b, 1000) for a, b in zip((0, 100, 300, 800, 2000, 8000, 30000),
                                                              (100, 300, 800, 2000, 8000, 30000, 50000))), "monotonic"
    # a dimmer display rolls harder, a peak past the source's range is the identity
    assert eetf(800, 400) < eetf(800, 1000) and eetf(800, 400) <= 400, "the peak is the display's"
    assert abs(eetf(500, 40000) - 500) < 1e-6, "a peak past PQ's range changes nothing"
    # the game's own map, and ours: the same picture under the knee, the highlights rolled off above it
    white, peak = 200, 1000
    m = game_matrix(white)
    game = lambda c: [pq_enc(max(sum(m[ch][i] * c[i] for i in range(3)), 0.0)) for ch in range(3)]   # the game's pass: matrix then PQ
    for c in ((0.01, 0.01, 0.01), (0.18, 0.11, 0.08), (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), (1.2, 1.15, 1.1)):
        ours, out_y = tonemap(list(c), m, peak)
        theirs = game(list(c))
        for a, b in zip(ours, theirs):
            assert abs(a - b) < 2e-6, f"the game's own picture under the knee: {c}"
    assert abs(tonemap([1.0, 1.0, 1.0], m, peak)[1] - white) < 1e-6, "the picture's white at the paper white"
    # above the knee: the game's linear map runs past the display, ours rolls to the peak and stays monotonic
    prev = 0.0
    for k in (2, 4, 8, 16, 32, 50):
        ours, out_y = tonemap([k, k, k], m, peak)
        assert out_y <= peak + 1e-6 and out_y > prev, "the highlights rolled off, brighter stays brighter"
        prev = out_y
    # saturation: 1 the scene's own, 0 grey at the luminance, between
    grey, y = tonemap([0.4, 0.8, 0.1], m, peak, 0.0)
    assert abs(grey[0] - grey[1]) < 1e-12 and abs(grey[1] - grey[2]) < 1e-12 and abs(pq_dec(grey[0]) - y) < 1e-6, "grey at its luminance"
    half, _ = tonemap([0.4, 0.8, 0.1], m, peak, 0.5)
    full, _ = tonemap([0.4, 0.8, 0.1], m, peak, 1.0)
    assert all(min(g, f) <= h <= max(g, f) for g, h, f in zip(grey, half, full)), "saturation between grey and the scene's own"
    # a highlight past PQ's ceiling: desaturated to the light it kept, so the hue holds (nothing passes 10,000 nits)
    ours, _ = tonemap([3000.0, 0.0, 0.0], game_matrix(200), 10000)
    assert abs(ours[0] - ours[1]) < 1e-6 and pq_dec(ours[0]) <= 10000 + 1e-6, "the over-10000 desaturation"
    # a NaN in the scene: read as 0, nothing flares
    ours, y = tonemap([float("nan")] * 3, m, peak)
    assert y == 0.0 and all(x < 1e-6 for x in ours), "a NaN pixel is black"
    ours, _ = tonemap([float("nan"), 1.0, 0.0], m, peak)
    zero, _ = tonemap([0.0, 1.0, 0.0], m, peak)
    assert all(abs(a - b) < 1e-12 for a, b in zip(ours, zero)), "a NaN channel read as 0"


def check_sources():
    draw = (VK / "vk_draw.cpp").read_text(encoding="utf-8")
    tm = (VK / "vk_hdr_tonemap.cpp").read_text(encoding="utf-8")
    menu_h = (VK / "vk_menu.h").read_text(encoding="utf-8")
    menu = (VK / "vk_menu.cpp").read_text(encoding="utf-8")
    replay = (VK / "vk_replay.cpp").read_text(encoding="utf-8")
    # the draw replaced only when ours runs; the game's kept otherwise (the return inside the if, the draw after it)
    hook = "hdr_tonemap_wanted() && hdr_tonemap_key(p.key) && hdr_tonemap_draw(cmd, s, p, at)"
    assert hook in draw, "the draw hook"
    hook_at = draw.index(hook)
    assert "return;\n    }" in draw[hook_at:hook_at + 400], "the game's draw is left out only when ours ran"
    # the game's pass found by its key alone; the same uniform buffer its fragment stage reads
    assert '"dbb1015dd9fcec75"' in tm, "the pass's key"
    assert "uniform_range(s, *fs, 3)" in draw, "the game's c3, as the game's fragment stage reads it"
    assert "const VkDescriptorBufferInfo ubo = uniform_range(s, *fs, 3);" in draw, "the uniform bound for ours"
    # the target and the scene checked; the write and the descriptor state kept right (texture_written with no reason:
    # the draw path's writers, as the upscale stand-in's)
    for shape in ("at.color_format[0] != VK_FORMAT_A2B10G10R10_UNORM_PACK32",
                  "texture_written(at.color[0]);",
                  "descriptors_disturbed();"):
        assert shape in draw, shape
    # the scene the game's pass reads, a float image (anything else bound is not our pass's scene)
    assert "scene->format != VK_FORMAT_B10G11R11_UFLOAT_PACK32" in draw, "the scene's format checked"
    # ours reads the game's colour matrix where its shader reads it, and pushes the peak and the saturation only
    comp = (SHADERS / "hdr_tonemap.comp").read_text(encoding="utf-8")
    for shape in ("game.words[0x120 / 16]", "game.words[0x130 / 16]", "game.words[0x140 / 16]", "VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER"):
        assert shape in comp or shape in tm, shape
    assert "float peak, saturation, pad0, pad1;" in tm, "the push constants: the peak and the saturation"
    assert "std::clamp(opts.hdr_peak, 400, 10000)" in tm and "opts.hdr_saturation, 50, 150" in tm, "the rows' ranges"
    # the menu: the row's fourth value, the saturation only with it; the saved meanings of 0..2 kept
    assert "tx_hdr" in menu and '"Native + our tone mapper"' in menu, "the row's text"
    assert '"HDR", &opts.hdr, 0, 3, 1, tx_hdr' in menu, "the row's values"
    assert "opts.hdr == 3" in menu, "the saturation row only with our tone mapper"
    assert 'v == 1 ? "Expanded" : v == 2 ? "Native (the game\'s)"' in menu, "the meanings of 1 and 2 kept"
    assert "int hdr_saturation = 100;" in menu_h, "the saturation's default"
    # the game is told HDR for 2 and 3 alike; the swapchain's format does not change between them
    assert "opts.hdr >= 2" in replay, "hdr 3 tells the game as hdr 2 does"
    assert "hdr_was != (opts.hdr != 0)" in replay, "the swapchain remade only between off and on"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glslang")
    args = parser.parse_args()
    src = (SHADERS / "hdr_tonemap.comp").read_bytes()
    header = (SHADERS / "hdr_tonemap_comp_spv.h").read_text()
    if hashlib.sha256(src).hexdigest() not in header.splitlines()[0]:
        sys.exit("FAIL: hdr_tonemap_comp_spv.h was not made from hdr_tonemap.comp as it is (recompile it)")
    check_curve()
    check_sources()
    if args.glslang:
        with tempfile.TemporaryDirectory() as d:
            out = Path(d, "t.h")
            subprocess.run([args.glslang, "-V", "--target-env", "vulkan1.2", "--vn", "HDR_TONEMAP_COMP_SPV", "-o", str(out),
                            str(SHADERS / "hdr_tonemap.comp")], check=True, capture_output=True)
            if out.read_text() != "\n".join(header.splitlines(True)[1:]) and out.read_text() != "".join(header.splitlines(True)[1:]):
                sys.exit("FAIL: hdr_tonemap_comp_spv.h differs from the shader compiled now")
    print("PASS: the tone mapper's header is its shader; the curve, the hook and the menu as intended")


if __name__ == "__main__":
    main()
