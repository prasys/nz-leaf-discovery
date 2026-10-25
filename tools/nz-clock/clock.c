#include "clock.h"

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int i32;

#define ZONE_TYPE_JP 0x3dU
#define ZONE_JP 3240000
#define NZST 4320000
#define NZDT 4680000
#define HOUR_S 3600
#define DAY_S 86400

static u32 rd32(const u8 *p)
{
    return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

/* Division-free (Cortex-A9 has no divider; avoids libgcc/compiler-rt calls).
 * Valid only for 2008..2099, where leap == (y % 4 == 0). */
static i32 dim(i32 y, i32 m)
{
    if (m == 2)
        return 28 + ((y & 3) == 0);
    return (0xA50 >> m) & 1 ? 30 : 31; /* bits 4,6,9,11 = Apr,Jun,Sep,Nov */
}

/* days since 1970-01-01 for a valid y/m/d, 2008 <= y <= 2099 */
static u32 days_from_civil(i32 y, i32 m, i32 d)
{
    u32 n = 365U * (u32)(y - 1970) + (u32)((y - 1969) >> 2);
    i32 i;

    for (i = 1; i < m; i++)
        n += (u32)dim(y, i);
    return n + (u32)(d - 1);
}

/* 0 = Sunday; n mod 7 by binary long subtraction */
static u32 weekday(u32 days)
{
    u32 n = days + 4;
    i32 k;

    for (k = 13; k >= 0; k--)
        if (n >= (7U << k))
            n -= 7U << k;
    return n;
}

/* 14:00 UTC on the Saturday before the Sunday `days` */
static u32 sat_1400(u32 days)
{
    return (days - 1) * DAY_S + 14 * HOUR_S;
}

int nz_apply(const unsigned char *obj, int *total)
{
    i32 y, mo, d, base, user;
    u32 days, t, first_apr, last_sep;
    int dst;

    if (!obj || !total)
        return -2;
    if (rd32(obj + 0x18) != ZONE_TYPE_JP || (i32)rd32(obj + 0x14) != ZONE_JP ||
        rd32(obj + 8) != 1)
        return 0;

    y = (i32)obj[0] | ((i32)obj[1] << 8);
    mo = obj[2];
    d = obj[3];
    if (y < 2008 || y > 2099 || mo < 1 || mo > 12 || d < 1 || d > dim(y, mo) ||
        obj[4] > 23 || obj[5] > 59 || obj[6] > 59)
        return 0;

    days = days_from_civil(y, mo, d);
    t = days * DAY_S + obj[4] * HOUR_S + obj[5] * 60 + obj[6];

    first_apr = days_from_civil(y, 4, 1);
    last_sep = weekday(first_apr);
    if (last_sep)
        first_apr += 7 - last_sep;
    last_sep = days_from_civil(y, 9, 30);
    last_sep -= weekday(last_sep);

    dst = t < sat_1400(first_apr) || t >= sat_1400(last_sep);
    base = dst ? NZDT : NZST;
    user = (i32)rd32(obj + 0x20);

    /* checked base + user; base is positive */
    if (user > 0x7fffffff - base)
        return 0;
    *total = base + user;
    return 1;
}
