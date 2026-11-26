// Copyright (C) 2026 Sacrappy

/* Game-free test of the crash record's last GPU write-back by page (host/hos_wb_stamp.h; tests/test_wb_stamp.py builds it), and
   of the crash lines that carry it and the registers: the report keeps them (host/hos_crash_dialog.h hos_crash_report_line drops
   the rows of the game's memory only). Exits non-zero on a failure. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hos_wb_stamp.h"
#include "hos_crash_dialog.h"

static int failures;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); putchar('\n'); } } while (0)

static HosWbStamps s;

int main(void) {
    uint64_t age = 0;
    uint32_t value = 0;
    CHECK(!hos_wbs_find(&s, 0x117e70d010, 100, &age, &value), "an empty table knows no page");
    /* a 64-byte head at 0x117e70d000, submission 218410, at 1000 ms */
    hos_wbs_note(&s, 0x117e70d000, 0x40, 218410, 1000);
    CHECK(hos_wbs_find(&s, 0x117e70dff8, 1250, &age, &value) && age == 250 && value == 218410, "the page: %llu ms, %u",
          (unsigned long long)age, value);
    CHECK(!hos_wbs_find(&s, 0x117e70e000, 1250, &age, &value), "the next page was not written back");
    /* a range over three pages, a later submission over the first */
    hos_wbs_note(&s, 0x117e70dff0, 0x2020, 218411, 1100);
    CHECK(hos_wbs_find(&s, 0x117e70d000, 1100, &age, &value) && age == 0 && value == 218411, "a later write-back wins");
    CHECK(hos_wbs_find(&s, 0x117e70f00f, 1300, &age, &value) && age == 200, "the range's last page");
    CHECK(hos_wbs_find(&s, 0x117e710008, 1300, &age, &value), "the range's last bytes, on a fourth page");
    CHECK(!hos_wbs_find(&s, 0x117e711000, 1300, &age, &value), "past the range");
    /* a range larger than the cap: its first HOS_WBS_MAX_PAGES pages */
    hos_wbs_note(&s, 0x2000000000, (uint64_t)(HOS_WBS_MAX_PAGES + 10) << 12, 7, 5000);
    CHECK(hos_wbs_find(&s, 0x2000000000 + ((uint64_t)(HOS_WBS_MAX_PAGES - 1) << 12), 5000, &age, &value), "the cap's last page");
    CHECK(!hos_wbs_find(&s, 0x2000000000 + ((uint64_t)HOS_WBS_MAX_PAGES << 12), 5000, &age, &value), "past the cap");
    /* another page in the same slot takes it: the first is then not known, never told as the other's */
    uint64_t other = 0;
    const uint64_t page = 0x117e70d000 >> 12;
    for (uint64_t p = page + 1; p < page + (1u << 26) && !other; p++)
        if (hos_wbs_slot(p) == hos_wbs_slot(page)) other = p;
    CHECK(other, "a colliding page");
    hos_wbs_note(&s, other << 12, 8, 9, 1200);
    CHECK(!hos_wbs_find(&s, 0x117e70d000, 1300, &age, &value), "a page whose slot was taken is not known");
    CHECK(hos_wbs_find(&s, other << 12, 1300, &age, &value) && value == 9, "the page that took it");
    /* out of the table's range: nothing */
    hos_wbs_note(&s, 1ull << 41, 8, 1, 1);
    CHECK(!hos_wbs_find(&s, 1ull << 41, 2, &age, &value), "a page past 2^28");

    /* the report keeps the new lines, and still drops the rows of memory */
    char out[400];
    CHECK(hos_crash_report_line(out, sizeof out, "CRASH: guest regs: x0=117e70d000 x1=90 x2=0 x3=1 x4=0 x5=0 x6=0 x7=0"),
          "the guest registers' line kept");
    CHECK(hos_crash_report_line(out, sizeof out, "CRASH: host regs: rax=90 rbx=0 rcx=0 rdx=0 rsi=0 rdi=100000000000 rbp=0 rsp=1"),
          "the host registers' line kept");
    CHECK(hos_crash_report_line(out, sizeof out, "[hos x] CRASH: GPU write-back: fault 90 page 12 ms ago (submission 5);") &&
          !strcmp(out, "CRASH: GPU write-back: fault 90 page 12 ms ago (submission 5);"), "the write-back line kept: %s", out);
    CHECK(!hos_crash_report_line(out, sizeof out, "CRASH:   x0  0000000000000090  x1  0000000000000000"), "the old row still out");
    CHECK(!hos_crash_report_line(out, sizeof out, "CRASH: [x19+0x000] 0 0 0 0"), "a memory row still out");
    if (failures) {
        printf("wb_stamp_test: %d failures\n", failures);
        return 1;
    }
    puts("wb stamp: ok");
    return 0;
}
