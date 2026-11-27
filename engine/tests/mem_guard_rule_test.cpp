// Copyright (C) 2026 Sacrappy
// the memory guard's rule (gpu/vk/mem_guard_rule.h): which GPUs have it on without a switch, and what each switch does
#include "../gpu/vk/mem_guard_rule.h"
#include <cstdio>

static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); failures++; } } while (0)

int main() {
    using namespace mem_guard;
    const uint32_t amd = 0x1002, nv = 0x10de, intel = 0x8086;
    // no switch set: pools only, an integrated AMD GPU on Windows alone
    { const Rule r = decide(amd, true, true, -1, -1, -1); CHECK(r.pools && !r.blocks && r.automatic && r.on()); }   // Vega 8, Z2 Extreme, the Deck's APU on Windows
    { const Rule r = decide(amd, false, true, -1, -1, -1); CHECK(!r.on()); }    // a discrete Radeon
    { const Rule r = decide(amd, true, false, -1, -1, -1); CHECK(!r.on()); }    // Linux (RADV: its own pressure valves)
    { const Rule r = decide(nv, true, true, -1, -1, -1); CHECK(!r.on()); }
    { const Rule r = decide(intel, true, true, -1, -1, -1); CHECK(!r.on()); }   // Intel integrated: not this driver
    { const Rule r = decide(nv, false, true, -1, -1, -1); CHECK(!r.on()); }
    // RX_VK_MEM_GUARD forces both anywhere, or nothing anywhere
    { const Rule r = decide(nv, false, false, 1, -1, -1); CHECK(r.pools && r.blocks && !r.automatic); }
    { const Rule r = decide(amd, false, true, 1, -1, -1); CHECK(r.pools && r.blocks); }
    { const Rule r = decide(amd, true, true, 1, -1, -1); CHECK(r.pools && r.blocks && !r.automatic); }
    { const Rule r = decide(amd, true, true, 0, -1, -1); CHECK(!r.on() && !r.automatic); }
    { const Rule r = decide(nv, false, false, 0, -1, -1); CHECK(!r.on()); }
    // the sub-switches, over the rule and over the master
    { const Rule r = decide(amd, true, true, -1, 0, -1); CHECK(!r.pools && !r.blocks); }             // pools off on the rule's GPU
    { const Rule r = decide(amd, true, true, -1, -1, 1); CHECK(r.pools && r.blocks); }               // blocks added to the rule's pools
    { const Rule r = decide(amd, true, true, -1, 0, 1); CHECK(!r.pools && r.blocks); }               // blocks only
    { const Rule r = decide(nv, false, false, -1, 1, -1); CHECK(r.pools && !r.blocks && !r.automatic); }   // pools forced on anywhere
    { const Rule r = decide(nv, false, false, -1, -1, 1); CHECK(!r.pools && r.blocks); }
    { const Rule r = decide(amd, true, true, 1, -1, 0); CHECK(r.pools && !r.blocks); }               // master on, blocks off: LAP2's pools-only measure
    { const Rule r = decide(amd, true, true, 1, 0, -1); CHECK(!r.pools && r.blocks); }               // blocks only
    { const Rule r = decide(amd, true, true, 0, 1, -1); CHECK(r.pools && !r.blocks); }               // a sub-switch wins over the master
    // the environment words
    CHECK(env_switch(nullptr) == -1 && env_switch("") == -1 && env_switch("0") == 0 && env_switch("1") == 1 && env_switch("2") == 1);
    CHECK(automatic(0x1002, true, true) && !automatic(0x1002, false, true) && !automatic(0x1002, true, false) && !automatic(0x10de, true, true));
    std::printf("mem_guard_rule: %d failures\n", failures);
    return failures ? 1 : 0;
}
