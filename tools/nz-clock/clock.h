/* NZ clock patch: freestanding, no OS/libc dependencies. */
#ifndef NZ_CLOCK_H
#define NZ_CLOCK_H

/*
 * Rewrites *total (hundredths of a second, as returned by the original
 * OBJ_Time_getTotalOffset) for a JDM unit running the Japan default.
 *
 * obj: clock object (year u16LE @0, month @2, day @3, hour @4, min @5, sec @6,
 *      validity u32LE @8, zone i32LE @0x14, zone type u32LE @0x18,
 *      DST i32LE @0x1c, user offset i32LE @0x20). GMT/UTC date and time.
 *
 * Applies only when zone type == 0x3d, zone == 3240000 (+9 h), validity == 1
 * and the UTC date/time is valid in 2008..2099. Then
 *   *total = NZST 4320000 (+12 h) or NZDT 4680000 (+13 h) + user offset;
 * the old DST field is ignored. Rules: DST ends first Sunday of April 03:00
 * NZDT, starts last Sunday of September 02:00 NZST.
 *
 * Returns 1 if *total was replaced, 0 if left unchanged (not applicable, or
 * arithmetic overflow), -2 if obj or total is NULL.
 */
int nz_apply(const unsigned char *obj, int *total);

#endif
