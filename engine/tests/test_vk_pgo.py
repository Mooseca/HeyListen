"""The Vulkan back end's play profile (nx2/vk_pgo.py, nx2/build.py's back end branch, scripts/vk_profile.py): which flags a build
gets with no profile, a matching one, a stale one, a counting build, and on Windows. Nothing here runs a compiler or needs the game.

python -I -B tests/test_vk_pgo.py
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "nx2"), str(ROOT / "third_party" / "a64-kit" / "tools"), str(ROOT / "tests")]
import vk_pgo   # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMPILER = "clang version 23.1.5"


class ChooseTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="hookshot-vk-pgo-")
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.gpu, self.work = self.root / "gpu", self.root / "work"
        for name, text in {"vk/vk_replay.cpp": "int replay;\n", "vk/vk_draw.h": "struct D {};\n", "vk/eden/ir.cpp": "int ir;\n",
                           "third_party/suyu/video_core/textures/decoders.cpp": "int dec;\n"}.items():
            (self.gpu / name).parent.mkdir(parents=True, exist_ok=True)
            (self.gpu / name).write_bytes(text.encode())
        self.work.mkdir()
        self.asked = 0

    def compiler(self, version=COMPILER):
        def ask():
            self.asked += 1
            return version
        return ask

    def record(self, path=None, compiler=COMPILER):
        prof = Path(path or self.work / vk_pgo.PROFILE)
        prof.write_bytes(b"\x81rofilpl\xff indexed profile")
        prof.with_name(prof.name + ".stamp").write_text(vk_pgo.stamp_text(str(self.gpu), compiler), encoding="utf-8")
        return prof

    def choose(self, env=None, windows=False, compiler=COMPILER):
        return vk_pgo.choose(env or {}, str(self.work), str(self.gpu), self.compiler(compiler), windows)

    def test_no_profile_builds_as_before_and_says_so(self):
        for windows in (False, True):
            flags, link, note = self.choose(windows=windows)
            self.assertEqual((flags, link), ([], []))
            self.assertIn("not found", note)
        self.assertEqual(self.asked, 0)   # (no compiler asked when there is nothing to check)

    def test_a_matching_profile_is_used_with_its_contents_in_the_flags(self):
        prof = self.record()
        flags, link, note = self.choose()
        self.assertEqual(link, [])
        self.assertEqual(flags[0], "-fprofile-instr-use=" + str(prof))
        self.assertTrue(flags[1].startswith("-DHOOKSHOT_VK_PROFILE_SHA1="))
        self.assertIn("built with the play profile", note)
        before = flags[1]
        prof.write_bytes(b"another profile")   # (same path, new contents: a new object key)
        self.assertNotEqual(self.choose()[0][1], before)

    def test_an_explicit_profile_path_is_checked_the_same_way(self):
        prof = self.record(self.root / "elsewhere.profdata")
        self.assertEqual(self.choose({"RX_VK_PGO": str(prof)})[0][0], "-fprofile-instr-use=" + str(prof))
        flags, _, note = self.choose({"RX_VK_PGO": str(self.root / "missing.profdata")})
        self.assertEqual(flags, [])
        self.assertIn("not found", note)

    def test_a_profile_without_its_stamp_is_not_used(self):
        (self.work / vk_pgo.PROFILE).write_bytes(b"profile")
        flags, link, note = self.choose()
        self.assertEqual((flags, link), ([], []))
        self.assertIn("no stamp", note)

    def test_changed_back_end_sources_make_the_profile_stale(self):
        self.record()
        for name in ("vk/vk_replay.cpp", "vk/vk_draw.h", "third_party/suyu/video_core/textures/decoders.cpp"):
            with self.subTest(name=name):
                path = self.gpu / name
                old = path.read_bytes()
                path.write_bytes(old + b"// changed\n")
                flags, link, note = self.choose()
                self.assertEqual((flags, link), ([], []))
                self.assertIn("stale (the back end's sources changed", note)
                path.write_bytes(old)
        self.assertTrue(self.choose()[0])

    def test_files_outside_the_back_ends_own_are_not_in_the_stamp(self):
        self.record()
        (self.gpu / "vk/eden/ir.cpp").write_bytes(b"int ir_changed;\n")   # (Eden's recompiler: not counted, not stamped)
        self.assertTrue(self.choose()[0])

    def test_line_endings_do_not_make_it_stale(self):
        self.record()
        (self.gpu / "vk/vk_replay.cpp").write_bytes(b"int replay;\r\n")
        self.assertTrue(self.choose()[0])

    def test_another_compiler_makes_it_stale_so_windows_ignores_a_linux_profile(self):
        self.record()
        flags, link, note = self.choose(windows=True, compiler="clang version 21.1.0 (llvm-mingw)")
        self.assertEqual((flags, link), ([], []))
        self.assertIn("the compiler changed", note)

    def test_counting_build_on_linux_only(self):
        flags, link, note = self.choose({"RX_VK_PGO": "gen"})
        self.assertIn("-fprofile-instr-generate", flags)
        self.assertIn("-fprofile-continuous", flags)
        self.assertEqual(link, ["-fprofile-instr-generate"])
        flags, link, note = self.choose({"RX_VK_PGO": "gen"}, windows=True)
        self.assertEqual((flags, link), ([], []))
        self.assertIn("Linux only", note)

    def test_off_ignores_a_matching_profile(self):
        self.record()
        for off in ("0", "off"):
            self.assertEqual(self.choose({"RX_VK_PGO": off})[:2], ([], []))


class BuildBranchTests(unittest.TestCase):
    """build.py's real back end branch (test_shader_stamp_cache.py's fixture): which files get the profile's flags"""

    def setUp(self):
        stamp_cache = load("stamp_cache_for_pgo", ROOT / "tests" / "test_shader_stamp_cache.py")
        self.fixture = stamp_cache.ShaderStampCacheTests("test_own_renderer_source_still_invalidates_its_object")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def jobs(self, linux=True):
        with mock.patch("builtins.print"):
            return self.fixture.jobs(linux)

    def test_with_no_profile_no_file_gets_a_profile_flag(self):
        for linux in (False, True):
            for name, job in self.jobs(linux).items():
                self.assertFalse([f for f in job["flags"] if "profile" in f or "PROFILE" in f], name)

    def test_a_matching_profile_reaches_the_back_ends_own_files_only(self):
        plain = self.jobs()
        work = self.root / "work"
        work.mkdir(exist_ok=True)
        (work / vk_pgo.PROFILE).write_bytes(b"profile")
        (work / (vk_pgo.PROFILE + ".stamp")).write_text(
            vk_pgo.stamp_text(str(self.root / "gpu"), vk_pgo.compiler_version("clang++")), encoding="utf-8")
        used = self.jobs()
        own = {n for n, j in used.items() if any(f.startswith("-fprofile-instr-use=") for f in j["flags"])}
        self.assertEqual(own, {n for n in used if (n.startswith("gpu/vk/") and n.count("/") == 2) or "/textures/" in n})
        self.assertEqual({n for n in used if used[n]["key"] != plain[n]["key"]}, own)
        self.assertNotIn("gpu/vk/eden/translate.cpp", own)
        self.assertFalse([n for n in own if n.startswith(("third_party/", "host/", "gen/"))])

    def test_the_counting_flags_reach_the_same_files(self):
        real = vk_pgo.choose
        # (the fixture runs the branch with a cleared environment: RX_VK_PGO=gen given to the branch's call instead)
        with mock.patch.object(vk_pgo, "choose", side_effect=lambda env, *a: real({"RX_VK_PGO": "gen"}, *a)):
            used = self.jobs()
        own = {n for n, j in used.items() if "-fprofile-instr-generate" in j["flags"]}
        self.assertIn("gpu/vk/vk_draw.cpp", own)
        self.assertFalse([n for n in own if "/eden/" in n or "/sirit/" in n or n.startswith("third_party/")])

    def test_the_linux_link_takes_the_profile_runtime(self):
        text = (ROOT / "nx2" / "build.py").read_text(encoding="utf-8")
        self.assertIn('"@" + vrsp] + vk_pgo_link', text)


