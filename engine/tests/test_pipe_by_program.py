"""A pipeline belongs to the program object it was built from (gpu/vk/vk_draw.cpp graphics_pipeline).

The key names a program by its code and variant hash, and two program objects can share both: a pipeline the precompile built
from one was drawn with the other, its shaders under the other's layout and constants, and the GPU never finished the draw (the
device lost near water on NVIDIA cards). Ported from Hookshot 65e2cb91 (HeyListen has no kept-ready pipelines, so only the
entry, the lookup and the precompile). Checked by source:

- PipeEntry keeps its program object; every place that makes one stores it (graphics_pipeline, the precompile);
- an entry made for another object is not returned: this one gets its own, under a key of its own, which is not noted;
- RX_VK_PIPE_BY_PROGRAM=0 turns it off, read with the switches' one rule (env_value_off).

python -I -B tests/test_pipe_by_program.py
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class PipeByProgramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.draw = (ROOT / "gpu" / "vk" / "vk_draw.cpp").read_text(encoding="utf-8")

    def test_entry_keeps_its_program_object(self):
        self.assertIn("std::atomic<const Program*> prog{nullptr};", block(self.draw, "struct PipeEntry {"))

    def test_lookup_is_by_key_and_object(self):
        gp = block(self.draw, "PipeEntry* graphics_pipeline(")
        for need in ('const char* e = getenv("RX_VK_PIPE_BY_PROGRAM"); return !(e && env_value_off(e));',
                     "const uint64_t own = mix(key, (uint64_t)(uintptr_t)&p);",
                     "if (made_for && made_for != &p) {", "key = own, own_key = true;",
                     "e->prog.store(&p, std::memory_order_release);",
                     "mine.find(mkey)", "mine[mkey]",
                     "job->note = !own_key", "if (job->note) pipeline_note(",
                     "if (!own_key) pipeline_note("):
            self.assertIn(need, gp, need)
        self.assertLess(gp.index("if (made_for && made_for != &p) {"), gp.index("pipelines.emplace(key"))

    def test_precompile_stores_the_object(self):
        run = block(self.draw, "void precompile_run(")
        self.assertIn("->prog.store(p, std::memory_order_release);", run)


if __name__ == "__main__":
    unittest.main()
