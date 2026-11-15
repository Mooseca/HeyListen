// gpu/vk/exe_base.h with the POSIX CaptureStackBackTrace (host/posix/windows.h), as RX_VK_RB_PROF's RbScope uses them: the
// return address into outer() less exe_base() is inside outer() in the link map (its address and size from nm, the
// arguments), and exe_base() is dladdr's dli_fbase, the crash offsets' base. Prints the offset.
#include "../host/posix/windows.h"
#include "../gpu/vk/exe_base.h"

#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>

#define CHECK(name, condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s at line %d\n", name, __LINE__); return 1; } } while (0)

extern "C" __attribute__((noinline)) uintptr_t leaf() {
    void* bt[4];
    const USHORT n = CaptureStackBackTrace(1, 4, bt, nullptr);   // (1: leaf's own frame left out, as RbScope does)
    return n ? (uintptr_t)bt[0] : 0;
}
extern "C" __attribute__((noinline)) uintptr_t outer() {
    const uintptr_t a = leaf();
    asm volatile("" ::: "memory");   // (no tail call: the return address stays in outer)
    return a;
}

int main(int argc, char** argv) {
    if (argc < 3) return 2;
    const uintptr_t sym = std::strtoull(argv[1], nullptr, 16), size = std::strtoull(argv[2], nullptr, 16);
    const uintptr_t base = mkwvk::exe_base();
    CHECK("base found", base != 0);
    Dl_info di;
    CHECK("dladdr", dladdr((void*)&main, &di) && di.dli_fbase);
    CHECK("base is dladdr's", (uintptr_t)di.dli_fbase == base);
    const uintptr_t a = outer();
    CHECK("frame captured", a != 0);
    const uintptr_t off = a - base;
    std::printf("outer at %#lx+%#lx in the map, its frame at offset %#lx\n", (unsigned long)sym, (unsigned long)size, (unsigned long)off);
    CHECK("site inside outer", off > sym && off <= sym + size);
    return 0;
}