class MergeTests(unittest.TestCase):
    def test_merge_writes_the_profile_and_this_checkouts_stamp(self):
        script = load("vk_profile_script", ROOT / "scripts" / "vk_profile.py")
        with tempfile.TemporaryDirectory(prefix="hookshot-vk-merge-") as d:
            raw = Path(d) / "hookshot_vk-1.profraw"
            raw.write_bytes(b"raw")
            out = Path(d) / "hookshot_vk.profdata"

            def fake_run(cmd, check):
                self.assertEqual(cmd[1:4], ["merge", "-o", str(out)])
                self.assertEqual(cmd[4:], [str(raw)])
                out.write_bytes(b"merged")

            with mock.patch.object(script.subprocess, "run", side_effect=fake_run), \
                    mock.patch.object(script.toolchain, "need", side_effect=lambda p: p), \
                    mock.patch.object(script.vk_pgo, "compiler_version", return_value=COMPILER), mock.patch("builtins.print"):
                self.assertEqual(script.main(["merge", d, "--out", str(out)]), 0)
            stamp = (Path(d) / "hookshot_vk.profdata.stamp").read_text(encoding="utf-8")
            self.assertEqual(stamp, vk_pgo.stamp_text(str(ROOT / "gpu"), COMPILER))


if __name__ == "__main__":
    unittest.main()
